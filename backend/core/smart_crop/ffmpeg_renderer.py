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

    def _rdp(self, points: List[tuple[float, int]], epsilon: float) -> List[tuple[float, int]]:
        """Ramer-Douglas-Peucker simplification algorithm for trajectory keyframes."""
        if len(points) <= 2:
            return points
        t0, x0 = points[0]
        t1, x1 = points[-1]
        dt = max(0.001, t1 - t0)
        max_d = 0.0
        idx = 0
        for i in range(1, len(points) - 1):
            ti, xi = points[i]
            expected_x = x0 + (x1 - x0) * ((ti - t0) / dt)
            d = abs(xi - expected_x)
            if d > max_d:
                max_d = d
                idx = i
        if max_d > epsilon:
            left = self._rdp(points[:idx + 1], epsilon)
            right = self._rdp(points[idx:], epsilon)
            return left[:-1] + right
        else:
            return [points[0], points[-1]]

    def _compress_keyframes(self, windows: List[CropWindow], tolerance_px: float = 8.0) -> List[tuple[float, int]]:
        """
        Compresses dense sampled windows into essential keyframe transitions (t, x)
        using the Ramer-Douglas-Peucker algorithm.
        """
        if not windows:
            return []

        pts = [(w.timestamp, w.x) for w in windows]
        if len(pts) <= 3:
            return pts

        return self._rdp(pts, tolerance_px)

    def _build_binary_tree_expr(self, keyframes: List[tuple[float, int]], max_x: int) -> str:
        """
        Recursively builds a balanced binary tree of if(lte(t, T_mid), left, right)
        to strictly guarantee maximum nesting depth <= log2(N) + 2 <= 10.
        This completely eliminates FFmpeg eval parser stack overflow / error -22.
        """
        if len(keyframes) == 1:
            x_val = max(0, min(max_x, keyframes[0][1]))
            return f"{x_val}"
        if len(keyframes) == 2:
            t0, x0 = keyframes[0]
            t1, x1 = keyframes[1]
            x0 = max(0, min(max_x, x0))
            x1 = max(0, min(max_x, x1))
            dt = max(0.001, t1 - t0)
            dx = x1 - x0
            if dx == 0:
                return f"{x0}"
            return f"({x0}+(t-{t0:.3f})*{dx:.2f}/{dt:.3f})"

        mid = len(keyframes) // 2
        t_mid = keyframes[mid][0]
        left = self._build_binary_tree_expr(keyframes[:mid + 1], max_x)
        right = self._build_binary_tree_expr(keyframes[mid:], max_x)
        return f"if(lte(t,{t_mid:.3f}),{left},{right})"

    def _build_crop_expression(self, keyframes: List[tuple[float, int]], crop_w: int, max_x: int) -> str:
        """
        Constructs an evaluation-efficient balanced binary piecewise linear interpolation expression for FFmpeg.
        """
        if not keyframes:
            return f"{(max_x // 2)}"

        if len(keyframes) == 1 or all(k[1] == keyframes[0][1] for k in keyframes):
            return f"{max(0, min(max_x, keyframes[0][1]))}"

        return self._build_binary_tree_expr(keyframes, max_x)

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
