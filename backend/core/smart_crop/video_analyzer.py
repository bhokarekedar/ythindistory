import json
import subprocess
import os
from typing import Optional
from .models import VideoMetadata


class VideoAnalyzer:
    """Extracts technical specifications and stream metadata from source videos via FFprobe."""

    @staticmethod
    def analyze(video_path: str) -> VideoMetadata:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file does not exist: {video_path}")

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            probe_data = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFprobe analysis failed for {video_path}: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Error parsing FFprobe output for {video_path}: {str(e)}")

        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise ValueError(f"No video stream found in file: {video_path}")

        raw_w = int(video_stream.get("width", 0))
        raw_h = int(video_stream.get("height", 0))
        codec = video_stream.get("codec_name", "unknown")
        pix_fmt = video_stream.get("pix_fmt", "yuv420p")

        # Parse FPS
        fps = 30.0
        fps_str = video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate")
        if fps_str and "/" in fps_str:
            num, den = fps_str.split("/")
            try:
                den_f = float(den)
                if den_f > 0:
                    fps = round(float(num) / den_f, 2)
            except (ValueError, ZeroDivisionError):
                pass
        elif fps_str:
            try:
                fps = float(fps_str)
            except ValueError:
                pass

        # Parse Duration
        duration = 0.0
        dur_str = video_stream.get("duration") or probe_data.get("format", {}).get("duration")
        if dur_str:
            try:
                duration = float(dur_str)
            except ValueError:
                pass

        # Check rotation metadata (e.g. from smartphone videos)
        rotation = 0
        side_data_list = video_stream.get("side_data_list", [])
        for sd in side_data_list:
            if "rotation" in sd:
                rotation = int(sd["rotation"])
                break
        if rotation == 0:
            tags = video_stream.get("tags", {})
            if "rotate" in tags:
                try:
                    rotation = int(tags["rotate"])
                except ValueError:
                    pass

        # Swap dimensions if rotated by 90 or 270 degrees
        final_w, final_h = raw_w, raw_h
        if abs(rotation) in (90, 270):
            final_w, final_h = raw_h, raw_w

        return VideoMetadata(
            width=final_w,
            height=final_h,
            fps=fps,
            duration=duration,
            codec=codec,
            pixel_format=pix_fmt,
            rotation=rotation,
            has_audio=audio_stream is not None,
            audio_codec=audio_stream.get("codec_name") if audio_stream else None,
            audio_channels=int(audio_stream.get("channels", 2)) if audio_stream else 0
        )

