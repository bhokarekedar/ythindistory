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
    def get_lines(text: str, max_chars_per_line: int = 44) -> list:
        """
        Splits text cleanly into wrapped lines respecting word boundaries.
        Prevents captions from extending past screen margins on mobile.
        """
        text = text.strip()
        if not text:
            return []
        if len(text) <= max_chars_per_line:
            return [text]

        words = text.split()
        if len(words) <= 2:
            return [text]

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

        return lines

    @classmethod
    def wrap_text(cls, text: str, max_chars_per_line: int = 44, max_lines: int = None) -> str:
        """
        Wraps long sentence lines cleanly for ASS subtitles using \\N.
        Supports 1, 2, or 3 lines without cutting off text.
        If max_lines is specified, limits to that count, otherwise retains all lines.
        """
        lines = cls.get_lines(text, max_chars_per_line=max_chars_per_line)
        if not lines:
            return ""
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
        return "\\N".join(lines)

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

            lines = self.get_lines(text, max_chars_per_line=44)
            if not lines:
                continue

            duration = end_sec - start_sec

            # Case 1: 1, 2, or 3 lines -> Display all lines simultaneously
            if len(lines) <= 3:
                wrapped_ass = "\\N".join(lines)
                start_ass = self.format_timestamp_ass(start_sec)
                end_ass = self.format_timestamp_ass(end_sec)
                ass_dialogues.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{wrapped_ass}")

                start_srt = self.format_timestamp_srt(start_sec)
                end_srt = self.format_timestamp_srt(end_sec)
                wrapped_srt = wrapped_ass.replace("\\N", "\n")
                srt_entries.append(f"{srt_idx}\n{start_srt} --> {end_srt}\n{wrapped_srt}\n")
                srt_idx += 1
            else:
                # Case 2: 4+ lines -> Paginate across duration into 2 timed cues so screen is never crowded
                mid_idx = (len(lines) + 1) // 2
                page1_lines = lines[:mid_idx]
                page2_lines = lines[mid_idx:]

                p1_words = max(1, sum(len(l.split()) for l in page1_lines))
                total_words = max(1, sum(len(l.split()) for l in lines))

                # Divide time proportionally to word count
                split_sec = start_sec + (duration * (p1_words / total_words))
                if duration >= 2.4:
                    split_sec = max(start_sec + 1.0, min(end_sec - 1.0, split_sec))

                # Page 1
                wrapped_ass_1 = "\\N".join(page1_lines)
                start_ass_1 = self.format_timestamp_ass(start_sec)
                end_ass_1 = self.format_timestamp_ass(split_sec)
                ass_dialogues.append(f"Dialogue: 0,{start_ass_1},{end_ass_1},Default,,0,0,0,,{wrapped_ass_1}")

                start_srt_1 = self.format_timestamp_srt(start_sec)
                end_srt_1 = self.format_timestamp_srt(split_sec)
                wrapped_srt_1 = wrapped_ass_1.replace("\\N", "\n")
                srt_entries.append(f"{srt_idx}\n{start_srt_1} --> {end_srt_1}\n{wrapped_srt_1}\n")
                srt_idx += 1

                # Page 2
                wrapped_ass_2 = "\\N".join(page2_lines)
                start_ass_2 = self.format_timestamp_ass(split_sec)
                end_ass_2 = self.format_timestamp_ass(end_sec)
                ass_dialogues.append(f"Dialogue: 0,{start_ass_2},{end_ass_2},Default,,0,0,0,,{wrapped_ass_2}")

                start_srt_2 = self.format_timestamp_srt(split_sec)
                end_srt_2 = self.format_timestamp_srt(end_sec)
                wrapped_srt_2 = wrapped_ass_2.replace("\\N", "\n")
                srt_entries.append(f"{srt_idx}\n{start_srt_2} --> {end_srt_2}\n{wrapped_srt_2}\n")
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
