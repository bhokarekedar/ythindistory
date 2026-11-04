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

    def generate_recap_script(self, movie_path: str, dialogue_json_path: str, output_script_path: str, target_lang: str = "english") -> str:
        """
        Distills raw movie dialogue into a high-retention, YouTube recap voiceover script.
        Breaks the film into 3 distinct acts to ensure rich storytelling depth and airtight climax.
        """
        if os.path.exists(output_script_path):
            print(f"  [MovieEngine] ⏩ Found cached recap script at: {output_script_path}")
            return output_script_path

        with open(dialogue_json_path, "r", encoding="utf-8") as f:
            dialogues = json.load(f)

        if not dialogues:
            raise ValueError(f"Dialogue log is empty: {dialogue_json_path}")

        total_lines = len(dialogues)
        movie_title = os.path.splitext(os.path.basename(movie_path))[0].split(".")[0].replace("_", " ").title()
        print(f"\n[MovieEngine] 🎬 Crafting Production YouTube Recap Script for '{movie_title}' ({total_lines} dialogue lines)...")

        # Split dialogue into 3 logical acts by dialogue count / runtime
        act1_end = int(total_lines * 0.33)
        act2_end = int(total_lines * 0.70)

        act1_dialogues = dialogues[:act1_end]
        act2_dialogues = dialogues[act1_end:act2_end]
        act3_dialogues = dialogues[act2_end:]

        acts_data = [
            ("Act 1: Inciting Incident & Setup", act1_dialogues, 35),
            ("Act 2: Rising Tension & Investigation", act2_dialogues, 45),
            ("Act 3: The Climax, Twist & Shocking Resolution", act3_dialogues, 40)
        ]

        all_segments = []
        global_seg_id = 1
        timeline_cursor = 0.0

        from core.translator import StoryTranslator

        for act_name, act_dialogues, target_segments in acts_data:
            print(f"  [MovieEngine] ✍️ Generating {act_name} (~{target_segments} voiceover beats)...")
            condensed_log = []
            for d in act_dialogues:
                hrs = int(d['start'] // 3600)
                mins = int((d['start'] % 3600) // 60)
                secs = int(d['start'] % 60)
                time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                condensed_log.append(f"[{time_str}] {d['text']}")

            sample_step = max(1, len(condensed_log) // 180)
            sampled_dialogue_text = "\n".join(condensed_log[::sample_step][:200])

            system_prompt = f"""You are a master YouTube movie recap script doctor and voiceover director.
Your mission is to transform the provided raw movie dialogue into an elite, high-retention YouTube Movie Recap narration script ({target_lang.upper()}).

CRITICAL STORYTELLING RULES:
1. MASTER RECAP STORYTELLER (NEVER TRANSLATE OR ECHO DIALOGUE LITERALLY):
   - You are the narrator explaining the film to movie lovers.
   - Set the scene, explain characters' inner thoughts, escalate dramatic stakes, and build mystery.
   - Example good line: "Driving home on a cold Thanksgiving night, Ray and his wife Joanne are locked in a bitter argument—completely unaware that a split-second tragedy is about to shatter their family."
2. UNIVERSAL 3RD-PERSON POV:
   - Always narrate in the third person ("Ray realized", "The doctor claimed", "She discovered"). Never use first-person "I" or "my".
3. KOKORO TTS AUDIO RULES:
   - Every single segment MUST be a complete, grammatically finished standalone statement ending strictly with a period (.), exclamation (!), or question mark (?).
   - NEVER end on trailing prepositions or conjunctions ('and', 'to', 'because', 'so', 'who', 'which').
4. DURATION & PACING:
   - Budget each segment to be punchy (~12 to 18 words), taking ~4.5 to 6.5 seconds when spoken.
5. PRESERVE THE CLIMAX & TRUTH:
   - Do not sanitize or obscure the ending. State the full, shocking resolution with maximum narrative impact.
6. FORMAT:
   - Output JSON with a key 'segments'. Each segment must have:
     "narration": The spoken voiceover text.
     "movie_timestamp": The timestamp string (HH:MM:SS) from the dialogue log where this scene occurs.
"""

            user_prompt = f"""Film: {movie_title}
Section: {act_name}
Target Segments to produce: approximately {target_segments} segments.

Movie Chronological Dialogue Sample:
{sampled_dialogue_text}
"""

            resp = self.provider.chat_completion(
                system_prompt=system_prompt,
                user_content=user_prompt,
                response_format={"type": "json_object"}
            )

            try:
                data = json.loads(resp)
                act_segs = data.get("segments", [])
            except Exception as parse_err:
                print(f"  [MovieEngine] Warning parsing act response ({parse_err}). Falling back.")
                act_segs = []

            for s in act_segs:
                narration = s.get("narration") or s.get("text") or ""
                if not narration:
                    continue
                # Sanitize text
                clean_text = StoryTranslator.sanitize_segment_text(narration, target_language=target_lang)
                ts_str = s.get("movie_timestamp", "00:00:00")
                
                # Estimate spoken duration (~2.5 words per sec, min 4s, max 7.5s)
                word_count = max(1, len(clean_text.split()))
                est_dur = round(max(3.8, min(7.5, word_count / 2.3)), 2)
                
                seg_obj = {
                    "id": global_seg_id,
                    "start": round(timeline_cursor, 2),
                    "end": round(timeline_cursor + est_dur, 2),
                    "duration_sec": est_dur,
                    "movie_timestamp": ts_str,
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
