import os
import json
import re
import subprocess
import shutil
from dotenv import load_dotenv
from core.providers import GroqProvider
from core.evidence_store import EvidenceStore
from core.subtitle_quality import SubtitleQualityReport
from core.movie_understanding import MovieUnderstanding

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

class MovieRecapEngine:
    """
    Channel 3: Full Movie to YouTube Recap Engine.
    1. Extracts embedded studio subtitles (.srt / .ass) directly from raw MKV/MP4 movie files.
    2. Parses dialogue with millisecond precision into a structured dialogue log.
    3. Distills the 100+ minute movie dialogue into an engaging, high-retention 10-12 minute
       YouTube recap script with original movie scene time-anchors.
    4. Adheres strictly to Kokoro TTS audio hygiene: standalone sentences, 3-line allowance,
       no dangling conjunctions, and airtight climax preservation.
    """

    def __init__(self, api_key: str = None, model: str = "qwen/qwen3.8-27b"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        groq_keys = []
        if self.api_key:
            groq_keys.append(self.api_key)
        for k in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY_TWO"), os.getenv("GROQ_API_KEY_THREE"), os.getenv("GROQ_API_KEY_FOUR")]:
            if k and k not in groq_keys:
                groq_keys.append(k)
        self.provider = GroqProvider(model=self.model, api_keys=groq_keys)

    def extract_subtitles_to_json(self, movie_path: str, job_dir: str, preferred_lang: str = "eng") -> str:
        """
        Probes movie streams, finds embedded subtitle track, extracts via ffmpeg,
        and parses into a clean transcript JSON format with float timestamps.
        """
        os.makedirs(job_dir, exist_ok=True)
        video_name = os.path.splitext(os.path.basename(movie_path))[0]
        json_output_path = os.path.join(job_dir, f"{video_name}_audio_transcript.json")

        if os.path.exists(json_output_path):
            print(f"  [MovieEngine] ⏩ Found cached dialogue JSON at: {json_output_path}")
            quality_path = os.path.join(job_dir, f"{video_name}_subtitle_quality.json")
            if not os.path.exists(quality_path):
                try:
                    with open(json_output_path, "r", encoding="utf-8") as f:
                        cached_d = json.load(f)
                    max_ts = max((float(d.get("end", d.get("start", 0))) for d in cached_d), default=5400.0)
                    total_runtime_sec = max(3600.0, max_ts)
                    q_rep = SubtitleQualityReport.analyze(cached_d, total_runtime_sec)
                    print(SubtitleQualityReport.format_report(q_rep))
                    with open(quality_path, "w", encoding="utf-8") as qf:
                        json.dump(q_rep, qf, indent=4)
                except Exception:
                    pass
            return json_output_path

        # 1. Probe for subtitle streams with disposition and tags
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=index,codec_name,disposition:stream_tags=language,title,NUMBER_OF_FRAMES,NUMBER_OF_BYTES",
            "-select_streams", "s",
            "-of", "json",
            movie_path
        ]
        res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(res.stdout)
        streams = probe_data.get("streams", [])

        if not streams:
            raise ValueError(f"No embedded subtitle tracks found in: {movie_path}. (External SRT or Whisper needed).")

        # 2. Filter and rank subtitle streams (strictly exclude forced signs / non-dialogue tracks)
        target_code = "hin" if preferred_lang.lower() in ["hi", "hindi", "hin"] else "eng"

        def is_forced_or_signs_track(s: dict) -> bool:
            tags = s.get("tags", {}) or {}
            title = tags.get("title", "").lower()
            disp = s.get("disposition", {}) or {}
            if disp.get("forced", 0) == 1:
                return True
            for bad_kw in ["forced", "sign", "song", "commentary", "info"]:
                if bad_kw in title:
                    return True
            try:
                frames = int(tags.get("NUMBER_OF_FRAMES", 0) or 0)
                if 0 < frames < 80:
                    return True
            except Exception:
                pass
            return False

        candidates = []
        for s in streams:
            tags = s.get("tags", {}) or {}
            lang = tags.get("language", "").lower()
            title = tags.get("title", "").lower()
            forced = is_forced_or_signs_track(s)
            is_target = target_code in lang
            is_eng = "eng" in lang
            is_sdh = "sdh" in title or "hearing" in title

            score = 0
            if not forced:
                score += 1000
            if is_target:
                score += 500
            elif is_eng:
                score += 200
            if not is_sdh:
                score += 100

            try:
                score += min(int(tags.get("NUMBER_OF_FRAMES", 0) or 0) // 10, 50)
            except Exception:
                pass

            candidates.append((score, s))

        candidates.sort(key=lambda x: x[0], reverse=True)

        temp_srt = os.path.join(job_dir, f"{video_name}_extracted.srt")
        parsed_dialogues = []
        selected_stream = None

        for score, cand_stream in candidates:
            s_idx = cand_stream["index"]
            s_lang = cand_stream.get("tags", {}).get("language", "unknown")
            s_title = cand_stream.get("tags", {}).get("title", "")
            print(f"  [MovieEngine] 🎬 Testing Subtitle Stream #{s_idx} ({s_lang.upper()}, '{s_title}', score={score})...")
            
            extract_cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-i", movie_path,
                "-map", f"0:{s_idx}",
                "-c:s", "copy",
                temp_srt
            ]
            try:
                subprocess.run(extract_cmd, check=True)
                test_dialogues = self._parse_srt_file(temp_srt)
                # Ensure it has substantial dialogue lines (not just 30 signs or song lyrics)
                if len(test_dialogues) >= 80:
                    parsed_dialogues = test_dialogues
                    selected_stream = cand_stream
                    print(f"  [MovieEngine] ✅ Selected valid dialogue stream #{s_idx} with {len(parsed_dialogues)} dialogue cues.")
                    break
                else:
                    print(f"  [MovieEngine] ⚠️ Stream #{s_idx} yielded only {len(test_dialogues)} cues (signs/forced). Skipping to next stream...")
            except Exception as e:
                print(f"  [MovieEngine] ⚠️ Error extracting stream #{s_idx}: {e}")

        # Fallback if no candidate met the 80-line threshold
        if not parsed_dialogues and candidates:
            top_stream = candidates[0][1]
            s_idx = top_stream["index"]
            extract_cmd = ["ffmpeg", "-y", "-v", "error", "-i", movie_path, "-map", f"0:{s_idx}", "-c:s", "copy", temp_srt]
            subprocess.run(extract_cmd, check=True)
            parsed_dialogues = self._parse_srt_file(temp_srt)
            selected_stream = top_stream

        if len(parsed_dialogues) < 30:
            raise ValueError(
                f"Extracted only {len(parsed_dialogues)} dialogue cues from {movie_path}. "
                f"No full dialogue subtitle track exists in the video file (only signs/forced tracks found). "
                f"Please provide an external .srt dialogue file or use Whisper speech-to-text to prevent hallucinations."
            )

        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(parsed_dialogues, f, indent=4, ensure_ascii=False)

        # Generate and save comprehensive subtitle quality report (Improvement #1)
        max_ts = max((float(d.get("end", d.get("start", 0))) for d in parsed_dialogues), default=5400.0)
        total_runtime_sec = max(3600.0, max_ts)
        quality_report = SubtitleQualityReport.analyze(parsed_dialogues, total_runtime_sec)
        print(SubtitleQualityReport.format_report(quality_report))
        quality_path = os.path.join(job_dir, f"{video_name}_subtitle_quality.json")
        try:
            with open(quality_path, "w", encoding="utf-8") as qf:
                json.dump(quality_report, qf, indent=4)
        except Exception as q_err:
            print(f"  [MovieEngine] Warning saving subtitle quality report: {q_err}")

        print(f"  [MovieEngine] ✅ Extracted & parsed {len(parsed_dialogues)} dialogue events: {json_output_path}")
        return json_output_path

    @staticmethod
    def _parse_srt_file(srt_path: str) -> list:
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        def to_secs(t_str):
            parts = t_str.replace(",", ".").split(":")
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

        blocks = re.split(r'\n\s*\n', content.strip())
        dialogues = []

        for b in blocks:
            lines = [l.strip() for l in b.split("\n") if l.strip()]
            if len(lines) >= 3 and "-->" in lines[1]:
                try:
                    times = lines[1].split("-->")
                    st = to_secs(times[0].strip())
                    et = to_secs(times[1].strip())
                    text = " ".join(lines[2:])
                    # Clean tags (e.g. <i>, </i>, font tags, unicode direction marks)
                    text = re.sub(r'<[^>]+>', '', text)
                    text = re.sub(r'[\u202a-\u202e]', '', text).strip()
                    if text:
                        dialogues.append({
                            "id": len(dialogues) + 1,
                            "start": round(st, 3),
                            "end": round(et, 3),
                            "duration_sec": round(et - st, 3),
                            "text": text,
                            # original_text preserved as the raw subtitle text — never overwritten
                            "original_text": text
                        })
                except Exception:
                    pass
        return dialogues

    @staticmethod
    def _clean_movie_title(raw_title: str) -> str:
        """
        Generic movie title sanitizer. Strips release groups, codec tags, resolutions,
        and audio formats so Wikipedia and synopsis search succeed for any movie.
        """
        import os
        t = os.path.splitext(raw_title)[0]
        t = t.replace('_', ' ').replace('.', ' ')
        # Strip common release tags, resolutions, codecs, platforms, and year
        pattern = r'\b(19\d{2}|20\d{2}|720p|1080p|2160p|4k|10bit|8bit|webrip|web-dl|web|bluray|brrip|dvdrip|hdtv|x264|x265|hevc|avc|aac|ac3|ddp\d?\.?\d?|dts|hindi|english|tam|tel|dubbed|subbed|esubs?|c0sm0s|pmz|yify|rarbg|galaxy\w*|nf|amzn|hulu|disney\+?|hbo\w*)\\b'
        t = re.sub(pattern, '', t, flags=re.IGNORECASE)
        t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        # Restore proper apostrophe formatting if separated
        t = re.sub(r"\b(\w+)\s+'\s*s\b", r"\1's", t, flags=re.IGNORECASE)
        return t

    @staticmethod
    def _fetch_film_synopsis(movie_title: str) -> str:
        """
        Fetches the Wikipedia plot synopsis for the movie as a reference for the overall plot arc.

        IMPORTANT: This synopsis is used as a broad narrative reference, NOT as absolute ground
        truth for scene-level narration. The actual film subtitle timeline remains the primary
        source for scene-level claims. Wikipedia may describe a different edition, omit minor
        events, or return a loosely-related page. Synopsis verification is keyword-based only.
        """
        import urllib.request
        import urllib.parse
        
        clean_title = MovieRecapEngine._clean_movie_title(movie_title)
        if not clean_title:
            clean_title = movie_title.strip()

        search_candidates = [
            clean_title,
            f"{clean_title} film",
            f"{clean_title} movie",
        ]
        
        title_keywords = set(re.findall(r'[a-zA-Z]{3,}', clean_title.lower()))

        for query in search_candidates:
            try:
                url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json"
                req = urllib.request.Request(url, headers={"User-Agent": "MovieRecapBot/1.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode())
                hits = data.get("query", {}).get("search", [])
                for hit in hits[:3]:
                    page_title = hit["title"]
                    # Ensure hit title overlaps significantly with query keywords
                    hit_keywords = set(re.findall(r'[a-zA-Z]{3,}', page_title.lower()))
                    if not title_keywords.intersection(hit_keywords):
                        continue

                    content_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={urllib.parse.quote(page_title)}&format=json"
                    req2 = urllib.request.Request(content_url, headers={"User-Agent": "MovieRecapBot/1.0"})
                    with urllib.request.urlopen(req2, timeout=6) as resp2:
                        data2 = json.loads(resp2.read().decode())
                    pages = data2.get("query", {}).get("pages", {})
                    for pid, pdata in pages.items():
                        extract = pdata.get("extract", "")
                        if "== Plot ==" in extract:
                            plot = extract.split("== Plot ==")[1].split("==")[0].strip()
                            if len(plot) > 200:
                                return plot
            except Exception:
                continue
        return ""

    @staticmethod
    def _condense_dialogue_block(condensed_log: list, max_tokens: int = 1800, max_lines: int = 65) -> str:
        """
        Three-Level Importance-Scored Dialogue Condensation (Improvement #4).
        Replaces rigid line-sampling with a content-aware, token-budgeted selection:
        Level 1: Preserve dialogue containing proper names, numbers/dates, locations,
                 and explicit revelation words (kills, secrets, confessions, etc.).
        Level 2: Preserve surrounding dialogue (1 line before/after) for critical lines
                 so context is not lost.
        Level 3: Sample remaining dialogue chronologically, with guaranteed coverage
                 of the ending of the block.
        Hard stops at max_tokens (~1,800 tokens) to stay well below 7,000 ITPM limit.
        """
        if not condensed_log:
            return ""

        # Rough token estimator: ~3.3 chars per token
        def line_tokens(l: str) -> int:
            return int(max(1, len(l) / 3.3))

        total_est = sum(line_tokens(l) for l in condensed_log)
        if total_est <= max_tokens and len(condensed_log) <= max_lines:
            return "\n".join(condensed_log)

        # 1. De-duplicate adjacent identical or near-identical lines first
        deduped = []
        prev_text = None
        for i, line in enumerate(condensed_log):
            text_part = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line).lower().strip()
            if text_part != prev_text:
                deduped.append((i, line))
                prev_text = text_part

        # 2. Level 1: Score lines by importance (proper nouns, revelations, numbers, locations)
        NAME_PATTERN = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b')
        NUMBER_PATTERN = re.compile(r'\b\d{2,}\b')
        REVEAL_WORDS = re.compile(
            r'(?i)\b(kill|murder|dead|die|truth|reveal|secret|lie|betray|confess|'
            r'discover|hidden|stolen|missing|innocent|guilty|arrest|escape|'
            r'love|marry|divorce|pregnant|father|mother|son|daughter|brother|sister)\b'
        )
        LOCATION_WORDS = re.compile(
            r'(?i)\b(hospital|house|office|prison|church|school|hotel|station|'
            r'apartment|room|basement|attic|garden|park|street|city|town)\b'
        )

        scored_lines = []
        for orig_idx, (i, line) in enumerate(deduped):
            text_clean = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line)
            score = 0
            words = text_clean.split()
            # Short lines (≤12 words) carry key dialogue punch
            if 2 <= len(words) <= 8:
                score += 3
            elif len(words) <= 12:
                score += 1
            if NAME_PATTERN.search(text_clean):
                score += 2
            if NUMBER_PATTERN.search(text_clean):
                score += 2
            if REVEAL_WORDS.search(text_clean):
                score += 3
            if LOCATION_WORDS.search(text_clean):
                score += 1
            scored_lines.append((orig_idx, score))

        # Level 1 + Level 2: Pick high-importance lines and include their immediate neighbors (context)
        important_indices = set()
        for idx, score in scored_lines:
            if score >= 3:
                important_indices.add(idx)
                # Level 2: Context preservation (1 before and 1 after)
                if idx > 0:
                    important_indices.add(idx - 1)
                if idx < len(deduped) - 1:
                    important_indices.add(idx + 1)

        # Level 3: Guarantee end-of-block coverage (last 20% of lines to prevent climax truncation)
        end_start = max(0, int(len(deduped) * 0.80))
        for idx in range(end_start, len(deduped)):
            important_indices.add(idx)

        # Fill remaining slots evenly across the block
        budget_important = min(len(important_indices), int(max_lines * 0.70))
        sorted_important = sorted(list(important_indices))[:budget_important]
        selected_set = set(sorted_important)

        remaining_slots = max_lines - len(selected_set)
        non_important = [idx for idx in range(len(deduped)) if idx not in selected_set]
        if non_important and remaining_slots > 0:
            step = max(1, len(non_important) / remaining_slots)
            for j in range(remaining_slots):
                pick_i = int(j * step)
                if pick_i < len(non_important):
                    selected_set.add(non_important[pick_i])

        all_selected = sorted(list(selected_set))

        # Build final text respecting max_tokens ceiling
        result_lines = []
        accumulated_tokens = 0
        for orig_idx in all_selected:
            line = deduped[orig_idx][1]
            lt = line_tokens(line)
            if accumulated_tokens + lt > max_tokens:
                break
            result_lines.append(line)
            accumulated_tokens += lt

        return "\n".join(result_lines)

    @staticmethod
    def _build_initial_story_state(movie_title: str) -> dict:
        """
        Returns an empty story-state dict that is passed between blocks to maintain narrative
        continuity. Updated after every block via _update_story_state().
        """
        return {
            "movie_title": movie_title,
            "characters": {},            # name -> role/description
            "confirmed_facts": [],       # Events established as objective fact
            "character_claims": [],      # Unverified claims made by specific characters
            "unresolved_mysteries": [],  # Open questions/clues not yet explained
            "important_evidence": [],    # Physical or verbal evidence discovered
            "timeline_events_narrated": [],  # Brief summaries of already-narrated events
        }

    def _update_story_state(self, story_state, act_segs: list, block_title: str, block_idx: int = 0) -> any:
        """
        Evidence-Based Story State Updates (Improvement #3).
        Dual-Memory Separation:
        - Generated narration ONLY updates the NARRATION STATE (what has been explained to the viewer).
        - Source facts are established by dialogue evidence and event map ONLY.
        - Generated narration alone can NEVER create a confirmed movie fact.
        """
        if not act_segs:
            return story_state

        narration_block = "\n".join(f"- {s.get('text', '')}" for s in act_segs if s.get("text"))
        
        # If using EvidenceStore
        if isinstance(story_state, EvidenceStore):
            try:
                known_chars = list(story_state.characters.keys())[:8]
                update_prompt = f"""You are a story continuity and narration coverage tracker.
Given these narration segments just generated for "{block_title}", extract narration coverage:

Narration:
{narration_block}

Known characters: {json.dumps(known_chars, ensure_ascii=False)}

Return JSON with these keys:
"block_summary": string — 1-2 sentence summary of what was narrated in this block
"characters_introduced": list of strings — character names introduced to the viewer in this block
"unverified_character_claims": list of objects {{"claimant": str, "claim": str}} — any subjective accusations or unproven claims made by characters
"new_questions_raised": list of strings — mysteries or questions raised"""

                resp = self.provider.chat_completion(
                    system_prompt="You are a narration coverage tracker. Output strict JSON.",
                    user_content=update_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=500,
                    stage_label="narration_coverage_update"
                )
                updates = json.loads(resp)
                summary = updates.get("block_summary", "")
                chars_intro = updates.get("characters_introduced", [])
                story_state.record_narration(
                    block_index=block_idx,
                    narrated_text=summary,
                    characters_mentioned=chars_intro
                )
                for clm in updates.get("unverified_character_claims", []):
                    if clm.get("claimant") and clm.get("claim"):
                        story_state.add_character_claim(
                            claimant=clm["claimant"],
                            claim=clm["claim"],
                            dialogue_id=0
                        )
                for q in updates.get("new_questions_raised", []):
                    story_state.add_mystery(q)
            except Exception as e:
                print(f"  [MovieEngine] ⚠️ Evidence store update notice: {e}")
            return story_state

        # Legacy dict fallback
        try:
            update_prompt = f"""You are a story continuity tracker for a movie recap pipeline.
Given these narration segments just generated for "{block_title}", extract structured updates.

Narration:
{narration_block}

Current known characters: {json.dumps(story_state.get('characters', {}), ensure_ascii=False)}
Current unresolved mysteries: {json.dumps(story_state.get('unresolved_mysteries', []), ensure_ascii=False)}

Return JSON with these keys (only include non-empty updates):
"new_characters": dict of {{name: role}} for any newly introduced characters
"confirmed_facts": list of strings — objective facts established in this block
"character_claims": list of strings — subjective claims/accusations made by characters (prefix with who claims it)
"new_evidence": list of strings — physical or verbal evidence discovered
"resolved_mysteries": list of strings — previously unresolved questions now answered
"new_mysteries": list of strings — new unresolved questions raised
"block_summary": string — 1-2 sentence summary of what was narrated in this block
"""
            resp = self.provider.chat_completion(
                system_prompt="You are a story continuity tracker. Output strict JSON.",
                user_content=update_prompt,
                response_format={"type": "json_object"},
                max_tokens=600,
                stage_label="story_state_update"
            )
            updates = json.loads(resp)

            for name, role in updates.get("new_characters", {}).items():
                story_state["characters"][name] = role
            story_state["confirmed_facts"].extend(updates.get("confirmed_facts", []))
            story_state["character_claims"].extend(updates.get("character_claims", []))
            story_state["important_evidence"].extend(updates.get("new_evidence", []))

            resolved = set(updates.get("resolved_mysteries", []))
            story_state["unresolved_mysteries"] = [
                m for m in story_state["unresolved_mysteries"] if m not in resolved
            ]
            story_state["unresolved_mysteries"].extend(updates.get("new_mysteries", []))

            block_summary = updates.get("block_summary", "")
            if block_summary:
                story_state["timeline_events_narrated"].append(f"[{block_title}] {block_summary}")

        except Exception as e:
            print(f"  [MovieEngine] ⚠️ Story state update notice: {e}")

        return story_state

    @staticmethod
    def _format_story_state_for_prompt(story_state) -> str:
        """
        Formats compact story state for prompt injection (budget: ~250 tokens).
        If EvidenceStore is used, outputs separate SOURCE STORY STATE (facts)
        and NARRATION STATE (viewer coverage).
        """
        if isinstance(story_state, EvidenceStore):
            src_text = story_state.format_source_state_for_prompt(max_tokens=250)
            nar_text = story_state.format_narration_state_for_prompt()
            return f"{src_text}\n\n{nar_text}"

        lines = ["STORY CONTINUITY:"]

        chars = story_state.get("characters", {})
        if chars:
            top_chars = [f"{n}: {r}" for n, r in list(chars.items())[:8]]
            lines.append("Characters: " + "; ".join(top_chars))

        facts = story_state.get("confirmed_facts", [])
        if facts:
            lines.append("Confirmed Facts: " + " | ".join(facts[-5:]))

        claims = story_state.get("character_claims", [])
        if claims:
            lines.append("Unproven Claims: " + " | ".join(claims[-4:]))

        mysteries = story_state.get("unresolved_mysteries", [])
        if mysteries:
            lines.append("Open Mysteries: " + " | ".join(mysteries[-3:]))

        evidence = story_state.get("important_evidence", [])
        if evidence:
            lines.append("Discovered Evidence: " + " | ".join(evidence[-3:]))

        narrated = story_state.get("timeline_events_narrated", [])
        if narrated:
            lines.append("Recent Events: " + " | ".join(narrated[-2:]))

        return "\n".join(lines)

    def generate_recap_script(self, movie_path: str, dialogue_json_path: str, output_script_path: str, target_lang: str = "english", overwrite: bool = False) -> str:
        """
        Distills raw movie dialogue into a high-retention, YouTube recap voiceover script.
        Uses verified whole-movie plot synopsis grounding and a persistent story_state across
        6 story blocks, guaranteeing full story coverage, seamless narrative bridges, airtight
        character introductions, and twist preservation.
        """
        if os.path.exists(output_script_path) and not overwrite:
            print(f"  [MovieEngine] ⏩ Found cached recap script at: {output_script_path}")
            return output_script_path

        # Check for verified golden script in training dataset
        video_name = os.path.splitext(os.path.basename(movie_path))[0]
        golden_training_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "training_dataset", video_name, f"{video_name}_full_movie_{target_lang}_script.json"
        )
        if os.path.exists(golden_training_path) and not overwrite:
            print(f"  [MovieEngine] 🌟 Utilizing verified golden training dataset script: {golden_training_path}")
            shutil.copy2(golden_training_path, output_script_path)
            return output_script_path

        with open(dialogue_json_path, "r", encoding="utf-8") as f:
            dialogues = json.load(f)

        if not dialogues:
            raise ValueError(f"Dialogue log is empty: {dialogue_json_path}")

        total_lines = len(dialogues)
        movie_title = self._clean_movie_title(os.path.basename(movie_path)).title()
        
        # Calculate actual elapsed runtime in seconds
        max_timestamp = max((float(d.get("end", d.get("start", 0))) for d in dialogues), default=5400.0)
        total_runtime_sec = max(3600.0, max_timestamp)
        runtime_mins = int(total_runtime_sec // 60)
        
        print(f"\n[MovieEngine] 🎬 Crafting Production YouTube Recap Script for '{movie_title}'")
        print(f"  [MovieEngine] ⏱️ Total Movie Runtime: ~{runtime_mins} minutes ({total_lines} dialogue lines)")

        # Step 0: Comprehensive Subtitle Quality Validation (Improvement #1)
        job_dir = os.path.dirname(output_script_path)
        os.makedirs(job_dir, exist_ok=True)
        quality_path = os.path.join(job_dir, f"{video_name}_subtitle_quality.json")
        if os.path.exists(quality_path):
            try:
                with open(quality_path, "r", encoding="utf-8") as qf:
                    subtitle_quality = json.load(qf)
            except Exception:
                subtitle_quality = SubtitleQualityReport.analyze(dialogues, total_runtime_sec)
        else:
            subtitle_quality = SubtitleQualityReport.analyze(dialogues, total_runtime_sec)
            try:
                with open(quality_path, "w", encoding="utf-8") as qf:
                    json.dump(subtitle_quality, qf, indent=4)
            except Exception:
                pass
        print(SubtitleQualityReport.format_report(subtitle_quality))

        # Step 1: Fetch Plot Synopsis as a broad narrative reference
        print(f"  [MovieEngine] 🌐 Fetching film plot synopsis for '{movie_title}'...")
        film_synopsis = self._fetch_film_synopsis(movie_title)
        if film_synopsis:
            print(f"  [MovieEngine] ✅ Retrieved film plot synopsis ({len(film_synopsis)} chars). Used as broad reference — subtitle timeline is primary source.")
        else:
            print(f"  [MovieEngine] ℹ️ Online synopsis unavailable. Synthesizing plot outline from dialogue...")
            all_log = [f"[{int(d['start']//60):02d}:{int(d['start']%60):02d}] {d['text'].strip()}" for d in dialogues]
            sampled_full_text = self._condense_dialogue_block(all_log, max_lines=80)
            synopsis_prompt = "You are a master film analyst. Summarize the complete chronological plot of this film from start to finish based on these sampled dialogues. State all main characters, key plot movements, physical evidence, and the climax/twist."
            try:
                film_synopsis = self.provider.chat_completion(
                    system_prompt=synopsis_prompt,
                    user_content=f"Film: {movie_title}\n\nDialogues:\n{sampled_full_text}",
                    max_tokens=1000
                )
            except Exception:
                film_synopsis = f"Recap the film {movie_title} with suspense and full twist preservation."

        # Step 1.5: Extract Structured Event Map & Character Map (Improvement #2)
        event_map_path = os.path.join(job_dir, f"{video_name}_event_map.json")
        if os.path.exists(event_map_path):
            print(f"  [MovieEngine] ⏩ Found cached event map at: {event_map_path}")
            try:
                with open(event_map_path, "r", encoding="utf-8") as emf:
                    event_map = json.load(emf)
            except Exception:
                event_map = {}
        else:
            print(f"  [MovieEngine] 🗺️ Extracting structured Event Map & Character Map from dialogue...")
            event_map = MovieUnderstanding.extract_event_map(
                dialogues=dialogues,
                provider=self.provider,
                film_synopsis=film_synopsis,
                movie_title=movie_title
            )
            try:
                with open(event_map_path, "w", encoding="utf-8") as emf:
                    json.dump(event_map, emf, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"  [MovieEngine] Warning saving event map: {e}")

        # Step 1.6: Initialize Evidence Store with Dual Memory (Improvement #3)
        evidence_store = EvidenceStore(movie_title)
        MovieUnderstanding.populate_evidence_store(event_map, evidence_store)

        # Pre-compute dialogue clusters and vector embeddings ONCE for the entire movie (Improvement #7)
        from core.semantic_aligner import SemanticAligner
        aligner = SemanticAligner()
        clusters = []
        curr_cluster = []
        curr_start = 0.0
        curr_end = 0.0
        for d in dialogues:
            st = float(d.get("start", 0.0))
            et = float(d.get("end", st + 2.0))
            txt = d.get("text", "").strip()
            if not txt:
                continue
            if not curr_cluster or (st - curr_start <= 25.0):
                if not curr_cluster:
                    curr_start = st
                curr_cluster.append(txt)
                curr_end = et
            else:
                clusters.append({"start": curr_start, "end": curr_end, "text": " ".join(curr_cluster)})
                curr_cluster = [txt]
                curr_start = st
                curr_end = et
        if curr_cluster:
            clusters.append({"start": curr_start, "end": curr_end, "text": " ".join(curr_cluster)})

        all_cluster_embeddings = aligner.precompute_cluster_embeddings(clusters)

        # Divide total runtime dynamically into 6 chronological story blocks
        block_count = 6
        block_dur = total_runtime_sec / block_count
        target_segs_per_block = 13

        def fmt_time(secs: float) -> str:
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        # Step 2: Divide plot synopsis into 6 chronological chapter scopes anchored to dialogue snapshots
        print(f"  [MovieEngine] 📋 Structuring plot into {block_count} sequential chapter scopes anchored to dialogue...")
        chapter_scopes = {}
        movie_memory = {
            "movie_title": movie_title,
            "plot_overview": (film_synopsis[:800] + "...") if len(film_synopsis) > 800 else film_synopsis,
            "ending_truth": ""
        }

        if film_synopsis and len(film_synopsis) > 500:
            movie_memory["ending_truth"] = film_synopsis[-1500:].strip()

        try:
            block_samples = []
            for b_idx in range(block_count):
                b_st = b_idx * block_dur
                b_et = (b_idx + 1) * block_dur if b_idx < block_count - 1 else total_runtime_sec + 10.0
                d_win = [d for d in dialogues if b_st <= d['start'] < b_et]
                sample = [f"[{fmt_time(d['start'])}] {d['text'].strip()}" for d in d_win[::max(1, len(d_win) // 8)]][:8]
                block_samples.append(f"Block {b_idx + 1} [{fmt_time(b_st)} - {fmt_time(min(total_runtime_sec, b_et))}]:\n" + "\n".join(sample))

            ch_prompt = f"""You are a master story editor.
Divide the plot synopsis of '{movie_title}' into exactly {block_count} non-overlapping chronological chapter scopes.

Dialogue Snapshots per window:
{chr(10).join(block_samples)}

Film Plot Synopsis (reference):
{film_synopsis[:3000]}

RULES:
1. Match scope strictly to the physical setting and dialogue events in that runtime window. Do NOT pull future events earlier.
2. Signpost flashbacks or flash-forwards so narrator can mark time shifts.
3. For Block {block_count}, explicitly document the true climax, final identity reveal, and resolution.

Return JSON with key 'chapters': list of {block_count} objects with 'block_index' (1 to {block_count}), 'title', and 'scope' (2-3 sentences)."""

            ch_resp = self.provider.chat_completion(
                system_prompt="You are a master film story editor. Output strict JSON with key 'chapters'.",
                user_content=ch_prompt,
                response_format={"type": "json_object"},
                max_tokens=1200,
                stage_label="chapter_planning"
            )
            ch_data = json.loads(ch_resp).get("chapters", [])
            for c in ch_data:
                idx = int(c.get("block_index", 0))
                if idx > 0:
                    chapter_scopes[idx] = c.get("scope", "")
        except Exception as ce:
            print(f"  [MovieEngine] Warning: Could not auto-generate chapter scopes ({ce}).")

        # Build chronological blocks
        acts_data = []
        for b_idx in range(block_count):
            b_start = b_idx * block_dur
            b_end = (b_idx + 1) * block_dur if b_idx < block_count - 1 else total_runtime_sec + 10.0
            b_dialogues = [d for d in dialogues if b_start <= d["start"] < b_end]
            
            is_final_climax = (b_idx == block_count - 1)
            block_title = f"Story Block {b_idx + 1} [{fmt_time(b_start)} - {fmt_time(min(total_runtime_sec, b_end))}]"
            
            guidance = chapter_scopes.get(b_idx + 1) or ""
            if is_final_climax:
                twist_instructions = (
                    "MANDATORY CLIMAX & TWIST RESOLUTION: Faithfully deliver the true ending resolution. "
                    "In psychological thrillers, verify whether the protagonist was validated OR disproved by the final discovery. "
                    f"Verified ending facts: {movie_memory['ending_truth'][:600]}"
                )
                guidance = f"{guidance}\n{twist_instructions}".strip()
            elif not guidance:
                guidance = f"Recap key events and conflicts occurring within [{fmt_time(b_start)} - {fmt_time(min(total_runtime_sec, b_end))}]."

            acts_data.append((block_title, b_dialogues, target_segs_per_block, guidance, is_final_climax, b_start, b_end))

        # Incremental Grounding Setup (Improvement #7)
        all_grounded_segments = []
        current_timeline_cursor = 0.0
        current_last_verified_sec = 0.0

        for b_idx, (act_name, act_dialogues, target_segments, act_guidance, is_final_climax, b_start, b_end) in enumerate(acts_data):
            if not act_dialogues:
                continue

            print(f"  [MovieEngine] ✍️ Generating {act_name} (~{target_segments} voiceover beats)...")
            
            condensed_log = [
                f"[{fmt_time(d['start'])}] {d['text'].strip()}"
                for d in act_dialogues
            ]

            # 3-Level importance-scored condensation (Improvement #4)
            sampled_dialogue_text = self._condense_dialogue_block(condensed_log, max_tokens=1800, max_lines=65)

            system_prompt = f"""You are an elite YouTube movie recap script doctor. Transform raw dialogue into viral, high-retention narration in spoken {target_lang.upper()}.

RECAP PRODUCTION RULES:
1. PUNCHY 3RD-PERSON: Clear, conversational third person ("The detective investigates", "Alice realizes the trap"). Never first person ("I", "we").
2. STRICT DIALOGUE GROUNDING: Base every segment strictly on actual dialogue events at that timestamp. Do NOT jump ahead to future scenes.
3. SEPARATE FACTS VS CLAIMS: Frame unverified allegations as claims ("Alice claims...", "Alvar insists..."), NEVER as confirmed facts.
4. SIMPLE LANGUAGE: Punchy everyday vocabulary. No purple prose, no jargon ("orthodox freudian", "predatory suitors"), no adverbs ("fearlessly", "maliciously").
5. NON-LINEAR TIME MARKERS: If a scene is a flashback, signpost it ("In a flashback...", "Flash-forward reveals...").
6. STRICT 1-SENTENCE CADENCE: Exactly ONE standalone sentence per segment, strictly 10 to 16 words. End with period (.), exclamation (!), or question mark (?). NEVER end on trailing conjunctions ('and', 'so', 'because', 'who').
7. ANCHOR QUOTE: Provide a short 3-8 word quote from characters in this scene for video editing sync.
8. ZERO REPETITION TOLERANCE: Never repeat identical backstory concepts across adjacent segments (e.g. father's estate, marital status). Every sentence must introduce a brand new cause-and-effect action.
9. CHARACTER INTRO BEFORE ACTION: When a new entity enters (inmate, officer, physician), state their name, role, and context before narrating their actions.
10. UNIFY CANONICAL CHARACTER NAMES: Use one consistent name throughout the script. Never alternate between translated variations (e.g. use 'Alice', never flip between 'Alice' and 'Alicia').
11. MANDATORY CLIMAX GROUNDING (FINAL BLOCK): For the final block, divide segments evenly across the penultimate confrontation AND the true ending twist. Never cluster all beats in an early scene while leaving the film's final 10 minutes unnarrated.

Output valid JSON with key 'segments': list of objects {{"text": "10-16 words", "anchor_quote": "3-8 word quote", "time": "HH:MM:SS", "loc": "Scene Location", "scene_change": bool}}"""

            # Dual-memory state prompt injection (Improvement #3)
            story_state_prompt = self._format_story_state_for_prompt(evidence_store)
            event_map_prompt = MovieUnderstanding.format_event_map_for_prompt(event_map, block_start_sec=b_start, block_end_sec=b_end)

            user_prompt = f"""Film: {movie_title}
Act / Window: {act_name}
Target: approximately {target_segments} segments (each EXACTLY 1 standalone sentence, 10-16 words).

CHAPTER SCOPE (FOCUS EXCLUSIVELY ON THESE EVENTS):
{act_guidance}

{event_map_prompt}

{story_state_prompt}

Chronological Dialogue Timeline:
{sampled_dialogue_text}
"""

            resp = self.provider.chat_completion(
                system_prompt=system_prompt,
                user_content=user_prompt,
                response_format={"type": "json_object"},
                max_tokens=1200,
                stage_label=f"script_generation_block_{b_idx + 1}"
            )

            try:
                data = json.loads(resp)
                act_segs = data.get("segments", [])
            except Exception as parse_err:
                print(f"  [MovieEngine] Warning parsing act response ({parse_err}). Falling back.")
                act_segs = []

            # Deduplicate boundary segments if model repeated previous segment
            if all_grounded_segments and act_segs:
                prev_clean = re.sub(r'[^a-z0-9]', '', (all_grounded_segments[-1].get("narration") or "").lower())
                first_clean = re.sub(r'[^a-z0-9]', '', (act_segs[0].get("text") or "").lower())
                if prev_clean and first_clean and (prev_clean == first_clean or prev_clean[:25] == first_clean[:25]):
                    act_segs.pop(0)

            for s in act_segs:
                s["_block_start"] = b_start
                s["_block_end"] = b_end

            # Update evidence store narration state (Improvement #3)
            self._update_story_state(evidence_store, act_segs, act_name, block_idx=b_idx + 1)

            # ── Incremental Grounding (Improvement #7) ──
            # Grounds ONLY this block rather than repeatedly re-grounding all earlier blocks!
            block_grounded = self._ground_and_verify_timestamps(
                raw_segments=act_segs,
                dialogues=dialogues,
                total_runtime_sec=total_runtime_sec,
                target_lang=target_lang,
                movie_path=movie_path,
                timeline_cursor_start=current_timeline_cursor,
                last_verified_sec_start=current_last_verified_sec,
                start_id=len(all_grounded_segments) + 1,
                precomputed_clusters=clusters,
                precomputed_embeddings=all_cluster_embeddings
            )
            all_grounded_segments.extend(block_grounded)

            if block_grounded:
                current_timeline_cursor = block_grounded[-1]["end"]
                for bg in reversed(block_grounded):
                    if not bg.get("is_flashback"):
                        try:
                            parts = str(bg["movie_timestamp"]).split(":")
                            sec = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                            current_last_verified_sec = max(current_last_verified_sec, sec)
                        except Exception:
                            pass
                        break

            # Real-Time Checkpoint Flush to Disk
            temp_flush_path = output_script_path + ".tmp"
            with open(temp_flush_path, "w", encoding="utf-8") as tf:
                json.dump(all_grounded_segments, tf, indent=4, ensure_ascii=False)
            os.replace(temp_flush_path, output_script_path)
            print(f"  [MovieEngine] 💾 Real-Time Sync: Incrementally grounded & flushed {len(all_grounded_segments)} segments ({act_name}) directly to disk.")

        # Save snapshot of final Evidence Store
        evidence_store_path = os.path.join(job_dir, f"{video_name}_evidence_store.json")
        try:
            with open(evidence_store_path, "w", encoding="utf-8") as esf:
                json.dump(evidence_store.to_dict(), esf, indent=4, ensure_ascii=False)
        except Exception:
            pass

        # Segments are already incrementally grounded!
        grounded_segments = all_grounded_segments

        # ─────────────────────────────────────────────────────────────────
        # STEP 4.5: INDEPENDENT CLAIM-LEVEL FACTUAL VERIFICATION (Improvement #5)
        # Deconstructs narration into atomic claims and verifies each against source dialogue
        # ─────────────────────────────────────────────────────────────────
        print(f"\n[MovieEngine] 🔬 Running claim-level factual verification on {len(grounded_segments)} segments...")
        grounded_segments = self._factual_verify_segments(grounded_segments, film_synopsis, evidence_store)

        # ─────────────────────────────────────────────────────────────────
        # STEP 5: AUTOMATED SCRIPT AUDITOR & GENERIC QUALITY ELEVATION (TARGET >= 9.5)
        # Enforces hard rejection gates (Improvement #8): zero contradicted claims allowed!
        # ─────────────────────────────────────────────────────────────────
        from core.script_auditor import ScriptAuditor
        for audit_round in range(1, 5):
            audit_report = ScriptAuditor.audit_script(grounded_segments, film_synopsis=film_synopsis, provider=self.provider)
            score = audit_report.get("overall_score", 0.0)
            audit_ok = audit_report.get("audit_success", False)
            passed = audit_report.get("passed", False)
            hard_rejections = audit_report.get("hard_rejections", [])
            print(f"\n  [ScriptAuditor] 📊 Round {audit_round} Quality Audit: {score}/10.0 (Target: 9.5+, Passed: {passed})")
            for cat, c_score in audit_report.get("category_scores", {}).items():
                print(f"    - {cat}: {c_score}/10.0")
            if hard_rejections:
                print(f"    🛑 Hard Rejections:")
                for hr in hard_rejections:
                    print(f"      - {hr}")

            if passed:
                print(f"  [ScriptAuditor] 🏆 SCRIPT QUALITY CERTIFIED (Score {score}/10.0 >= 9.5, zero hard rejections)!")
                break
            else:
                print(f"  [ScriptAuditor] 🛠️ Applying surgical adjustments to flawed segments...")
                polished_segments = ScriptAuditor.apply_generic_polish(
                    grounded_segments, 
                    provider=self.provider, 
                    film_synopsis=film_synopsis, 
                    audit_report=audit_report,
                    dialogues=dialogues
                )

                # Re-ground using precomputed embeddings
                rewritten_raw = []
                for seg in polished_segments:
                    new_text = ScriptAuditor._get_narration_text(seg)
                    raw_entry = {
                        "text": new_text,
                        "anchor_quote": seg.get("anchor_quote", ""),
                        "time": seg.get("movie_timestamp", ""),
                        "loc": seg.get("scene_location", ""),
                        "scene_change": seg.get("is_scene_change", False),
                        "_block_start": seg.get("_block_start", 0.0),
                        "_block_end": seg.get("_block_end", total_runtime_sec),
                    }
                    rewritten_raw.append(raw_entry)

                grounded_segments = self._ground_and_verify_timestamps(
                    raw_segments=rewritten_raw,
                    dialogues=dialogues,
                    total_runtime_sec=total_runtime_sec,
                    target_lang=target_lang,
                    movie_path=movie_path,
                    precomputed_clusters=clusters,
                    precomputed_embeddings=all_cluster_embeddings
                )
                grounded_segments = self._factual_verify_segments(grounded_segments, film_synopsis, evidence_store)

        # Final audit pass to record official certified rating
        final_report = ScriptAuditor.audit_script(grounded_segments, film_synopsis=film_synopsis, provider=self.provider)
        final_score = final_report.get("overall_score", 0.0)
        final_ok = final_report.get("audit_success", False)
        final_passed = final_report.get("passed", False)
        final_hard_rejections = final_report.get("hard_rejections", [])
        print(f"\n  [ScriptAuditor] 🏁 Final Certified Score: {final_score}/10.0 (Audit Success: {final_ok}, Passed: {final_passed})")
        for cat, c_score in final_report.get("category_scores", {}).items():
            print(f"    - {cat}: {c_score}/10.0")
        if final_hard_rejections:
            print(f"    🛑 Hard Rejections:")
            for hr in final_hard_rejections:
                print(f"      - {hr}")

        if not final_passed:
            review_path = output_script_path.replace(".json", "_needs_review.json")
            with open(review_path, "w", encoding="utf-8") as f:
                json.dump(grounded_segments, f, indent=4, ensure_ascii=False)
            report_path = output_script_path.replace(".json", "_audit_report.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(final_report, f, indent=4, ensure_ascii=False)
            print(
                f"\n[MovieEngine] ⚠️ Script did NOT pass quality audit ({final_score}/10.0 < 9.5 or hard rejections triggered). "
                f"Saved to {review_path} and audit report to {report_path}."
            )
            with open(output_script_path, "w", encoding="utf-8") as f:
                json.dump(grounded_segments, f, indent=4, ensure_ascii=False)
            print(f"[MovieEngine] ⚠️ Also saved to {output_script_path} — REQUIRES MANUAL REVIEW before publishing.")
        else:
            with open(output_script_path, "w", encoding="utf-8") as f:
                json.dump(grounded_segments, f, indent=4, ensure_ascii=False)
            print(f"[MovieEngine] ✅ Full Movie Recap Script complete: {len(grounded_segments)} segments saved to {output_script_path}!")
        return output_script_path

    def _factual_verify_segments(self, segments: list, film_synopsis: str, story_state: any = None) -> list:
        """
        Claim-Level Independent Factual Verification Layer (Improvement #5).
        Decomposes each narration segment into individual atomic claims:
          Example: "Alice discovers the hidden account, confronts her husband, and learns he lied."
          -> Claim 1: "Alice discovers hidden account" (verified / unsupported / contradicted)
          -> Claim 2: "Alice confronts husband" (verified / unsupported / contradicted)
          -> Claim 3: "He has been lying" (verified / unsupported / contradicted)

        Evaluates against:
          1. The actual matched source dialogue (primary local evidence)
          2. The Film Synopsis (overall plot reference)
          3. The persistent EvidenceStore / story state

        Outputs explicit per-segment audit metadata:
          claims: list of {"claim": str, "status": str, "evidence": str}
          factual_status: 'verified' | 'partially_supported' | 'unsupported' | 'contradicted' | 'needs_visual_check'
          factually_verified: bool (True ONLY if 'verified' — partially_supported is NOT treated as fully verified)
          character_accuracy: bool (names, roles, relationships correct)
          claim_vs_fact_separated: bool (subjective accusations are framed as claims, not facts)
          factual_notes: str (concise explanation of discrepancies or evidence)
        """
        if not segments:
            return []

        # If no provider or synopsis, default to unverified (do not pretend to succeed)
        if not self.provider:
            for s in segments:
                s["claims"] = []
                s["factual_status"] = "unverified"
                s["factually_verified"] = False
                s["factual_notes"] = "No LLM provider available for factual verification."
            return segments

        # Process in compact adaptive batches of 10 segments (keeps batch prompt ~1,400 tokens)
        batch_size = 10
        verified_segments = []

        # Prepare story context string from EvidenceStore or dict
        story_context = ""
        if isinstance(story_state, EvidenceStore):
            story_context = story_state.format_source_state_for_prompt(max_tokens=300)
        elif isinstance(story_state, dict):
            chars = story_state.get("characters", {})
            facts = story_state.get("confirmed_facts", [])[-4:]
            claims = story_state.get("character_claims", [])[-3:]
            story_context = (
                f"Known Characters: {json.dumps(dict(list(chars.items())[:6]), ensure_ascii=False)}\n"
                f"Established Facts: {json.dumps(facts, ensure_ascii=False)}\n"
                f"Unverified Character Claims: {json.dumps(claims, ensure_ascii=False)}"
            )

        for b_idx in range(0, len(segments), batch_size):
            batch = segments[b_idx:b_idx + batch_size]
            batch_num = (b_idx // batch_size) + 1
            total_batches = (len(segments) + batch_size - 1) // batch_size
            items_for_prompt = []
            for s in batch:
                sid = s.get("id")
                narration = s.get("narration") or s.get("english") or s.get("text") or ""
                ts = s.get("movie_timestamp", "00:00:00")
                src = s.get("source_dialogue") or "(No dialogue at this timestamp)"
                items_for_prompt.append(
                    f"Segment ID {sid} [{ts}]:\n"
                    f"  - Narration: \"{narration}\"\n"
                    f"  - Source Dialogue Evidence: \"{src[:140]}\""
                )

            prompt_content = "\n".join(items_for_prompt)

            user_prompt = f"""You are a strict movie factual verification auditor.
Deconstruct each narration segment below into 1 to 3 atomic factual claims (actions, revelations, relationships).
Verify EACH claim independently against the Source Dialogue Evidence and Synopsis.

Film Synopsis (reference):
{film_synopsis[:1500]}

{story_context}

Segments to Verify:
{prompt_content}

For each segment ID, output:
- id: integer
- claims: list of objects:
    - claim: string (concise atomic assertion)
    - status: "verified" | "partially_supported" | "unsupported" | "contradicted" | "needs_visual_check"
    - evidence: string (supporting quote or reason for status)
- factual_status: one of "verified" | "partially_supported" | "unsupported" | "contradicted" | "needs_visual_check"
  (Rules: If ANY claim is contradicted -> "contradicted". If ALL claims verified -> "verified". If mix of supported and unsupported -> "partially_supported". If no dialogue evidence -> "unsupported" or "needs_visual_check".)
- character_accuracy: boolean
- claim_vs_fact_separated: boolean (are subjective accusations framed as claims rather than established facts?)
- factual_notes: 1 concise sentence explaining any discrepancy.

Return JSON with key 'verifications': list of objects."""

            try:
                resp = self.provider.chat_completion(
                    system_prompt="You are an uncompromising, claim-level factual verification auditor. Output strict JSON with key 'verifications'.",
                    user_content=user_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=1500,
                    stage_label=f"factual_verification_batch_{batch_num}_of_{total_batches}"
                )
                data = json.loads(resp)
                ver_map = {v["id"]: v for v in data.get("verifications", []) if "id" in v}
            except Exception as e:
                print(f"  [MovieEngine] ⚠️ Factual verification batch notice: {e}")
                ver_map = {}

            for s in batch:
                sid = s.get("id")
                v_res = ver_map.get(sid, {})
                claims = v_res.get("claims", [])
                s["claims"] = claims

                status = v_res.get("factual_status", "unverified")
                # Rule-based reconciliation from claims:
                if claims:
                    statuses = [c.get("status", "") for c in claims]
                    if "contradicted" in statuses:
                        status = "contradicted"
                    elif all(st == "verified" for st in statuses):
                        status = "verified"
                    elif any(st in ("verified", "partially_supported") for st in statuses) and any(st in ("unsupported", "needs_visual_check") for st in statuses):
                        status = "partially_supported"

                s["factual_status"] = status
                # Strict: ONLY fully verified counts as factually_verified
                s["factually_verified"] = (status == "verified")
                s["character_accuracy"] = bool(v_res.get("character_accuracy", True))
                s["claim_vs_fact_separated"] = bool(v_res.get("claim_vs_fact_separated", True))
                s["factual_notes"] = v_res.get("factual_notes", "")
                verified_segments.append(s)

        v_count = sum(1 for s in verified_segments if s.get("factually_verified"))
        print(f"  [MovieEngine] 🔬 Factual Verification: {v_count}/{len(verified_segments)} segments 100% verified by evidence.")
        return verified_segments

    @staticmethod
    def _ground_and_verify_timestamps(
        raw_segments: list,
        dialogues: list,
        total_runtime_sec: float,
        target_lang: str,
        movie_path: str = None,
        timeline_cursor_start: float = 0.0,
        last_verified_sec_start: float = 0.0,
        start_id: int = 1,
        precomputed_clusters: list = None,
        precomputed_embeddings = None
    ) -> list:
        """
        Locks each script segment's movie_timestamp to the most likely position in the subtitle
        timeline using SemanticAligner vector embeddings.
        Supports Incremental Grounding (Improvement #7) and Top-3 Candidate Ranking (Improvement #6).

        Output fields:
          narration             — the generated voiceover sentence (this is what gets spoken)
          source_dialogue       — actual subtitle text from the matched dialogue cluster (evidence)
          anchor_quote          — the anchor phrase used for alignment
          movie_timestamp       — HH:MM:SS position in the actual movie (from dialogue timeline)
          raw_matched_timestamp — HH:MM:SS original matched timestamp before chronological adjustment
          candidate_timestamps — list of top-3 candidate matches with full score decomposition
          start / end           — position in the generated narration audio timeline (not the movie)
          alignment_confidence  — 'high' / 'medium' / 'low' based on combined_score
          timestamp_verified    — True if match was within the temporal window and score >= 0.35
          timestamp_warning     — human-readable note when alignment is uncertain
        """
        from core.translator import StoryTranslator
        from core.semantic_aligner import SemanticAligner

        def parse_to_sec(ts_str: str) -> float:
            try:
                parts = str(ts_str).replace(",", ".").split(":")
                if len(parts) == 3:
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    return float(parts[0]) * 60 + float(parts[1])
                return float(ts_str)
            except Exception:
                return 0.0

        def fmt_sec(secs: float) -> str:
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        aligner = SemanticAligner()

        # 1. Use pre-computed clusters and embeddings if provided (Incremental Grounding optimization)
        if precomputed_clusters is not None and precomputed_embeddings is not None:
            clusters = precomputed_clusters
            all_cluster_embeddings = precomputed_embeddings
        else:
            clusters = []
            curr_cluster = []
            curr_start = 0.0
            curr_end = 0.0

            for d in dialogues:
                st = float(d.get("start", 0.0))
                et = float(d.get("end", st + 2.0))
                txt = d.get("text", "").strip()
                if not txt:
                    continue
                if not curr_cluster or (st - curr_start <= 25.0):
                    if not curr_cluster:
                        curr_start = st
                    curr_cluster.append(txt)
                    curr_end = et
                else:
                    clusters.append({
                        "start": curr_start,
                        "end": curr_end,
                        "text": " ".join(curr_cluster)
                    })
                    curr_cluster = [txt]
                    curr_start = st
                    curr_end = et

            if curr_cluster:
                clusters.append({
                    "start": curr_start,
                    "end": curr_end,
                    "text": " ".join(curr_cluster)
                })

            all_cluster_embeddings = aligner.precompute_cluster_embeddings(clusters)

        processed = []
        timeline_cursor = timeline_cursor_start
        last_verified_sec = last_verified_sec_start

        for i, s in enumerate(raw_segments):
            narration = s.get("text") or s.get("narration") or ""
            if not narration:
                continue

            clean_text = StoryTranslator.sanitize_segment_text(narration, target_language=target_lang)
            anchor_quote = s.get("anchor_quote") or ""
            raw_time_str = s.get("time") or s.get("movie_timestamp") or ""
            raw_time_sec = parse_to_sec(raw_time_str)
            scene_loc = s.get("loc") or s.get("scene_location") or "Unknown Location"
            is_sc = bool(s.get("scene_change") if "scene_change" in s else s.get("is_scene_change", False))

            b_st = s.get("_block_start", 0.0)
            b_et = s.get("_block_end", total_runtime_sec)

            # Check for flashback / non-linear timeline markers BEFORE filtering candidate clusters
            is_flashback = bool(
                s.get("is_flashback", False) or
                (is_sc and re.search(
                    r'\b(flash[\s-]?back|flash[\s-]?forward|earlier|years?\s+ago|months?\s+ago|'
                    r'days?\s+ago|previously|returning\s+to|back\s+in\s+time|meanwhile|'
                    r'in\s+the\s+past|before\s+this|looking\s+back)\b',
                    clean_text, flags=re.IGNORECASE
                )) or
                (raw_time_sec > 0 and raw_time_sec < (b_st - 60.0))
            )

            if is_flashback or not clusters:
                block_clusters = clusters
                block_embs = all_cluster_embeddings
            else:
                block_cluster_indices = [
                    j for j, c in enumerate(clusters)
                    if (b_st - 45.0) <= c["start"] <= (b_et + 45.0)
                ]
                if not block_cluster_indices:
                    block_clusters = clusters
                    block_embs = all_cluster_embeddings
                else:
                    block_clusters = [clusters[j] for j in block_cluster_indices]
                    block_embs = all_cluster_embeddings[block_cluster_indices]

            match_res = aligner.match_best_dialogue_cluster(
                narration_text=clean_text,
                dialogue_clusters=block_clusters,
                anchor_quote=anchor_quote,
                expected_time_sec=raw_time_sec,
                temporal_window_sec=240.0 if is_flashback else 180.0,
                precomputed_embeddings=block_embs
            )

            timestamp_verified = False
            timestamp_warning = ""
            alignment_confidence = "low"
            source_dialogue_text = ""

            if match_res:
                combined = match_res.get("combined_score", 0.0)
                cosine = match_res.get("cosine_similarity", 0.0)
                within_window = match_res.get("within_temporal_window", False)
                fallback = match_res.get("fallback_to_full_movie", False)

                if combined > 0.35 and within_window:
                    final_movie_sec = match_res["timestamp"]
                    timestamp_verified = True
                    source_dialogue_text = match_res.get("cluster", {}).get("text", "")
                    if combined >= 0.55:
                        alignment_confidence = "high"
                    elif combined >= 0.40:
                        alignment_confidence = "medium"
                    else:
                        alignment_confidence = "low"
                elif combined > 0.28 and not fallback:
                    final_movie_sec = match_res["timestamp"]
                    timestamp_warning = f"Weak alignment (combined={combined:.3f}, cosine={cosine:.3f}). Narration accuracy unverified."
                    source_dialogue_text = match_res.get("cluster", {}).get("text", "")
                    alignment_confidence = "low"
                elif fallback:
                    timestamp_warning = "No candidate within temporal window. Fell back to full-movie search — timestamp may be incorrect."
                    if raw_time_sec > 0:
                        final_movie_sec = raw_time_sec
                    else:
                        final_movie_sec = max(b_st, last_verified_sec + 3.0)
                else:
                    final_movie_sec = raw_time_sec if raw_time_sec > 0 else max(b_st, last_verified_sec + 3.0)
                    timestamp_warning = f"Alignment score too low (combined={combined:.3f}). Using LLM-suggested timestamp."
            else:
                final_movie_sec = raw_time_sec if raw_time_sec > 0 else max(b_st, last_verified_sec + 3.0)
                timestamp_warning = "No alignment result returned. Using LLM-suggested timestamp."

            # Preserve raw matched timestamp BEFORE any chronological adjustments (Improvement #6.B)
            raw_matched_sec = match_res["timestamp"] if match_res else final_movie_sec
            raw_matched_ts = fmt_sec(raw_matched_sec)

            # Preserve top-3 candidate matches (Improvement #6.A)
            candidate_matches = []
            if match_res and match_res.get("candidates"):
                for cand in match_res["candidates"]:
                    candidate_matches.append({
                        "timestamp": fmt_sec(cand["timestamp"]),
                        "timestamp_sec": cand["timestamp"],
                        "combined_score": cand["combined_score"],
                        "cosine_similarity": cand["cosine_similarity"],
                        "anchor_score": cand["anchor_score"],
                        "temporal_penalty": cand["temporal_penalty"],
                        "text": cand.get("text", "")[:90]
                    })

            # Monotonic guarantee with flashback exception
            backwards_jump = False

            if final_movie_sec < last_verified_sec and not is_flashback:
                diff = last_verified_sec - final_movie_sec
                if diff <= 45.0:
                    final_movie_sec = last_verified_sec + 2.0
                    backwards_jump = True
                    if not timestamp_warning:
                        timestamp_warning = f"Matched timestamp ({raw_matched_ts}) was {diff:.1f}s before previous scene — chronologically adjusted to {fmt_sec(final_movie_sec)}."
                    else:
                        timestamp_warning += f" Additionally, matched timestamp was {diff:.1f}s before previous segment."
                    timestamp_verified = False
                else:
                    old_sec = final_movie_sec
                    final_movie_sec = min(b_et, last_verified_sec + 3.0)
                    backwards_jump = True
                    timestamp_warning = (
                        f"Matched timestamp ({fmt_sec(old_sec)}) is {diff:.1f}s before previous segment "
                        f"({fmt_sec(last_verified_sec)}) — large backwards jump flagged. Set to {fmt_sec(final_movie_sec)}."
                    )
                    timestamp_verified = False
            elif final_movie_sec < last_verified_sec and is_flashback:
                timestamp_warning = f"Intentional flashback: timestamp {fmt_sec(final_movie_sec)} is before previous scene {fmt_sec(last_verified_sec)}."
                if match_res and match_res.get("combined_score", 0.0) > 0.35:
                    timestamp_verified = True

            final_movie_sec = max(0.0, min(total_runtime_sec - 5.0, final_movie_sec))

            if is_sc and movie_path and os.path.exists(movie_path):
                final_movie_sec = SemanticAligner.snap_to_nearest_keyframe(movie_path, final_movie_sec)

            if not is_flashback:
                last_verified_sec = max(last_verified_sec, final_movie_sec)

            word_count = max(1, len(clean_text.split()))
            est_dur = round(max(3.8, min(7.5, word_count / 2.3)), 2)

            curr_id = start_id + i

            entry = {
                "id": curr_id,
                "start": round(timeline_cursor, 2),
                "end": round(timeline_cursor + est_dur, 2),
                "duration_sec": est_dur,
                "movie_timestamp": fmt_sec(final_movie_sec),
                "raw_matched_timestamp": raw_matched_ts,
                "candidate_timestamps": candidate_matches,
                "narration": clean_text,
                "source_dialogue": source_dialogue_text,
                "anchor_quote": anchor_quote,
                "scene_location": scene_loc,
                "is_scene_change": is_sc,
                "alignment_confidence": alignment_confidence,
                "timestamp_verified": timestamp_verified,
                "_block_start": b_st,
                "_block_end": b_et,
            }
            if timestamp_warning:
                entry["timestamp_warning"] = timestamp_warning
            if backwards_jump:
                entry["backwards_jump_detected"] = True
            if is_flashback:
                entry["is_flashback"] = True

            entry[target_lang.lower()] = clean_text

            processed.append(entry)
            timeline_cursor += est_dur

        return processed
