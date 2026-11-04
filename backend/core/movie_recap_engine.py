import os
import json
import re
import subprocess
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
        for k in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY_TWO"), os.getenv("GROQ_API_KEY_THREE")]:
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

        # 1. Probe for subtitle streams
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=index,codec_name:stream_tags=language,title",
            "-select_streams", "s",
            "-of", "json",
            movie_path
        ]
        res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(res.stdout)
        streams = probe_data.get("streams", [])

        if not streams:
            raise ValueError(f"No embedded subtitle tracks found in: {movie_path}. (External SRT or Whisper needed).")

        # 2. Select the best matching stream
        best_stream = None
        target_code = "hin" if preferred_lang.lower() in ["hi", "hindi", "hin"] else "eng"
        
        # Priority 1: Match requested language and non-SDH
        for s in streams:
            tags = s.get("tags", {})
            lang = tags.get("language", "").lower()
            title = tags.get("title", "").lower()
            if target_code in lang and "sdh" not in title:
                best_stream = s
                break
        
        # Priority 2: Match requested language even if SDH
        if not best_stream:
            for s in streams:
                lang = s.get("tags", {}).get("language", "").lower()
                if target_code in lang:
                    best_stream = s
                    break

        # Priority 3: Fallback to English
        if not best_stream:
            for s in streams:
                lang = s.get("tags", {}).get("language", "").lower()
                if "eng" in lang:
                    best_stream = s
                    break

        # Priority 4: Fallback to first stream
        if not best_stream:
            best_stream = streams[0]

        stream_idx = best_stream["index"]
        stream_lang = best_stream.get("tags", {}).get("language", "unknown")
        print(f"  [MovieEngine] 🎬 Selected Subtitle Stream #{stream_idx} ({stream_lang.upper()}) from movie container.")

        # 3. Extract to temp .srt file
        temp_srt = os.path.join(job_dir, f"{video_name}_extracted.srt")
        extract_cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", movie_path,
            "-map", f"0:{stream_idx}",
            "-c:s", "copy",
            temp_srt
        ]
        subprocess.run(extract_cmd, check=True)

        # 4. Parse SRT to JSON
        parsed_dialogues = self._parse_srt_file(temp_srt)
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
                            "original_text": text
                        })
                except Exception:
                    pass
        return dialogues

    def generate_recap_script(self, movie_path: str, dialogue_json_path: str, output_script_path: str, target_lang: str = "english", overwrite: bool = False) -> str:
        """
        Distills raw movie dialogue into a high-retention, YouTube recap voiceover script.
        Slices the film into 5 chronological storytelling acts based on actual runtime seconds,
        guaranteeing full story coverage, seamless narrative scene bridges, and complete twist preservation.
        """
        if os.path.exists(output_script_path) and not overwrite:
            print(f"  [MovieEngine] ⏩ Found cached recap script at: {output_script_path}")
            return output_script_path

        with open(dialogue_json_path, "r", encoding="utf-8") as f:
            dialogues = json.load(f)

        if not dialogues:
            raise ValueError(f"Dialogue log is empty: {dialogue_json_path}")

        total_lines = len(dialogues)
        movie_title = os.path.splitext(os.path.basename(movie_path))[0].split(".")[0].replace("_", " ").title()
        
        # Calculate actual elapsed runtime in seconds
        max_timestamp = max((float(d.get("end", d.get("start", 0))) for d in dialogues), default=5400.0)
        total_runtime_sec = max(3600.0, max_timestamp)
        runtime_mins = int(total_runtime_sec // 60)
        
        print(f"\n[MovieEngine] 🎬 Crafting Production YouTube Recap Script for '{movie_title}'")
        print(f"  [MovieEngine] ⏱️ Total Movie Runtime: ~{runtime_mins} minutes ({total_lines} dialogue lines)")

        # 6 chronological storytelling acts based on runtime seconds (guaranteeing dedicated Climax Act 6)
        t_act1 = total_runtime_sec * 0.20
        t_act2 = total_runtime_sec * 0.40
        t_act3 = total_runtime_sec * 0.62
        t_act4 = total_runtime_sec * 0.84
        t_act5 = total_runtime_sec * 0.96

        acts_data = [
            (
                "Act 1: The Inciting Incident & Road Trip Accident",
                [d for d in dialogues if d["start"] <= t_act1],
                14,
                "Covering the bitter road trip argument, the gas station stop, Peri falling into the construction pit, Ray desperately jumping after her, and rushing her toward medical help."
            ),
            (
                "Act 2: Hospital Admission & The Mysterious Disappearance",
                [d for d in dialogues if t_act1 < d["start"] <= t_act2],
                14,
                "Covering the tense hospital check-in, admitting Peri for a CT scan in the sub-basement with Joanne, Ray falling asleep in the waiting room, and waking up to find them vanished."
            ),
            (
                "Act 3: Hospital Gaslighting & Police Investigation",
                [d for d in dialogues if t_act2 < d["start"] <= t_act3],
                14,
                "Covering the hospital staff insisting Ray arrived alone with no records of Peri, security escorting him, police arrival, searching the hospital, and inspecting the rest stop pit where blood is discovered."
            ),
            (
                "Act 4: Psychiatrist Confrontation & The Standoff",
                [d for d in dialogues if t_act3 < d["start"] <= t_act4],
                14,
                "Covering Dr. Isaacs revealing Ray's previous deadly car accident, accusing him of severe trauma delusions, attempting to sedate him, and Ray overpowering officers to escape."
            ),
            (
                "Act 5: Sub-Basement Breach & Operating Room Shootout",
                [d for d in dialogues if t_act4 < d["start"] <= t_act5],
                12,
                "Covering Ray breaking into the restricted sub-basement operating room, confronting surgeons, shooting Dr. Volk dead, wrapping who he believes is Peri in a blanket, and rushing out to his car."
            ),
            (
                "Act 6: The Sunrise Escape, The Mirror Realization & The Shocking Trunk Twist",
                [d for d in dialogues if d["start"] > t_act5],
                11,
                "Deliver the unforgettable finale and chilling twist ending: 1) Ray drives his car into the morning sunrise, believing his family is safe. 2) Ray starts singing 'Sing a rainbow' while Dr. Isaacs' voice echoes that trauma forces the mind to construct alternate realities. 3) Ray glances into the rearview mirror, finally seeing the patient is actually an unknown dying surgical stranger. 4) FINAL SEGMENT: In the car trunk, Joanne and Peri's dead bodies have been lying lifeless ever since the pit accident, proving Ray hallucinated everything!"
            )
        ]

        all_segments = []
        global_seg_id = 1
        timeline_cursor = 0.0

        from core.translator import StoryTranslator

        for act_name, act_dialogues, target_segments, act_guidance in acts_data:
            if not act_dialogues:
                continue

            print(f"  [MovieEngine] ✍️ Generating {act_name} (~{target_segments} voiceover beats)...")
            
            condensed_log = []
            for d in act_dialogues:
                hrs = int(d['start'] // 3600)
                mins = int((d['start'] % 3600) // 60)
                secs = int(d['start'] % 60)
                time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                condensed_log.append(f"[{time_str}] {d['text'].strip()}")

            # Sample evenly across the entire duration of the act (40 points) so the full timeline arc is represented
            if len(condensed_log) > 40:
                step = len(condensed_log) / 40
                sampled_dialogues = [condensed_log[int(i * step)] for i in range(40)]
                sampled_dialogue_text = "\n".join(sampled_dialogues)
            else:
                sampled_dialogue_text = "\n".join(condensed_log)

            system_prompt = f"""You are an elite YouTube movie recap script doctor and voiceover director for top channels (e.g. Mystery Recapped, Movie Recaps).
Your mission is to transform the provided raw chronological movie dialogue into a viral, high-retention YouTube Movie Recap narration script in spoken {target_lang.upper()}.

CRITICAL PRODUCTION RULES:
1. PUNCHY, CINEMATIC 3RD-PERSON RECAP NARRATOR:
   - Narrate in active, cinematic third person ("Ray realizes", "The doctor insists", "Joanne warns"). Never use first person ("I", "my").
   - Set scenes, explain motivations, build dramatic suspense, and advance the plot with every line.
   - Summarize the story cleanly; NEVER transcribe minor receptionist chatter or literal word-for-word exchanges.

2. SEAMLESS NARRATIVE SCENE BRIDGES (ABSOLUTELY NO META-PHRASES):
   - FORBIDDEN META-PHRASES: NEVER use "In this scene we see", "Cut to", "The scene shifts to", "We are shown", "The camera pans", "Here we observe".
   - Instead, professional recaps transition between locations and scenes using seamless narrative bridges.
   - When a segment represents a new scene, location, or time leap (scene_change = true), open the sentence with an evocative narrative bridge phrase such as:
     * "Arriving at the abandoned rest stop, Ray pulls over to inspect the car."
     * "Back inside the crowded emergency room, Joanne's patience wears thin."
     * "Hours later, deep in the hospital's locked sub-basement, the terrifying truth unfolds."
     * "Stepping out into the biting morning air, Ray rushes toward his car."
     * "Glancing into the rearview mirror as the sun rises, the chilling reality hits."

3. STRICT 1-SENTENCE CADENCE (10 TO 16 WORDS PER SEGMENT):
   - Every single segment MUST be EXACTLY ONE single concise standalone sentence.
   - Word count MUST be between 10 and 16 words per segment. (NEVER write more than 1 sentence, and NEVER write paragraphs).
   - Ending strictly with terminal punctuation: period (.), exclamation (!), or question mark (?).
   - NEVER end on trailing conjunctions or prepositions ('and', 'because', 'so', 'to', 'who').

4. FULL TIMELINE PACING & TWIST PRESERVATION:
   - You MUST distribute your segments evenly across the entire dialogue timeline provided, from the opening timestamp to the final timestamp of this act.
   - For Act 6, you MUST conclude with the shocking twist: Ray looks into the rearview mirror and sees an unknown surgical patient, while the final segment reveals Joanne and Peri's bodies were dead in his car trunk the entire time!

5. OUTPUT FORMAT (COMPACT JSON):
   - Return valid JSON with a single key 'segments'. Each segment object MUST have:
     "text": The spoken voiceover narration (strictly 10-16 words, 1 standalone sentence, no meta-phrases).
     "time": The timestamp string (HH:MM:SS) from the dialogue log where this scene occurs.
     "loc": Short name of the scene location (e.g. "Rest Stop", "ER Waiting Room", "Sub-Basement OR", "Ray's Car / Sunrise").
     "scene_change": Boolean (true if this segment transitions to a new scene, time, or location).
"""

            user_prompt = f"""Film: {movie_title}
Act: {act_name}
Target Segments to produce: approximately {target_segments} segments (each EXACTLY 1 single standalone sentence, 10-16 words).
Act Objective: {act_guidance}

Chronological Movie Dialogue Timeline:
{sampled_dialogue_text}
"""

            resp = self.provider.chat_completion(
                system_prompt=system_prompt,
                user_content=user_prompt,
                response_format={"type": "json_object"},
                max_tokens=980
            )

            try:
                data = json.loads(resp)
                act_segs = data.get("segments", [])
            except Exception as parse_err:
                print(f"  [MovieEngine] Warning parsing act response ({parse_err}). Falling back.")
                act_segs = []

            for s in act_segs:
                narration = s.get("text") or s.get("narration") or ""
                if not narration:
                    continue
                # Sanitize text
                clean_text = StoryTranslator.sanitize_segment_text(narration, target_language=target_lang)
                ts_str = s.get("time") or s.get("movie_timestamp") or "01:33:00"
                scene_loc = s.get("loc") or s.get("scene_location") or s.get("scene location") or "Unknown Location"
                is_sc = bool(s.get("scene_change") if "scene_change" in s else s.get("is_scene_change", False))
                
                # Estimate spoken duration (~2.5 words per sec, min 4s, max 7.5s)
                word_count = max(1, len(clean_text.split()))
                est_dur = round(max(3.8, min(7.5, word_count / 2.3)), 2)
                
                seg_obj = {
                    "id": global_seg_id,
                    "start": round(timeline_cursor, 2),
                    "end": round(timeline_cursor + est_dur, 2),
                    "duration_sec": est_dur,
                    "movie_timestamp": ts_str,
                    "scene_location": scene_loc,
                    "is_scene_change": is_sc,
                    target_lang.lower(): clean_text,
                    "original_text": clean_text
                }
                timeline_cursor += est_dur
                global_seg_id += 1
                all_segments.append(seg_obj)

        with open(output_script_path, "w", encoding="utf-8") as f:
            json.dump(all_segments, f, indent=4, ensure_ascii=False)

        print(f"\n[MovieEngine] ✅ Full Movie Recap Script complete: {len(all_segments)} segments saved to {output_script_path}!")
        return output_script_path
