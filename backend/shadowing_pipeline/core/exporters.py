"""Subtitle (SRT) and Timeline JSON Exporters for Debugging and Distribution.
"""

import json
from pathlib import Path
from typing import List
from shadowing_pipeline.core.timeline import TimelineEvent


def format_srt_timestamp(seconds: float) -> str:
    """Formats seconds into SRT time format HH:MM:SS,mmm."""
    ms = int(round(seconds * 1000))
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    secs = ms // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def export_srt(events: List[TimelineEvent], output_srt_path: str):
    """Generates a standard .srt subtitle file from the timeline events."""
    lines = []
    sub_index = 1

    for ev in events:
        start_ts = format_srt_timestamp(ev.start_time)
        end_ts = format_srt_timestamp(ev.end_time)

        if ev.sub_type == "section_title":
            caption = f"--- {ev.text.upper()} ---"
        elif ev.type == "silence":
            rep = f" ({ev.repeat_index}/{ev.repeat_total})" if ev.repeat_index else ""
            caption = f"[Your Turn{rep}]: {ev.text}"
        elif ev.sub_type == "dialogue":
            caption = f"{ev.speaker}: {ev.text}"
        else:
            caption = ev.text

        lines.append(f"{sub_index}")
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(caption)
        lines.append("")
        sub_index += 1

    out_file = Path(output_srt_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def export_timeline_json(events: List[TimelineEvent], output_json_path: str):
    """Dumps all timeline events and aligned word timings to JSON for inspection."""
    data = [ev.to_dict() for ev in events]
    out_file = Path(output_json_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

