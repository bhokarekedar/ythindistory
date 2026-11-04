import os
import re

class SubtitleGenerator:
    """
    Generates high-retention, styled subtitles for movie recap & thriller stories.
    Outputs:
      1. Advanced SubStation Alpha (.ass) for razor-sharp burned-in rendering with
         crisp white text, bold font, and deep black border outline.
      2. Standard SubRip (.srt) for optional soft-subtitle upload to YouTube / Facebook.
    """

    @staticmethod
    def format_timestamp_ass(seconds: float) -> str:
        """Converts float seconds to ASS timestamp format: H:MM:SS.cs"""
        if seconds < 0:
            seconds = 0
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        if cs >= 100:
            cs = 99
        return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"

    @staticmethod
    def format_timestamp_srt(seconds: float) -> str:
        """Converts float seconds to SRT timestamp format: HH:MM:SS,mmm"""
        if seconds < 0:
            seconds = 0
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms >= 1000:
            ms = 999
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

    @staticmethod
    def wrap_text(text: str, max_chars_per_line: int = 32) -> str:
        """
        Wraps long sentence lines cleanly for ASS subtitles using \\N.
        Prevents captions from extending past screen margins on mobile.
        """
        text = text.strip()
        if len(text) <= max_chars_per_line:
            return text
            
        words = text.split()
        if len(words) <= 2:
            return text

        lines = []
        current_line = []
        current_len = 0

        for word in words:
            if current_len + len(word) + 1 > max_chars_per_line and current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_len = len(word)
            else:
                current_line.append(word)
                current_len += len(word) + 1

        if current_line:
            lines.append(" ".join(current_line))

        # Join lines using ASS line break tag
        return "\\N".join(lines[:2])  # Max 2 lines per screen to avoid clutter

    def generate(self, timeline: list, job_dir: str, base_name: str = "subtitles") -> dict:
        """
        Generates .ass and .srt files from the synchronized audio timeline.
        Returns a dict with paths to both files.
        """
        os.makedirs(job_dir, exist_ok=True)
        ass_path = os.path.join(job_dir, f"{base_name}.ass")
        srt_path = os.path.join(job_dir, f"{base_name}.srt")

        # ASS header with Mobile / Facebook viral styling:
        # - Crisp pure white text (&H00FFFFFF)
        # - 34px bold font for clear readability on mobile phone screens
        # - 3.2px solid black outline (&H00000000) for sharp contrast on light/dark scenes
        # - 1.5px shadow for depth
        # - Alignment 2 (bottom-center)
        # - MarginV 46px (comfortably above bottom scrubbers without covering faces)
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,34,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.2,1.5,2,50,50,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        ass_dialogues = []
        srt_entries = []
        srt_idx = 1

        for seg in timeline:
            text = (seg.get("text") or seg.get("hi") or seg.get("en") or "").strip()
            # Clean unwanted artifacts
            text = re.sub(r'\[.*?\]', '', text).strip()
            text = re.sub(r'\s+', ' ', text)
            if not text:
                continue

            start_sec = seg.get("audio_start", seg.get("start", 0.0))
            end_sec = seg.get("audio_end", seg.get("end", start_sec + 2.0))

            # Ensure minimum display time of 0.8s
            if end_sec <= start_sec:
                end_sec = start_sec + 1.0

            # 1. ASS Dialogue entry
            start_ass = self.format_timestamp_ass(start_sec)
            end_ass = self.format_timestamp_ass(end_sec)
            wrapped_ass = self.wrap_text(text, max_chars_per_line=44)
            ass_dialogues.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{wrapped_ass}")

            # 2. SRT Entry
            start_srt = self.format_timestamp_srt(start_sec)
            end_srt = self.format_timestamp_srt(end_sec)
            wrapped_srt = wrapped_ass.replace("\\N", "\n")
            srt_entries.append(f"{srt_idx}\n{start_srt} --> {end_srt}\n{wrapped_srt}\n")
            srt_idx += 1

        # Write ASS file
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(ass_dialogues) + "\n")

        # Write SRT file
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_entries) + "\n")

        print(f"  [Subtitles] ✅ Generated {len(ass_dialogues)} styled subtitle lines: {ass_path}")
        return {
            "ass_path": ass_path,
            "srt_path": srt_path,
            "total_lines": len(ass_dialogues)
        }
