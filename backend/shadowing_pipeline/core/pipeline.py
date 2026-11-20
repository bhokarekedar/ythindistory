"""End-to-End Orchestrator for the English Shadowing Video Pipeline.
"""

import copy
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from shadowing_pipeline.core.audio_builder import AudioBuilder
from shadowing_pipeline.core.audio_provider import AudioProvider
from shadowing_pipeline.core.exporters import (
    build_chapters_list,
    export_chapters_txt,
    export_srt,
    export_timeline_json,
    export_youtube_metadata,
)
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
        auto_upload: bool = False,
        privacy: str = "private",
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> Dict[str, Any]:
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
        # The video renderer must ignore "youtube" completely
        try:
            script = parse_and_validate_script(raw_dict)
        except ValueError as val_err:
            # If youtube metadata has validation errors, the video renderer still proceeds
            temp_dict = copy.deepcopy(raw_dict)
            yt_block = temp_dict.pop("youtube", None) if isinstance(temp_dict, dict) else None
            # Validate segments strictly
            script = parse_and_validate_script(temp_dict, require_youtube=False)
            if yt_block and isinstance(yt_block, dict):
                # Auto-trim tags if > 500 characters so auto-upload still succeeds
                if isinstance(yt_block.get("tags"), list):
                    trimmed_tags = []
                    curr_len = 0
                    for t in yt_block["tags"]:
                        add_len = len(str(t)) + (1 if trimmed_tags else 0)
                        if curr_len + add_len <= 500:
                            trimmed_tags.append(str(t).lower())
                            curr_len += add_len
                    yt_block["tags"] = trimmed_tags
                from shadowing_pipeline.core.schema import validate_youtube_metadata
                parsed_yt, _, _ = validate_youtube_metadata(yt_block, temp_dict.get("segments"))
                script.youtube = parsed_yt
            print(f"ℹ️ Video renderer proceeding (YouTube metadata auto-adapted: {val_err})")
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

        # 3. Export SRT, Timeline JSON, Chapters & YouTube Metadata
        print(f"📄 Exporting subtitles, timeline metadata, chapters, and YouTube metadata...")
        export_srt(events, final_srt)
        export_timeline_json(events, final_json)
        
        # Build chapters with '00:00 Intro'
        formatted_chapters, chap_warnings = build_chapters_list(
            self.timeline_builder.chapters, total_duration=total_duration
        )
        for w in chap_warnings:
            print(f"   ⚠️ {w}")
        chapters_txt = export_chapters_txt(formatted_chapters, final_chapters)
        if chapters_txt:
            print("\n📌 YouTube Chapters:")
            for line in chapters_txt.splitlines():
                print(f"   {line}")
            print("")

        yt_meta_paths = {}
        if script.youtube:
            yt_meta_paths = export_youtube_metadata(
                youtube_data=script.youtube,
                chapters_content=chapters_txt,
                chapters_list=formatted_chapters,
                duration_seconds=total_duration,
                output_dir=out_path,
            )
            print(f"✅ YouTube metadata exported to {out_path / 'video_metadata.json'}")

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

        result_dict = {
            "video": final_mp4,
            "srt": final_srt,
            "timeline": final_json,
            "chapters": final_chapters,
            "duration": total_duration,
        }
        if yt_meta_paths:
            result_dict.update({
                "metadata": yt_meta_paths["metadata_path"],
                "description": yt_meta_paths["description_path"],
                "tags": yt_meta_paths["tags_path"],
            })

        # 6. Automatically upload to YouTube as private video
        if auto_upload and not preview and yt_meta_paths and "metadata_path" in yt_meta_paths:
            print(f"\n🚀 Automatically uploading to YouTube (@ShadowEnglishDaily-d4z) as {privacy} video...")
            try:
                from shadowing_pipeline.core.youtube_uploader import upload_to_youtube
                upload_res = upload_to_youtube(
                    video_path=final_mp4,
                    metadata_path=yt_meta_paths["metadata_path"],
                    privacy=privacy,
                    confirm=True,
                )
                result_dict["youtube_upload"] = upload_res
                result_dict["youtube_url"] = upload_res.get("video_url")
                print(f"🎉 Successfully uploaded {privacy} video to YouTube: {upload_res.get('video_url')}")

                if upload_res.get("success") and upload_res.get("video_id"):
                    # 1. Save covered topics and YouTube metadata to training_dataset/
                    self._save_to_training_dataset(
                        script=script,
                        raw_dict=raw_dict,
                        upload_res=upload_res,
                        metadata_path=yt_meta_paths.get("metadata_path"),
                    )

                    # 2. Clear rendered video (.mp4) from output directory to free disk space
                    try:
                        import os
                        if final_mp4 and os.path.exists(final_mp4):
                            os.remove(final_mp4)
                            print(f"🗑️ Cleaned up rendered video from output: {final_mp4} (successfully saved to YouTube & stored in training_dataset)")
                            result_dict["video_cleaned_up"] = True
                    except Exception as clean_err:
                        print(f"⚠️ Note: Could not delete output video {final_mp4}: {clean_err}")
            except Exception as e:
                print(f"⚠️ Auto-upload to YouTube encountered an error: {e}")
                result_dict["youtube_upload_error"] = str(e)

        return result_dict

    def export_metadata_only(
        self,
        script_input: dict | str,
        output_dir: str = "output",
    ) -> Dict[str, Any]:
        """Validates script and exports all metadata without rendering video frames.

        Generates:
        - chapters.txt
        - video_metadata.json
        - description.txt
        - tags.txt
        - timeline.json
        """
        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        if isinstance(script_input, str):
            if script_input.strip().startswith("{"):
                raw_dict = json.loads(script_input)
            else:
                with open(script_input, "r", encoding="utf-8") as f:
                    raw_dict = json.load(f)
        else:
            raw_dict = script_input

        try:
            script = parse_and_validate_script(raw_dict)
        except ValueError as val_err:
            temp_dict = copy.deepcopy(raw_dict)
            yt_block = temp_dict.pop("youtube", None) if isinstance(temp_dict, dict) else None
            script = parse_and_validate_script(temp_dict, require_youtube=False)
            if yt_block and isinstance(yt_block, dict):
                if isinstance(yt_block.get("tags"), list):
                    trimmed_tags = []
                    curr_len = 0
                    for t in yt_block["tags"]:
                        add_len = len(str(t)) + (1 if trimmed_tags else 0)
                        if curr_len + add_len <= 500:
                            trimmed_tags.append(str(t).lower())
                            curr_len += add_len
                    yt_block["tags"] = trimmed_tags
                from shadowing_pipeline.core.schema import validate_youtube_metadata
                parsed_yt, _, _ = validate_youtube_metadata(yt_block, temp_dict.get("segments"))
                script.youtube = parsed_yt
        events = self.timeline_builder.build_timeline(script, preview=False)
        total_duration = events[-1].end_time if events else 0.0

        base_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in script.title)
        final_json = str(out_path / f"{base_name}_timeline.json")
        final_chapters = str(out_path / "chapters.txt")
        export_timeline_json(events, final_json)

        formatted_chapters, chap_warnings = build_chapters_list(
            self.timeline_builder.chapters, total_duration=total_duration
        )
        chapters_txt = export_chapters_txt(formatted_chapters, final_chapters)

        yt_meta_paths = {}
        if script.youtube:
            yt_meta_paths = export_youtube_metadata(
                youtube_data=script.youtube,
                chapters_content=chapters_txt,
                chapters_list=formatted_chapters,
                duration_seconds=total_duration,
                output_dir=out_path,
            )

        return {
            "title": script.title,
            "duration_seconds": total_duration,
            "chapters": formatted_chapters,
            "chapters_txt": chapters_txt,
            "metadata_path": yt_meta_paths.get("metadata_path", str(out_path / "video_metadata.json")),
            "description_path": yt_meta_paths.get("description_path", str(out_path / "description.txt")),
            "tags_path": yt_meta_paths.get("tags_path", str(out_path / "tags.txt")),
            "chapters_path": final_chapters,
            "video_metadata": yt_meta_paths.get("video_metadata", {}),
            "warnings": chap_warnings,
        }

    def _save_to_training_dataset(
        self,
        script: Any,
        raw_dict: dict,
        upload_res: dict,
        metadata_path: Optional[str] = None,
    ):
        """Saves covered topics, full script, and YouTube metadata into backend/training_dataset/."""
        import datetime
        import os

        # Find training_dataset directory
        training_dir = PACKAGE_DIR.parent / "training_dataset"
        training_dir.mkdir(parents=True, exist_ok=True)

        video_id = upload_res.get("video_id", "unknown")
        video_url = upload_res.get("video_url", f"https://youtu.be/{video_id}")
        title = getattr(script, "title", raw_dict.get("title", "untitled"))
        safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in title).strip("_")
        now_iso = datetime.datetime.now().isoformat()

        # Load video_metadata.json if available
        yt_meta = {}
        if metadata_path and os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    yt_meta = json.load(f)
            except Exception:
                pass
        if not yt_meta and isinstance(raw_dict.get("youtube"), dict):
            yt_meta = raw_dict.get("youtube")

        dataset_entry = {
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
            "uploaded_at": now_iso,
            "youtube": yt_meta,
            "script": raw_dict,
        }

        # 1. Save individual detailed record per video
        record_file = training_dir / f"{safe_title}_{video_id}.json"
        with open(record_file, "w", encoding="utf-8") as f:
            json.dump(dataset_entry, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved topic & YouTube metadata to training dataset: {record_file}")

        # 2. Update cumulative topics history index
        history_file = training_dir / "topics_history.json"
        history = []
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

        history = [h for h in history if h.get("video_id") != video_id]
        summary_item = {
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
            "youtube_title": yt_meta.get("title") if isinstance(yt_meta, dict) else title,
            "playlist": yt_meta.get("playlist") if isinstance(yt_meta, dict) else "",
            "tags": yt_meta.get("tags", []) if isinstance(yt_meta, dict) else [],
            "uploaded_at": now_iso,
        }
        history.append(summary_item)

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        print(f"📚 Updated cumulative topics history ({len(history)} total topics recorded): {history_file}")


