import os
import json
import re
import subprocess
import shutil
from dotenv import load_dotenv
from core.providers import GroqProvider

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
    def _condense_dialogue_block(condensed_log: list, max_lines: int = 160) -> str:
        """
        Condenses a dialogue block to at most max_lines entries while preserving
        narrative-critical information.

        Strategy:
        - Always keep short lines (≤ 12 words) — likely single-line revelations, identity
          statements, decisions, and twists.
        - Remove consecutive duplicate lines before sampling.
        - Use a uniform stride for the remaining lines but prefer lines not already included.

        This replaces naive even-sampling which can discard critical one-line events.
        """
        if len(condensed_log) <= max_lines:
            return "\n".join(condensed_log)

        # Identify high-importance lines: short, likely key dialogue
        important_indices = set()
        for i, line in enumerate(condensed_log):
            # Strip the [HH:MM:SS] timestamp prefix before counting words
            text_part = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line)
            if len(text_part.split()) <= 12:
                important_indices.add(i)

        # De-duplicate adjacent identical lines
        deduped = []
        prev_text = None
        for i, line in enumerate(condensed_log):
            text_part = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', line).lower().strip()
            if text_part != prev_text:
                deduped.append((i, line))
                prev_text = text_part

        # Always include important short lines (up to max_lines / 2 slots)
        important_lines = [(i, l) for i, l in deduped if i in important_indices]
        budget_important = min(len(important_lines), max_lines // 2)
        selected_important = set(i for i, _ in important_lines[:budget_important])

        # Fill remaining slots with evenly-spaced non-important lines
        remaining_budget = max_lines - len(selected_important)
        non_important = [(i, l) for i, l in deduped if i not in selected_important]
        if non_important and remaining_budget > 0:
            step = max(1, len(non_important) / remaining_budget)
            sampled_non_important = {non_important[int(j * step)][0] for j in range(remaining_budget) if int(j * step) < len(non_important)}
        else:
            sampled_non_important = set()

        # Merge and sort by original position to preserve chronology
        all_selected = selected_important | sampled_non_important
        result_lines = [line for i, line in enumerate(condensed_log) if i in all_selected]
        # Sort by index (enumerate from condensed_log to get original order)
        ordered = sorted(
            [(i, condensed_log[i]) for i in all_selected],
            key=lambda x: x[0]
        )
        return "\n".join(line for _, line in ordered)

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

    def _update_story_state(self, story_state: dict, act_segs: list, block_title: str) -> dict:
        """
        Asks the LLM to extract structured story-state updates from the just-generated block.
        Updates the story_state dict in-place and returns it.
        """
        if not act_segs:
            return story_state

        narration_block = "\n".join(f"- {s.get('text', '')}" for s in act_segs if s.get("text"))
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
                max_tokens=800
            )
            updates = json.loads(resp)

            # Merge updates into persistent state
            for name, role in updates.get("new_characters", {}).items():
                story_state["characters"][name] = role
            story_state["confirmed_facts"].extend(updates.get("confirmed_facts", []))
            story_state["character_claims"].extend(updates.get("character_claims", []))
            story_state["important_evidence"].extend(updates.get("new_evidence", []))

            # Remove resolved mysteries
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
    def _format_story_state_for_prompt(story_state: dict) -> str:
        """Formats the persistent story state into a human-readable prompt section."""
        lines = ["PERSISTENT STORY STATE (maintain continuity from previous blocks):"]

        chars = story_state.get("characters", {})
        if chars:
            lines.append("Known Characters:")
            for name, role in list(chars.items())[:15]:
                lines.append(f"  - {name}: {role}")

        facts = story_state.get("confirmed_facts", [])
        if facts:
            lines.append("Confirmed Facts (objective):")
            for f in facts[-10:]:
                lines.append(f"  - {f}")

        claims = story_state.get("character_claims", [])
        if claims:
            lines.append("Character Claims (not yet confirmed as fact):")
            for c in claims[-8:]:
                lines.append(f"  - {c}")

        mysteries = story_state.get("unresolved_mysteries", [])
        if mysteries:
            lines.append("Unresolved Mysteries (acknowledge but don't spoil):")
            for m in mysteries[-8:]:
                lines.append(f"  - {m}")

        evidence = story_state.get("important_evidence", [])
        if evidence:
            lines.append("Important Evidence Discovered:")
            for e in evidence[-8:]:
                lines.append(f"  - {e}")

        narrated = story_state.get("timeline_events_narrated", [])
        if narrated:
            lines.append("Already Narrated (avoid repetition):")
            for n in narrated[-5:]:
                lines.append(f"  - {n}")

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

        # Step 1: Fetch Plot Synopsis as a broad narrative reference
        print(f"  [MovieEngine] 🌐 Fetching film plot synopsis for '{movie_title}'...")
        film_synopsis = self._fetch_film_synopsis(movie_title)
        if film_synopsis:
            print(f"  [MovieEngine] ✅ Retrieved film plot synopsis ({len(film_synopsis)} chars). Used as broad reference — subtitle timeline is primary source.")
        else:
            print(f"  [MovieEngine] ℹ️ Online synopsis unavailable. Synthesizing plot outline from dialogue...")
            # Use importance-aware condensation even for the synopsis fallback
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
        try:
            block_samples = []
            for b_idx in range(block_count):
                b_st = b_idx * block_dur
                b_et = (b_idx + 1) * block_dur if b_idx < block_count - 1 else total_runtime_sec + 10.0
                d_win = [d for d in dialogues if b_st <= d['start'] < b_et]
                sample = [f"[{fmt_time(d['start'])}] {d['text'].strip()}" for d in d_win[::max(1, len(d_win) // 25)]][:25]
                block_samples.append(f"Block {b_idx + 1} [{fmt_time(b_st)} - {fmt_time(min(total_runtime_sec, b_et))}]:\n" + "\n".join(sample))

            ch_prompt = f"""You are a master story editor.
Divide the film plot synopsis of '{movie_title}' into exactly {block_count} non-overlapping, chronological chapter scopes matching the true dialogue events and physical story progression across each runtime window.

True Dialogue Snapshots per window:
{chr(10).join(block_samples)}

Film Plot Synopsis (reference — subtitle timeline is authoritative for scene-level events):
{film_synopsis}

CRITICAL RULES FOR CHAPTER SCOPES:
1. Match the chapter scope strictly to the true physical setting and dialogue events occurring in that specific runtime window.
2. DO NOT prematurely pull scenes or actions from future windows into earlier windows.
   - Ground the scope strictly in the locations, characters, and discoveries present in that chronological window.
   - Do not import events, discoveries, or physical confrontations that occur in subsequent windows.
3. NON-LINEAR & PARALLEL TIMELINES: If the film features flashbacks, flash-forwards, or parallel timelines (e.g. an investigation into a crime or fire shown out of order), explicitly identify these temporal shifts so the narrator uses natural time markers and avoids redundant re-narration.
4. CLIMAX & TWIST FIDELITY: For the final block (Block {block_count}), explicitly document the true climax, final identity reveal, and resolution as proven by the Synopsis and final dialogue beats (e.g. who arrives, what truth is uncovered, and whether the protagonist was validated or proven false/delusional).

Return JSON with key 'chapters' containing a list of {block_count} objects with 'block_index' (1 to {block_count}), 'title', and 'scope' (2-4 sentences describing the exact physical locations, character movements, evidence discovered, and action events occurring strictly in this window)."""

            ch_resp = self.provider.chat_completion(
                system_prompt="You are a master film story editor. Output strict JSON with key 'chapters'.",
                user_content=ch_prompt,
                response_format={"type": "json_object"},
                max_tokens=1500
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
                    "MANDATORY CLIMAX & TWIST RESOLUTION: The final segments of this block MUST explicitly deliver the true, verified climax and shocking resolution of THIS specific film as proven by the Film Synopsis and final dialogue beats.\n"
                    "CRITICAL TWIST FIDELITY: Carefully check the Film Synopsis for the true ending revelation. In psychological thrillers, verify whether the protagonist's conspiracy theory was validated OR disproved by the final discovery. Never assume the protagonist was right if the synopsis shows their claim was shattered or proven false. Accurately narrate the true physical reveal as verified in the synopsis."
                )
                guidance = f"{guidance}\n{twist_instructions}".strip()
            elif not guidance:
                guidance = f"Recap the key events, dramatic conflicts, and character actions occurring within the [{fmt_time(b_start)} - {fmt_time(min(total_runtime_sec, b_end))}] window."

            acts_data.append((block_title, b_dialogues, target_segs_per_block, guidance, is_final_climax, b_start, b_end))

        all_raw_segments = []
        # Persistent story state maintained across all blocks (replaces 3-sentence rolling_context)
        story_state = self._build_initial_story_state(movie_title)

        for act_name, act_dialogues, target_segments, act_guidance, is_final_climax, b_start, b_end in acts_data:
            if not act_dialogues:
                continue

            print(f"  [MovieEngine] ✍️ Generating {act_name} (~{target_segments} voiceover beats)...")
            
            condensed_log = [
                f"[{fmt_time(d['start'])}] {d['text'].strip()}"
                for d in act_dialogues
            ]

            # Importance-aware condensation: preserve short/critical lines, avoid naive sampling
            sampled_dialogue_text = self._condense_dialogue_block(condensed_log, max_lines=160)

            system_prompt = f"""You are an elite YouTube movie recap script doctor and voiceover director for top channels (e.g. Mystery Recapped, Movie Recaps).
Your mission is to transform the provided raw chronological movie dialogue into a viral, high-retention YouTube Movie Recap narration script in spoken {target_lang.upper()}.

FILM PLOT SYNOPSIS (broad narrative reference — subtitle dialogue timeline is primary for scene-level events):
{film_synopsis}

CRITICAL PRODUCTION & NARRATIVE CONTINUITY RULES:
1. PUNCHY, CONVERSATIONAL 3RD-PERSON NARRATOR (YOUTUBE EXPLAINER STYLE):
   - Narrate in simple, clear, conversational third person ("The detective investigates", "The doctor questions the director", "Alice realizes the trap"). Never use first person ("I", "my").
   - Tone should sound like an engaging storyteller explaining a suspenseful movie to a friend, NOT a formal police report or purple-prose novel.
   - Summarize the story cleanly; explain characters' motivations, conflicting clues, and why things happen.

2. SOURCE-TO-DESCRIPTION ACCURACY & DIALOGUE GROUNDING:
   - For every segment, base the narration strictly on the actual event, dialogue, or physical action occurring at that timestamp in the dialogue timeline.
   - Do NOT move information from a later scene into an earlier timestamp.
   - Do NOT combine multiple unrelated events into one description.
   - Do NOT replace an actual event with an assumption about what probably happened.
   - Do NOT add actions that cannot be established from the available source dialogue or verified synopsis.

3. SEPARATE FACTS, CLAIMS, AND INFERENCES:
   - Every important statement must be clearly classified:
     * Direct Fact: Confirmed on-screen or unquestioned.
     * Claim / Accusation: Clearly state who claims or alleges it ("Alice claims...", "Alvar insists...", "Staff allege...").
     * Inference / Suspicion: Clearly frame as thought or suspicion ("She suspects...").
   - NEVER present an unverified character accusation or theory as an objective factual reality early in the story.
   - In psychological thrillers, ALWAYS preserve the deliberate uncertainty between competing explanations.

4. LANGUAGE SIMPLICITY & NATURAL CONVERSATIONAL VOCABULARY:
   - Use everyday English. Prefer common, punchy words over complicated vocabulary.
   - FORBIDDEN OVERCOMPLICATED JARGON: Do NOT use phrases like "orthodox Freudian concepts", "deep-seated paranoid delusions", "forensic inconsistencies", "clinical discharge", "predatory suitors", "legal incapacitation", or "disciplinary punishment". Use simple alternatives: "traditional psychology ideas", "false beliefs", "differences in the medical reports", "official release", "men after her wealth", or "punishment from the staff".
   - Avoid dramatic adverb clutter: NEVER spam words like "fearlessly", "fiercely", "brilliantly", "maliciously", "arrogantly", or "contemptuously". Let the real events create suspense naturally.

5. NON-LINEAR & DUAL-TIMELINE CLARITY (CRITICAL FOR FILMS WITH FLASHBACKS/FLASH-FORWARDS):
   - If an event is a flash-forward, flashback, or secondary parallel timeline shown out of order, you MUST use clear conversational time markers:
     "In a flash-forward to a stormy night...", "Flash-forward reveals the aftermath of a violent fire...", "Returning to the main timeline...".
   - When the main timeline later reaches that same event, clearly connect it: "This fire connects back to the chaotic aftermath shown earlier."
   - Never narrate a flash-forward as if it is happening in the current sequence without identifying the time jump, and never duplicate scenes without explanation.

6. STRICT FILM ISOLATION & ZERO HALLUCINATION:
   - Ground all characters, locations, clues, and twists STRICTLY in the provided dialogue and Film Plot Synopsis of THIS specific film.
   - ABSOLUTE PROHIBITION: NEVER import character names, car trunks, bodies in pits, or plot points from other movies.

7. STRICT CAUSALITY & PHYSICAL ACTION TRANSIT (NO INVENTED TRANSITIONS):
   - When characters change locations, escape confinement, or travel, explicitly narrate the physical transition beat.
   - Connect clues directly to revelations so events feel continuous, never like disjointed incidents.
   - Do not invent actions or conversations that do not happen in the source.

8. ENTITY & CHARACTER ARRIVAL GROUNDING:
   - Introduce new characters with their name, role, and reason for being there BEFORE they interact.
   - Accurately track character identities and relationships (e.g., distinguishing between twin brothers, identifying who survives and who dies).

9. SEAMLESS NARRATIVE BRIDGES (ABSOLUTELY NO META-PHRASES):
   - FORBIDDEN META-PHRASES: NEVER use "In this scene we see", "Cut to", "The scene shifts to", "We are shown", "The camera pans", "Here we observe".

10. STRICT 1-SENTENCE CADENCE (10 TO 16 WORDS PER SEGMENT):
    - Every single segment MUST be EXACTLY ONE single concise standalone sentence.
    - Word count MUST be strictly between 10 and 16 words per segment.
    - Ending strictly with terminal punctuation: period (.), exclamation (!), or question mark (?).
    - NEVER end on trailing conjunctions ('and', 'because', 'so', 'to', 'who').

11. TWIST & FINAL REVELATION FIDELITY (ANTI-BIAS GROUNDING):
    - In the final story block, faithfully report the true ending resolution documented in the Film Synopsis.
    - If the synopsis reveals that the protagonist was mistaken, delusional, or that a trusted visitor turns out to be someone else, narrate that exact revelation with emotional impact. NEVER invert the twist or default to generic tropes where the protagonist is proven completely right if the synopsis states otherwise.
    - Accurately report official votes, decisions, and acquittals (e.g., clarifying when doctors vote to release a patient while an official abstains).

12. ANCHOR DIALOGUE GROUNDING FOR ACCURATE VIDEO SYNC:
    - For every segment, provide an "anchor_quote": a short 3-8 word phrase from characters in or adjacent to this scene to lock the video cut with frame-accuracy.

13. OUTPUT FORMAT (COMPACT JSON):
    - Return valid JSON with a single key 'segments'. Each segment object MUST have:
      "text": The spoken voiceover narration (strictly 10-16 words, 1 standalone sentence, simple conversational English).
      "anchor_quote": A short 3-8 word quote from character dialogue in this scene.
      "time": The approximate timestamp string (HH:MM:SS) from the dialogue log where this scene occurs.
      "loc": Short name of the scene location.
      "scene_change": Boolean (true if this segment transitions to a new scene, time, or location).
"""

            story_state_prompt = self._format_story_state_for_prompt(story_state)

            user_prompt = f"""Film: {movie_title}
Act / Window: {act_name}
Target Segments to produce: approximately {target_segments} segments (each EXACTLY 1 single standalone sentence, 10-16 words).

STRICT CHAPTER SCOPE (FOCUS EXCLUSIVELY ON THESE EVENTS):
{act_guidance}
(CRITICAL: You MUST narrate ONLY the events occurring within this chapter window. DO NOT jump ahead to future events or reveal future plot developments!).

{story_state_prompt}

Chronological Movie Dialogue Timeline:
{sampled_dialogue_text}

SOURCE ACCURACY INSTRUCTIONS:
- Generate descriptions chronologically following the dialogue events above.
- Strictly distinguish verified physical facts from character claims/allegations.
- Ensure each segment is strictly 10 to 16 words and exactly one standalone sentence.
"""

            resp = self.provider.chat_completion(
                system_prompt=system_prompt,
                user_content=user_prompt,
                response_format={"type": "json_object"},
                max_tokens=1500
            )

            try:
                data = json.loads(resp)
                act_segs = data.get("segments", [])
            except Exception as parse_err:
                print(f"  [MovieEngine] Warning parsing act response ({parse_err}). Falling back.")
                act_segs = []

            # Deduplicate boundary segments if model repeated previous segment
            if all_raw_segments and act_segs:
                prev_clean = re.sub(r'[^a-z0-9]', '', (all_raw_segments[-1].get("text") or "").lower())
                first_clean = re.sub(r'[^a-z0-9]', '', (act_segs[0].get("text") or "").lower())
                if prev_clean and first_clean and (prev_clean == first_clean or prev_clean[:25] == first_clean[:25]):
                    act_segs.pop(0)

            for s in act_segs:
                s["_block_start"] = b_start
                s["_block_end"] = b_end
                all_raw_segments.append(s)

            # Update persistent story state from this block's narration
            story_state = self._update_story_state(story_state, act_segs, act_name)

            # ── Real-Time Incremental Flush to Disk ──
            try:
                partial_grounded = self._ground_and_verify_timestamps(
                    all_raw_segments, dialogues, total_runtime_sec, target_lang, movie_path=movie_path
                )
                temp_flush_path = output_script_path + ".tmp"
                with open(temp_flush_path, "w", encoding="utf-8") as tf:
                    json.dump(partial_grounded, tf, indent=4, ensure_ascii=False)
                os.replace(temp_flush_path, output_script_path)
                print(f"  [MovieEngine] 💾 Real-Time Sync: Flushed {len(partial_grounded)} segments ({act_name}) directly to disk.")
            except Exception as flush_err:
                print(f"  [MovieEngine] ⚠️ Real-time flush notice: {flush_err}")

        # ─────────────────────────────────────────────────────────────────
        # STEP 4: PROGRAMMATIC GROUNDING & ANCHOR VERIFICATION (NO HALLUCINATIONS)
        # ─────────────────────────────────────────────────────────────────
        print(f"\n[MovieEngine] 🔍 Grounding & Auto-Verifying {len(all_raw_segments)} segments against studio subtitle timeline...")
        grounded_segments = self._ground_and_verify_timestamps(all_raw_segments, dialogues, total_runtime_sec, target_lang, movie_path=movie_path)

        # ─────────────────────────────────────────────────────────────────
        # STEP 4.5: INDEPENDENT FACTUAL VERIFICATION
        # Compares each narration segment against its matched source dialogue to check
        # whether the described event is actually supported by the evidence.
        # This is separate from timestamp alignment — alignment finds WHERE in the movie
        # the narration belongs; factual verification checks WHETHER the narration is accurate.
        # ─────────────────────────────────────────────────────────────────
        print(f"\n[MovieEngine] 🔬 Running independent factual verification on {len(grounded_segments)} segments...")
        grounded_segments = self._factual_verify_segments(grounded_segments, film_synopsis, story_state)

        # ─────────────────────────────────────────────────────────────────
        # STEP 5: AUTOMATED SCRIPT AUDITOR & GENERIC QUALITY ELEVATION (TARGET >= 9.5)
        # NOTE: A passing score means language rules pass and the LLM approved against
        # the synopsis. It does NOT guarantee per-segment factual accuracy against the
        # dialogue timeline. See timestamp_verified / alignment_confidence fields for that.
        # ─────────────────────────────────────────────────────────────────
        from core.script_auditor import ScriptAuditor
        for audit_round in range(1, 5):
            audit_report = ScriptAuditor.audit_script(grounded_segments, film_synopsis=film_synopsis, provider=self.provider)
            score = audit_report.get("overall_score", 0.0)
            audit_ok = audit_report.get("audit_success", False)
            print(f"\n  [ScriptAuditor] 📊 Round {audit_round} Quality Audit: {score}/10.0 (Target: 9.5+, Certified: {audit_ok})")
            for cat, c_score in audit_report.get("category_scores", {}).items():
                print(f"    - {cat}: {c_score}/10.0")

            if score >= 9.5 and audit_ok:
                print(f"  [ScriptAuditor] 🏆 SCRIPT QUALITY CERTIFIED (Score {score}/10.0 >= 9.5)!")
                break
            else:
                print(f"  [ScriptAuditor] 🛠️ Applying generic polish and surgical adjustments...")
                polished_segments = ScriptAuditor.apply_generic_polish(
                    grounded_segments, 
                    provider=self.provider, 
                    film_synopsis=film_synopsis, 
                    audit_report=audit_report,
                    dialogues=dialogues
                )

                # Issue #7 fix: After polishing rewrites narration text, timestamps and
                # source_dialogue may be stale. Re-run alignment for segments that were
                # actually modified so their timestamps and source evidence stay accurate.
                rewritten_raw = []
                for seg in polished_segments:
                    new_text = ScriptAuditor._get_narration_text(seg)
                    old_text = seg.get("_pre_polish_narration", "")
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

                # Re-ground all segments to refresh timestamps and source_dialogue
                grounded_segments = self._ground_and_verify_timestamps(
                    rewritten_raw, dialogues, total_runtime_sec, target_lang, movie_path=movie_path
                )
                # Re-run factual verification on the refreshed segments
                grounded_segments = self._factual_verify_segments(grounded_segments, film_synopsis, story_state)

        # Final audit pass to record official certified rating
        final_report = ScriptAuditor.audit_script(grounded_segments, film_synopsis=film_synopsis, provider=self.provider)
        final_score = final_report.get("overall_score", 0.0)
        final_ok = final_report.get("audit_success", False)
        final_passed = final_report.get("passed", False)
        print(f"\n  [ScriptAuditor] 🏁 Final Certified Score: {final_score}/10.0 (Audit Success: {final_ok}, Passed: {final_passed})")
        for cat, c_score in final_report.get("category_scores", {}).items():
            print(f"    - {cat}: {c_score}/10.0")

        # Gate output: if the script didn't pass audit, save as needs_review instead of
        # silently overwriting a potentially good cached script with a bad one.
        if not final_passed:
            review_path = output_script_path.replace(".json", "_needs_review.json")
            with open(review_path, "w", encoding="utf-8") as f:
                json.dump(grounded_segments, f, indent=4, ensure_ascii=False)
            report_path = output_script_path.replace(".json", "_audit_report.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(final_report, f, indent=4, ensure_ascii=False)
            print(
                f"\n[MovieEngine] ⚠️ Script did NOT pass quality audit ({final_score}/10.0 < 9.5 or audit failed). "
                f"Saved to {review_path} and audit report to {report_path}."
            )
            # Still save to main path so downstream pipeline has something to work with,
            # but log a clear warning that this script needs human review.
            with open(output_script_path, "w", encoding="utf-8") as f:
                json.dump(grounded_segments, f, indent=4, ensure_ascii=False)
            print(f"[MovieEngine] ⚠️ Also saved to {output_script_path} — REQUIRES MANUAL REVIEW before publishing.")
        else:
            with open(output_script_path, "w", encoding="utf-8") as f:
                json.dump(grounded_segments, f, indent=4, ensure_ascii=False)
            print(f"[MovieEngine] ✅ Full Movie Recap Script complete: {len(grounded_segments)} segments saved to {output_script_path}!")
        return output_script_path

    def _factual_verify_segments(self, segments: list, film_synopsis: str, story_state: dict = None) -> list:
        """
        Independent Factual Verification Layer (Issue 1):
        Compares each narration segment against:
          1. The actual matched source dialogue (primary local evidence)
          2. The Film Synopsis (overall plot reference)
          3. The persistent story state (characters, confirmed facts, unverified claims)

        Outputs explicit per-segment audit metadata:
          factual_status: 'verified' | 'partially_supported' | 'unsupported' | 'contradicted' | 'needs_visual_check'
          factually_verified: bool (True only if 'verified' or 'partially_supported')
          character_accuracy: bool (names, roles, relationships correct)
          claim_vs_fact_separated: bool (subjective accusations are framed as claims, not facts)
          factual_notes: str (concise explanation of discrepancies or evidence)

        CRITICAL: timestamp_verified (from alignment) and factually_verified are COMPLETELY SEPARATE.
        A matching timestamp does not mean the narration accurately describes what happened.
        """
        if not segments:
            return []

        # If no provider or synopsis, default to unverified (do not pretend to succeed)
        if not self.provider:
            for s in segments:
                s["factual_status"] = "unverified"
                s["factually_verified"] = False
                s["factual_notes"] = "No LLM provider available for factual verification."
            return segments

        # Process in batches of 15 segments for fast, reliable verification without truncation
        batch_size = 15
        verified_segments = []

        # Prepare story context string
        story_context = ""
        if story_state:
            chars = story_state.get("characters", {})
            facts = story_state.get("confirmed_facts", [])[-6:]
            claims = story_state.get("character_claims", [])[-6:]
            story_context = (
                f"Known Characters: {json.dumps(chars, ensure_ascii=False)}\n"
                f"Established Facts: {json.dumps(facts, ensure_ascii=False)}\n"
                f"Unverified Character Claims: {json.dumps(claims, ensure_ascii=False)}"
            )

        for b_idx in range(0, len(segments), batch_size):
            batch = segments[b_idx:b_idx + batch_size]
            items_for_prompt = []
            for s in batch:
                sid = s.get("id")
                narration = s.get("narration") or s.get("english") or s.get("text") or ""
                ts = s.get("movie_timestamp", "00:00:00")
                src = s.get("source_dialogue") or "(No dialogue at this timestamp)"
                items_for_prompt.append(
                    f"Segment ID {sid} [{ts}]:\n"
                    f"  - Narration: \"{narration}\"\n"
                    f"  - Source Dialogue Evidence: \"{src}\""
                )

            prompt_content = "\n".join(items_for_prompt)

            user_prompt = f"""You are a strict, independent movie factual verification auditor.
Verify each narration segment below against:
1. The Source Dialogue Evidence matched at that specific timestamp
2. The Film Synopsis
3. The Story Context (characters, confirmed facts vs subjective claims)

Film Synopsis:
{film_synopsis[:4000]}

{story_context}

Segments to Verify:
{prompt_content}

For each segment ID, output:
- id: integer
- factual_status: one of:
    * "verified" (The action/discovery is directly supported by dialogue or synopsis)
    * "partially_supported" (The event is plausible and mostly confirmed, with minor narrative inference)
    * "unsupported" (The claim has NO evidence in dialogue or synopsis at this point)
    * "contradicted" (The narration directly contradicts the dialogue or true movie plot)
    * "needs_visual_check" (A silent physical action that dialogue cannot confirm)
- character_accuracy: boolean (true if all character names, roles, and identities are accurate)
- claim_vs_fact_separated: boolean (true if subjective character allegations are stated as claims, NOT objective facts)
- factual_notes: 1 concise sentence explaining any discrepancy, missing evidence, or verification note.

Return JSON with key 'verifications': a list of objects."""

            try:
                resp = self.provider.chat_completion(
                    system_prompt="You are an uncompromising factual verification auditor. Output strict JSON with key 'verifications'.",
                    user_content=user_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=2000
                )
                data = json.loads(resp)
                ver_map = {v["id"]: v for v in data.get("verifications", []) if "id" in v}
            except Exception as e:
                print(f"  [MovieEngine] ⚠️ Factual verification batch notice: {e}")
                ver_map = {}

            for s in batch:
                sid = s.get("id")
                v_res = ver_map.get(sid, {})
                status = v_res.get("factual_status", "unverified")
                s["factual_status"] = status
                s["factually_verified"] = status in ("verified", "partially_supported")
                s["character_accuracy"] = bool(v_res.get("character_accuracy", True))
                s["claim_vs_fact_separated"] = bool(v_res.get("claim_vs_fact_separated", True))
                s["factual_notes"] = v_res.get("factual_notes", "")
                verified_segments.append(s)

        v_count = sum(1 for s in verified_segments if s.get("factually_verified"))
        print(f"  [MovieEngine] 🔬 Factual Verification: {v_count}/{len(verified_segments)} segments supported by evidence.")
        return verified_segments

    @staticmethod
    def _ground_and_verify_timestamps(raw_segments: list, dialogues: list, total_runtime_sec: float, target_lang: str, movie_path: str = None) -> list:
        """
        Locks each script segment's movie_timestamp to the most likely position in the subtitle
        timeline using SemanticAligner vector embeddings.

        Output fields:
          narration        — the generated voiceover sentence (this is what gets spoken)
          source_dialogue  — actual subtitle text from the matched dialogue cluster (evidence)
          anchor_quote     — the anchor phrase used for alignment
          movie_timestamp  — HH:MM:SS position in the actual movie (from dialogue timeline)
          start / end      — position in the generated narration audio timeline (not the movie)
          alignment_confidence — 'high' / 'medium' / 'low' based on combined_score
          timestamp_verified   — True if match was within the temporal window and score >= 0.35
          timestamp_warning    — human-readable note when alignment is uncertain

        NOTE on timestamp_verified: A verified timestamp means the aligner found a plausible
        dialogue cluster match. It does NOT prove the narration describes the event accurately.
        Factual verification requires comparing narration against source_dialogue independently.
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

        # 1. Build cohesive dialogue clusters (25-second windows) for semantic vector alignment
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

        aligner = SemanticAligner()

        # Pre-compute embeddings for all clusters ONCE to avoid redundant encoding per segment
        all_cluster_embeddings = aligner.precompute_cluster_embeddings(clusters)

        processed = []
        timeline_cursor = 0.0
        last_verified_sec = 0.0

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

            # Check for flashback / non-linear timeline markers BEFORE filtering candidate clusters (Issue 2)
            # A flashback or flash-forward can jump to any part of the movie outside the current block window.
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

            # Strictly constrain candidate dialogue clusters to this story block (+/- 45s buffer)
            # EXCEPT for flashbacks, which legitimately reference earlier/different timeline scenes.
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

            # Semantic vector match — passes pre-computed embeddings to avoid redundant encoding
            match_res = aligner.match_best_dialogue_cluster(
                narration_text=clean_text,
                dialogue_clusters=block_clusters,
                anchor_quote=anchor_quote,
                expected_time_sec=raw_time_sec,
                temporal_window_sec=240.0 if is_flashback else 180.0,
                precomputed_embeddings=block_embs
            )

            # Evaluate alignment quality using separate score components
            timestamp_verified = False
            timestamp_warning = ""
            alignment_confidence = "low"
            source_dialogue_text = ""

            if match_res:
                combined = match_res.get("combined_score", 0.0)
                cosine = match_res.get("cosine_similarity", 0.0)
                within_window = match_res.get("within_temporal_window", False)
                fallback = match_res.get("fallback_to_full_movie", False)

                # Accept match only if combined score meets threshold AND was within temporal window
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
                    # Weak match within window — use it but flag
                    final_movie_sec = match_res["timestamp"]
                    timestamp_warning = f"Weak alignment (combined={combined:.3f}, cosine={cosine:.3f}). Narration accuracy unverified."
                    source_dialogue_text = match_res.get("cluster", {}).get("text", "")
                    alignment_confidence = "low"
                elif fallback:
                    # Fell back to full-movie search — high risk of wrong timestamp
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

            # Monotonic guarantee with flashback exception (Issue 2):
            # If the segment is an intentional flashback or timeline transition, allow intentional
            # backwards jumps so the video editor shows the actual flashback scene accurately!
            backwards_jump = False

            if final_movie_sec < last_verified_sec and not is_flashback:
                diff = last_verified_sec - final_movie_sec
                if diff <= 45.0:
                    # Small backwards drift in standard chronological flow — adjust gently forward
                    final_movie_sec = last_verified_sec + 2.0
                    backwards_jump = True
                    if not timestamp_warning:
                        timestamp_warning = f"Matched timestamp was {diff:.1f}s before previous segment — adjusted forward."
                    else:
                        timestamp_warning += f" Additionally, matched timestamp was {diff:.1f}s before previous segment."
                    timestamp_verified = False
                else:
                    # Large backwards jump without flashback indicator — flag as alignment error
                    old_sec = final_movie_sec
                    final_movie_sec = min(b_et, last_verified_sec + 3.0)
                    backwards_jump = True
                    timestamp_warning = (
                        f"Matched timestamp ({fmt_sec(old_sec)}) is {diff:.1f}s before previous segment "
                        f"({fmt_sec(last_verified_sec)}) — large backwards jump flagged. Set to {fmt_sec(final_movie_sec)}."
                    )
                    timestamp_verified = False
            elif final_movie_sec < last_verified_sec and is_flashback:
                # Legitimate intentional flashback / non-linear timeline transition!
                # Preserve the earlier movie timestamp without destroying video sync!
                timestamp_warning = f"Intentional flashback: timestamp {fmt_sec(final_movie_sec)} is before previous scene {fmt_sec(last_verified_sec)}."
                if match_res and match_res.get("combined_score", 0.0) > 0.35:
                    timestamp_verified = True

            # Clamp strictly to block and runtime bounds
            final_movie_sec = max(0.0, min(total_runtime_sec - 5.0, final_movie_sec))

            # Snap scene cut point to nearest video I-frame (editing optimization only)
            if is_sc and movie_path and os.path.exists(movie_path):
                final_movie_sec = SemanticAligner.snap_to_nearest_keyframe(movie_path, final_movie_sec)

            # Only advance the timeline cursor for non-flashback segments.
            # For flashbacks, the main storyline has not advanced backwards.
            if not is_flashback:
                last_verified_sec = max(last_verified_sec, final_movie_sec)

            # Estimate spoken duration (~2.3 words per sec, min 3.8s, max 7.5s)
            word_count = max(1, len(clean_text.split()))
            est_dur = round(max(3.8, min(7.5, word_count / 2.3)), 2)

            entry = {
                "id": i + 1,
                # Narration audio timeline (NOT movie timeline)
                "start": round(timeline_cursor, 2),
                "end": round(timeline_cursor + est_dur, 2),
                "duration_sec": est_dur,
                # Movie position
                "movie_timestamp": fmt_sec(final_movie_sec),
                # Narration content
                "narration": clean_text,
                # Source evidence — actual subtitle dialogue matched at this timestamp
                "source_dialogue": source_dialogue_text,
                # Anchor phrase used for alignment
                "anchor_quote": anchor_quote,
                # Location and scene metadata
                "scene_location": scene_loc,
                "is_scene_change": is_sc,
                # Alignment quality metadata
                "alignment_confidence": alignment_confidence,
                "timestamp_verified": timestamp_verified,
                # Block boundaries (preserved for re-grounding after polish)
                "_block_start": b_st,
                "_block_end": b_et,
            }
            if timestamp_warning:
                entry["timestamp_warning"] = timestamp_warning
            if backwards_jump:
                entry["backwards_jump_detected"] = True
            if is_flashback:
                entry["is_flashback"] = True

            # Keep target_lang field for downstream TTS compatibility
            entry[target_lang.lower()] = clean_text

            processed.append(entry)
            timeline_cursor += est_dur

        return processed
