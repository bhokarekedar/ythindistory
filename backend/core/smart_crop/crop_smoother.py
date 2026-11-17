import math
from typing import List
from .models import CropWindow
from .config import SmartCropConfig


class CropSmoother:
    """Applies temporal damping, deadzone suppression, and velocity limiting to eliminate crop jitter."""

    def __init__(self, config: SmartCropConfig):
        self.config = config

    def smooth_windows(self, raw_windows: List[CropWindow], src_w: int) -> List[CropWindow]:
        """
        Processes a sequence of raw crop windows into smooth, cinematographic camera panning.
        """
        if not raw_windows:
            return []

        if len(raw_windows) == 1 or not self.config.crop_smoothing_enabled:
            return raw_windows

        smoothed: List[CropWindow] = []
        first = raw_windows[0]
        smoothed.append(CropWindow(
            timestamp=first.timestamp,
            x=first.x,
            y=first.y,
            width=first.width,
            height=first.height,
            layout_type=first.layout_type
        ))

        curr_x = float(first.x)
        crop_w = first.width
        max_x = src_w - crop_w
        deadzone = self.config.deadzone_threshold_px
        alpha = self.config.smoothing_ema_alpha
        max_vel = self.config.max_horizontal_velocity_px_s

        for i in range(1, len(raw_windows)):
            prev = smoothed[-1]
            raw = raw_windows[i]
            dt = max(0.001, raw.timestamp - prev.timestamp)

            target_x = float(raw.x)
            delta_x = target_x - curr_x

            # 1. Deadzone: If movement is tiny, keep camera completely steady
            if abs(delta_x) < deadzone:
                # Camera remains stationary
                pass
            else:
                # 2. Exponential Moving Average smoothing
                # Effective alpha adjusted for variable dt
                effective_alpha = 1.0 - math.pow(1.0 - alpha, dt * self.config.frame_sampling_fps)
                new_x = curr_x + (delta_x * effective_alpha)

                # 3. Maximum velocity limit (avoid whip-pan)
                max_step = max_vel * dt
                actual_step = new_x - curr_x
                if abs(actual_step) > max_step:
                    actual_step = math.copysign(max_step, actual_step)
                    new_x = curr_x + actual_step

                curr_x = new_x

            # 4. Strict boundary clamping
            clamped_x = int(round(max(0.0, min(float(max_x), curr_x))))
            # Ensure even x for ffmpeg encoder alignment
            clamped_x = clamped_x - (clamped_x % 2)

            smoothed.append(CropWindow(
                timestamp=raw.timestamp,
                x=clamped_x,
                y=raw.y,
                width=raw.width,
                height=raw.height,
                layout_type=raw.layout_type
            ))

        return smoothed

