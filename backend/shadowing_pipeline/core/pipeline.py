"""End-to-End Orchestrator for the English Shadowing Video Pipeline.
"""

import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional
from shadowing_pipeline.core.audio_builder import AudioBuilder
from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.exporters import export_chapters_txt, export_srt, export_timeline_json
from shadowing_pipeline.core.schema import parse_and_validate_script
from shadowing_pipeline.core.timeline import TimelineBuilder
from shadowing_pipeline.core.video_renderer import VideoRenderer
from shadowing_pipeline.core.visual_engine import VisualEngine


PACKAGE_DIR = Path(__file__).resolve().parent.parent


class ShadowingVideoPipeline:
    def __init__(
        self,
        theme_path: Optional[str] = None,
        custom_tts: Optional[Callable[[str, str], str]] = None,
        custom_transcribe: Optional[Callable[[str], List[Dict]]] = None,
    ):
        self.theme_path = theme_path
        self.audio_provider = AudioProvider(
            custom_tts=custom_tts, custom_transcribe=custom_transcribe
        )
        self.timeline_builder = TimelineBuilder(self.audio_provider)
        self.visual_engine = VisualEngine(theme_path)
        self.video_renderer = VideoRenderer(self.visual_engine)

    def run(
        self,
        script_input: dict | str,
        output_dir: str = "output",
        video_filename: Optional[str] = None,
        preview: bool = False,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> Dict[str, str]:
        """Runs the complete script-to-video generation pipeline.

        Returns a dictionary of output paths: video, srt, timeline.
        """
        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        temp_dir = out_path / "_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Parse and validate JSON input
        if isinstance(script_input, str):
            if script_input.strip().startswith("{"):
                raw_dict = json.loads(script_input)
            else:
                with open(script_input, "r", encoding="utf-8") as f:
                    raw_dict = json.load(f)
        else:
            raw_dict = script_input

        print("🔍 Validating script schema...")
        script = parse_and_validate_script(raw_dict)
        print(f"✅ Script validated: '{script.title}' ({len(script.segments)} segments)")

        # 2. Build Timeline
        print(f"⏱️ Building timeline (preview={preview})...")
        events = self.timeline_builder.build_timeline(script, preview=preview)
        total_duration = events[-1].end_time if events else 0.0
        print(
            f"✅ Timeline created: {len(events)} events, total duration: {total_duration:.1f}s"
        )

        # File naming
        base_name = video_filename or (
            "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in script.title)
            + ("_preview" if preview else "")
        )
        final_mp4 = str(out_path / f"{base_name}.mp4")
        final_srt = str(out_path / f"{base_name}.srt")
        final_json = str(out_path / f"{base_name}_timeline.json")
        final_chapters = str(out_path / f"{base_name}_chapters.txt")
        master_wav = str(temp_dir / f"{base_name}_master.wav")

        # 3. Export SRT, Timeline JSON & Chapters early for inspection
        print(f"📄 Exporting subtitles, timeline metadata, and chapters...")
        export_srt(events, final_srt)
        export_timeline_json(events, final_json)
        chapters_txt = export_chapters_txt(self.timeline_builder.chapters, final_chapters)
        if chapters_txt:
            print("\n📌 YouTube Chapters:")
            for line in chapters_txt.splitlines():
                print(f"   {line}")
            print("")

        # 4. Assemble Master Audio & Pre-compute Waveform Bars
        print("🎵 Assembling master audio track...")
        audio_builder = AudioBuilder(temp_dir=temp_dir)
        master_audio_path = audio_builder.assemble_master_audio(events, master_wav)

        print("📊 Extracting audio waveform envelope...")
        amplitude_matrix = audio_builder.extract_frame_amplitudes(
            master_audio_path,
            fps=self.visual_engine.fps,
            num_bars=self.visual_engine.theme["waveform"]["num_bars"],
        )

        # 5. Render Video Frames & Stream directly to FFmpeg
        print(f"🎬 Rendering and encoding {final_mp4} at 1080p 30fps...")
        start_time = time.time()
        self.video_renderer.render_video(
            events=events,
            master_audio_path=master_audio_path,
            amplitude_matrix=amplitude_matrix,
            output_mp4=final_mp4,
            progress_callback=progress_callback,
        )
        elapsed = time.time() - start_time
        fps_render = (
            int(round(total_duration * self.visual_engine.fps)) / max(0.1, elapsed)
        )
        print(
            f"\n🎉 Video rendered successfully in {elapsed:.1f}s ({fps_render:.1f} fps rendering speed)!"
        )

        return {
            "video": final_mp4,
            "srt": final_srt,
            "timeline": final_json,
            "chapters": final_chapters,
            "duration": total_duration,
        }

