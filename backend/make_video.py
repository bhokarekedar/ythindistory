#!/usr/bin/env python3
"""Command Line Interface for English Shadowing Script-to-Video Pipeline.

Usage:
    python make_video.py script.json
    python make_video.py script.json --preview
    python make_video.py script.json --output-dir output
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shadowing_pipeline.core.pipeline import ShadowingVideoPipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render English Shadowing YouTube Video from JSON Script."
    )
    parser.add_argument(
        "script",
        type=str,
        help="Path to the JSON script file (or '-' to read from stdin).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Render preview of only the first 5 segments for quick QA.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(BACKEND_DIR / "output"),
        help="Directory where output video, SRT, and timeline will be saved.",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default=str(BACKEND_DIR / "shadowing_pipeline" / "config" / "theme.json"),
        help="Path to custom theme configuration file.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional custom base filename for outputs.",
    )
    return parser.parse_args()


def progress_tracker(rendered_frames: int, total_frames: int, pct: float):
    bar_len = 30
    filled = int(round(bar_len * (pct / 100.0)))
    bar = "█" * filled + "░" * (bar_len - filled)
    sys.stdout.write(f"\r⏳ [Encoding Video] [{bar}] {pct:5.1f}% ({rendered_frames}/{total_frames} frames)")
    sys.stdout.flush()


def main():
    args = parse_args()

    script_source = args.script
    if script_source == "-":
        script_input = sys.stdin.read()
    else:
        script_path = Path(script_source)
        if not script_path.exists():
            print(f"❌ Error: Script file not found: {script_source}")
            sys.exit(1)
        script_input = str(script_path.resolve())

    try:
        pipeline = ShadowingVideoPipeline(theme_path=args.theme)
        results = pipeline.run(
            script_input=script_input,
            output_dir=args.output_dir,
            video_filename=args.name,
            preview=args.preview,
            progress_callback=progress_tracker,
        )
        print("\n" + "=" * 60)
        print("🎯 RENDERING COMPLETE:")
        print(f"📹 Video:    {results['video']}")
        print(f"📝 Subtitle: {results['srt']}")
        print(f"📊 Timeline: {results['timeline']}")
        print(f"⏱️ Duration: {results['duration']:.1f} seconds")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
