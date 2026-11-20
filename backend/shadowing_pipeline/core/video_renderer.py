"""Video Rendering Engine with Zero-RAM-Exhaustion Streaming to FFmpeg.

Streams rendered RGB24 frames sequentially into FFmpeg's stdin pipe, ensuring
constant O(1) memory usage regardless of video length (even 60+ minutes).
Ensures 1-frame audio/visual synchronization.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional
import numpy as np
from shadowing_pipeline.core.timeline import TimelineEvent
from shadowing_pipeline.core.visual_engine import VisualEngine


class VideoRenderer:
    def __init__(self, visual_engine: VisualEngine):
        self.visual_engine = visual_engine
        self.width = visual_engine.width
        self.height = visual_engine.height
        self.fps = visual_engine.fps

    def render_video(
        self,
        events: List[TimelineEvent],
        master_audio_path: str,
        amplitude_matrix: np.ndarray,
        output_mp4: str,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ):
        """Renders the entire timeline into a synchronized 1080p 30fps MP4 video.

        Streams frames to FFmpeg stdin to prevent memory exhaustion.
        """
        output_file = Path(output_mp4).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)

        total_duration = events[-1].end_time if events else 0.0
        total_frames = int(round(total_duration * self.fps))
        if total_frames <= 0:
            raise ValueError("Timeline is empty or has zero duration.")

        # FFmpeg encode pipeline
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{self.width}x{self.height}",
            "-pix_fmt",
            "rgb24",
            "-r",
            str(self.fps),
            "-i",
            "-",  # Stdin video stream
            "-i",
            str(Path(master_audio_path).resolve()),  # Audio track
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_file),
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=10**7,
        )

        event_idx = 0
        num_events = len(events)
        start_wall_time = time.time()

        try:
            for f in range(total_frames):
                current_time = f / float(self.fps)

                # Monotonically advance event index
                while (
                    event_idx + 1 < num_events
                    and current_time >= events[event_idx].end_time
                ):
                    event_idx += 1

                curr_event = events[event_idx]
                local_time = max(0.0, current_time - curr_event.start_time)
                is_speech = curr_event.type == "speech"

                # Get waveform amplitude slice for this frame
                if f < len(amplitude_matrix):
                    wf_bars = amplitude_matrix[f]
                else:
                    wf_bars = np.zeros(
                        self.visual_engine.theme["waveform"]["num_bars"]
                    )

                # Render single frame
                frame_img = self.visual_engine.render_frame(
                    curr_event, local_time, wf_bars, is_speech
                )

                # Write raw bytes directly to FFmpeg stdin
                proc.stdin.write(frame_img.tobytes())

                # Progress notification every 30 frames (1 second of video)
                if progress_callback and (f % 30 == 0 or f == total_frames - 1):
                    pct = round(((f + 1) / total_frames) * 100, 1)
                    progress_callback(f + 1, total_frames, pct)

            proc.stdin.close()
            stderr = proc.stderr.read() if proc.stderr else b""
            proc.wait()

            if proc.returncode != 0:
                err_msg = stderr.decode(errors="replace") if stderr else "Unknown error"
                raise RuntimeError(f"FFmpeg encoding failed: {err_msg}")

        except Exception as e:
            if proc.poll() is None:
                proc.kill()
            raise e
