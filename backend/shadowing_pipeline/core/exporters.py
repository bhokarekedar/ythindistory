"""Subtitle (SRT), Timeline JSON, YouTube Chapters, and YouTube Metadata Exporters.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel
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


def format_chapter_timestamp(seconds: float, is_over_hour: bool = False) -> str:
    """Formats seconds into YouTube chapter format MM:SS or H:MM:SS."""
    total_secs = int(round(seconds))
    hours = total_secs // 3600
    mins = (total_secs % 3600) // 60
    secs = total_secs % 60
    if is_over_hour or hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def build_chapters_list(
    raw_chapters: List[Dict[str, Any]],
    total_duration: float = 0.0,
    min_gap_seconds: float = 10.0,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Builds the final formatted YouTube chapters list.

    Rules:
    - ALWAYS prepends '00:00 Intro' (or '0:00:00 Intro' if video is over 1 hour).
    - Uses DISPLAYED title text, not spoken text.
    - Timestamps must be at least 10 seconds apart.
    - Warns if there are fewer than 3 chapters.
    """
    is_over_hour = total_duration >= 3600
    warnings: List[str] = []

    intro_time_str = "0:00:00" if is_over_hour else "00:00"
    result: List[Dict[str, Any]] = [
        {"time": intro_time_str, "title": "Intro", "seconds": 0.0}
    ]

    last_time = 0.0
    for ch in raw_chapters:
        start_sec = float(ch.get("start_time", 0.0))
        title = ch.get("title", "").strip()
        if not title:
            continue

        # Check YouTube 10s gap requirement
        if (start_sec - last_time) < min_gap_seconds:
            warnings.append(
                f"YouTube requires chapters to be at least {min_gap_seconds:.0f}s apart: chapter '{title}' at {start_sec:.1f}s is only {start_sec - last_time:.1f}s from previous chapter."
            )

        time_str = format_chapter_timestamp(start_sec, is_over_hour=is_over_hour)
        result.append({"time": time_str, "title": title, "seconds": start_sec})
        last_time = start_sec

    if len(result) < 3:
        warnings.append(
            f"YouTube requires at least 3 chapters for chapter markers to display (found {len(result)})."
        )

    return result, warnings


def export_chapters_txt(
    chapters_list: List[Dict[str, Any]], output_chapters_path: str
) -> str:
    """Generates YouTube-ready chapters lines and saves to chapters.txt."""
    lines = [f"{ch['time']} {ch['title']}" for ch in chapters_list]
    content = "\n".join(lines)
    out_file = Path(output_chapters_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def export_youtube_metadata(
    youtube_data: Union[BaseModel, Dict[str, Any]],
    chapters_content: str,
    chapters_list: List[Dict[str, Any]],
    duration_seconds: float,
    output_dir: Union[str, Path],
) -> Dict[str, Any]:
    """Generates video_metadata.json, description.txt, and tags.txt.

    Replaces {{CHAPTERS}} in description with chapters_content, validates
    total description length <= 5000 characters, and adds computed fields:
    - duration_seconds
    - chapters: list of {"time": str, "title": str}
    """
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(youtube_data, BaseModel):
        meta_dict = youtube_data.model_dump()
    else:
        meta_dict = dict(youtube_data)

    orig_desc = meta_dict.get("description", "")
    if "{{CHAPTERS}}" in orig_desc:
        final_desc = orig_desc.replace("{{CHAPTERS}}", chapters_content.strip())
    else:
        final_desc = f"{orig_desc}\n\n{chapters_content.strip()}"

    # Re-run length check AFTER replacement
    if len(final_desc) > 5000:
        raise ValueError(
            f"YouTube description exceeds maximum limit of 5000 characters after adding chapters ({len(final_desc)} characters). Please shorten the description text."
        )

    meta_dict["description"] = final_desc
    meta_dict["duration_seconds"] = round(float(duration_seconds), 2)
    meta_dict["chapters"] = [
        {"time": ch["time"], "title": ch["title"]} for ch in chapters_list
    ]

    # 1. video_metadata.json
    meta_file = out_dir / "video_metadata.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, indent=2, ensure_ascii=False)

    # 2. description.txt
    desc_file = out_dir / "description.txt"
    with open(desc_file, "w", encoding="utf-8") as f:
        f.write(final_desc)

    # 3. tags.txt
    tags_list = meta_dict.get("tags", [])
    tags_str = ",".join(str(t) for t in tags_list)
    tags_file = out_dir / "tags.txt"
    with open(tags_file, "w", encoding="utf-8") as f:
        f.write(tags_str)

    return {
        "metadata_path": str(meta_file),
        "description_path": str(desc_file),
        "tags_path": str(tags_file),
        "video_metadata": meta_dict,
    }


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
