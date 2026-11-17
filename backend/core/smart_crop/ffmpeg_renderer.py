import os
import subprocess
import tempfile
from typing import List, Optional
from .models import CropWindow, CropPlan, VideoMetadata
from .config import SmartCropConfig


class FFmpegRenderer:
    """Executes production-grade FFmpeg filter graphs for dynamic smart cropping, blurred background, and static reframing."""

    def __init__(self, config: Optional[SmartCropConfig] = None):
        self.config = config or SmartCropConfig()

    def _compress_keyframes(self, windows: List[CropWindow], tolerance_px: float = 6.0) -> List[tuple[float, int]]:
        """
        Compresses dense sampled windows into essential keyframe transitions (t, x).
        Merges stationary holds and removes collinear intermediate samples.
        """
        if not windows:
            return []

        pts = [(w.timestamp, w.x) for w in windows]
        if len(pts) <= 3:
            return pts

        # Simplify by retaining points where velocity changes significantly
        compressed = [pts[0]]
        for i in range(1, len(pts) - 1):
            prev_t, prev_x = compressed[-1]
            curr_t, curr_x = pts[i]
            next_t, next_x = pts[i + 1]

            # If current position deviates from straight line between prev and next by > tolerance
            if next_t - prev_t > 0.001:
                expected_x = prev_x + (next_x - prev_x) * ((curr_t - prev_t) / (next_t - prev_t))
                if abs(curr_x - expected_x) > tolerance_px:
                    compressed.append((curr_t, curr_x))

        compressed.append(pts[-1])
        return compressed

    def _build_crop_expression(self, keyframes: List[tuple[float, int]], crop_w: int, max_x: int) -> str:
        """
        Constructs an evaluation-efficient piecewise linear interpolation expression for FFmpeg.
        """
        if not keyframes:
            return f"{(max_x // 2)}"

        if len(keyframes) == 1 or all(k[1] == keyframes[0][1] for k in keyframes):
            return f"{keyframes[0][1]}"

        # Build reverse-nested if(lte(t, t_i), ...) expression
        expr = f"{keyframes[-1][1]}"
        for i in range(len(keyframes) - 1, 0, -1):
            t_prev, x_prev = keyframes[i - 1]
            t_curr, x_curr = keyframes[i]
            dt = max(0.001, t_curr - t_prev)
            dx = x_curr - x_prev

            if dx == 0:
                seg_expr = f"{x_prev}"
            else:
                seg_expr = f"({x_prev}+(t-{t_prev:.3f})*{dx:.2f}/{dt:.3f})"

            expr = f"if(lte(t,{t_curr:.3f}),{seg_expr},{expr})"

        return expr

    def render(
        self,
        source_path: str,
        output_path: str,
        crop_plan: CropPlan,
        start_time: Optional[float] = None,
        duration: Optional[float] = None
    ) -> str:
        """Renders the final vertical video using the selected layout strategy."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        layout = crop_plan.layout
        if layout == "blurred_background":
            return self.render_blurred_background(source_path, output_path, start_time, duration)
        elif layout == "split_screen":
            return self.render_split_screen(source_path, output_path, start_time, duration)
        else:
            return self.render_smart_crop(source_path, output_path, crop_plan, start_time, duration)

    def render_smart_crop(
        self,
        source_path: str,
        output_path: str,
        crop_plan: CropPlan,
        start_time: Optional[float] = None,
        duration: Optional[float] = None
    ) -> str:
        """Renders dynamic or static crop with smooth subject-following camera panning."""
        windows = crop_plan.crop_windows
        if not windows:
            crop_w, crop_h = 608, 1080
            crop_expr = f"({crop_plan.source_width - crop_w} / 2)"
        else:
            crop_w = windows[0].width
            crop_h = windows[0].height
            max_x = max(0, crop_plan.source_width - crop_w)
            keyframes = self._compress_keyframes(windows)
            crop_expr = self._build_crop_expression(keyframes, crop_w, max_x)

        # Build FFmpeg filtergraph
        # 1. Crop to 9:16 slice based on dynamic x(t)
        # 2. Scale up/down cleanly to target 1080x1920 using lanczos filter
        # 3. Set display aspect ratio (setsar=1)
        vf_filter = (
            f"crop=w={crop_w}:h={crop_h}:x='{crop_expr}':y=0,"
            f"scale={self.config.target_width}:{self.config.target_height}:flags=lanczos,"
            f"setsar=1"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as script_file:
            script_file.write(vf_filter)
            script_path = script_file.name

        try:
            cmd = ["ffmpeg", "-y", "-v", "error"]

            if start_time is not None:
                cmd.extend(["-ss", f"{start_time:.3f}"])

            cmd.extend([
                "-i", source_path,
                "-filter_script:v", script_path,
                "-c:v", self.config.output_video_codec,
                "-preset", self.config.preset,
                "-crf", str(self.config.crf),
                "-pix_fmt", "yuv420p",
                "-r", str(self.config.output_fps),
                "-c:a", self.config.output_audio_codec,
                "-b:a", "192k",
                "-ac", "2",
                "-ar", "48000"
            ])

            if duration is not None:
                cmd.extend(["-t", f"{duration:.3f}"])

            if self.config.faststart:
                cmd.extend(["-movflags", "+faststart"])

            cmd.append(output_path)

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg rendering failed: {res.stderr}")

            return output_path
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

    def render_blurred_background(
        self,
        source_path: str,
        output_path: str,
        start_time: Optional[float] = None,
        duration: Optional[float] = None
    ) -> str:
        """
        Renders wide/gaming/landscape videos with central proportional presentation
        over a darkened, heavily blurred background fill.
        """
        target_w = self.config.target_width   # 1080
        target_h = self.config.target_height  # 1920

        # Complex filter:
        # [0:v] split into [bg] and [fg]
        # bg: scaled to fill 1080x1920, heavy boxblur, dimmed to 45% brightness
        # fg: scaled proportionally to width 1080 (height = 1080 * src_h / src_w)
        # overlay fg in vertical center of bg
        filter_complex = (
            f"[0:v]split=2[bg_src][fg_src];"
            f"[bg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},"
            f"boxblur=25:25,"
            f"colorchannelmixer=aa=0.85,"
            f"eq=brightness=-0.08:contrast=0.95[bg];"
            f"[fg_src]scale={target_w}:-2[fg];"
            f"[bg][fg]overlay=x=0:y=(H-h)/2:shortest=1[outv]"
        )

        cmd = ["ffmpeg", "-y", "-v", "error"]
        if start_time is not None:
            cmd.extend(["-ss", f"{start_time:.3f}"])

        cmd.extend([
            "-i", source_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a?",
            "-c:v", self.config.output_video_codec,
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            "-pix_fmt", "yuv420p",
            "-r", str(self.config.output_fps),
            "-c:a", self.config.output_audio_codec,
            "-b:a", "192k",
            "-ac", "2",
            "-ar", "48000"
        ])

        if duration is not None:
            cmd.extend(["-t", f"{duration:.3f}"])

        if self.config.faststart:
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(output_path)
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg blurred background rendering failed: {res.stderr}")

        return output_path

    def render_split_screen(
        self,
        source_path: str,
        output_path: str,
        start_time: Optional[float] = None,
        duration: Optional[float] = None
    ) -> str:
        """
        Renders two visual sections stacked vertically (top & bottom half of 1080x1920).
        """
        target_w = self.config.target_width   # 1080
        half_h = self.config.target_height // 2  # 960

        filter_complex = (
            f"[0:v]split=2[top_src][bot_src];"
            f"[top_src]crop=iw/2:ih:0:0,scale={target_w}:{half_h}:force_original_aspect_ratio=increase,crop={target_w}:{half_h}[top];"
            f"[bot_src]crop=iw/2:ih:iw/2:0,scale={target_w}:{half_h}:force_original_aspect_ratio=increase,crop={target_w}:{half_h}[bot];"
            f"[top][bot]vstack=inputs=2[outv]"
        )

        cmd = ["ffmpeg", "-y", "-v", "error"]
        if start_time is not None:
            cmd.extend(["-ss", f"{start_time:.3f}"])

        cmd.extend([
            "-i", source_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a?",
            "-c:v", self.config.output_video_codec,
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            "-pix_fmt", "yuv420p",
            "-r", str(self.config.output_fps),
            "-c:a", self.config.output_audio_codec,
            "-b:a", "192k",
            "-ac", "2",
            "-ar", "48000"
        ])

        if duration is not None:
            cmd.extend(["-t", f"{duration:.3f}"])

        if self.config.faststart:
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(output_path)
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg split screen rendering failed: {res.stderr}")

        return output_path
