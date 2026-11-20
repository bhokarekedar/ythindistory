#!/usr/bin/env python3
"""Builds timeline.json and chapters.txt for the Travel English Shadowing Script."""

import json
import sys
from pathlib import Path

# Add backend to sys.path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.exporters import export_chapters_txt, export_timeline_json, format_chapter_timestamp
from shadowing_pipeline.core.schema import validate_script_full
from shadowing_pipeline.core.timeline import TimelineBuilder, load_pipeline_config


def main():
    script_path = BACKEND_DIR / "travel_script.json"
    config_path = BACKEND_DIR / "shadowing_pipeline" / "config" / "config.json"
    output_dir = BACKEND_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    timeline_json_out = output_dir / "timeline.json"
    chapters_txt_out = output_dir / "chapters.txt"

    print(f"📖 Loading script: {script_path}")
    with open(script_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    print(f"⚙️ Loading config: {config_path}")
    config = load_pipeline_config(str(config_path))

    print("\n🔍 Step 1: Validating script...")
    script, errors, warnings = validate_script_full(raw_data, config)

    if warnings:
        print("⚠️ Validation Warnings / Notices:")
        for w in warnings:
            print(f"   • {w}")
    print("✅ Script passed validation!\n")

    print("🎙️ Step 2: Initializing Audio Provider & Kokoro TTS...")
    audio_provider = AudioProvider()
    builder = TimelineBuilder(audio_provider=audio_provider, config=config)

    print("⏱️ Step 3: Generating timeline events & synthesis...")
    events = builder.build_timeline(script, preview=False)

    total_duration = events[-1].end_time if events else 0.0
    total_mins = int(total_duration // 60)
    total_secs = int(total_duration % 60)

    # Export Deliverable 2: timeline.json
    export_timeline_json(events, str(timeline_json_out))
    print(f"💾 Deliverable 2 saved: {timeline_json_out}")

    # Export Deliverable 4: chapters.txt
    chapters_content = export_chapters_txt(builder.chapters, str(chapters_txt_out))
    print(f"💾 Deliverable 4 saved: {chapters_txt_out}")

    speech_count = sum(1 for e in events if e.event_type == "SPEECH")
    silence_count = sum(1 for e in events if e.event_type == "SILENCE")

    print("\n" + "=" * 65)
    print("🎯 TIMELINE BUILD SUMMARY")
    print("=" * 65)
    print(f"Lesson Title:    {script.title}")
    print(f"Total Events:    {len(events)} ({speech_count} SPEECH, {silence_count} SILENCE)")
    print(f"Total Duration:  {total_duration:.2f} seconds ({total_mins:02d}:{total_secs:02d})")
    print(f"Total Chapters:  {len(builder.chapters)}")
    print("=" * 65)

    print("\n📌 YouTube Chapters (chapters.txt):")
    print("-" * 45)
    print(chapters_content)
    print("-" * 45)


if __name__ == "__main__":
    main()

