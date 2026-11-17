from typing import Optional, List, Dict
from .models import DetectedFace, CropWindow, VideoMetadata
from .config import SmartCropConfig


class CropPlanner:
    """Calculates optimal 9:16 crop windows based on visual subject positions and cinematographic framing."""

    def __init__(self, config: Optional[SmartCropConfig] = None):
        self.config = config or SmartCropConfig()

    def calculate_crop_dimensions(self, src_w: int, src_h: int) -> tuple[int, int]:
        """Calculates 9:16 crop width and height that maximizes source frame coverage."""
        target_aspect = 9.0 / 16.0  # 0.5625
        src_aspect = src_w / max(1, src_h)

        if src_aspect >= target_aspect:
            # Landscape or wide: Crop width horizontally, preserve full height
            crop_h = src_h
            crop_w = int(round(src_h * target_aspect))
        else:
            # Extremely tall vertical: Crop height vertically, preserve full width
            crop_w = src_w
            crop_h = int(round(src_w / target_aspect))

        # Ensure even dimensions for H.264 macroblocks (yuv420p)
        crop_w = crop_w - (crop_w % 2)
        crop_h = crop_h - (crop_h % 2)
        return crop_w, crop_h

    def plan_window(
        self,
        primary_subject: Optional[DetectedFace],
        all_faces: List[DetectedFace],
        timestamp: float,
        src_w: int,
        src_h: int,
        layout: str = "dynamic_smart_crop"
    ) -> CropWindow:
        """Determines the raw target crop window for a single frame analysis point."""
        crop_w, crop_h = self.calculate_crop_dimensions(src_w, src_h)

        # Default fallback: Exact horizontal center
        default_x = (src_w - crop_w) // 2
        default_y = (src_h - crop_h) // 2

        if not primary_subject:
            return CropWindow(
                timestamp=timestamp,
                x=max(0, min(src_w - crop_w, default_x)),
                y=max(0, min(src_h - crop_h, default_y)),
                width=crop_w,
                height=crop_h,
                layout_type=layout
            )

        # Subject-centered composition
        ideal_center_x = primary_subject.center_x

        # If multiple people exist and fit comfortably inside 9:16, frame both
        if len(all_faces) >= 2 and layout == "dynamic_smart_crop":
            min_x = min(f.px_x for f in all_faces[:2])
            max_x = max(f.px_x + f.px_w for f in all_faces[:2])
            group_span = max_x - min_x
            # If both faces span less than 80% of crop width, center on group midpoint!
            if group_span < (crop_w * 0.80):
                ideal_center_x = (min_x + max_x) // 2

        target_x = ideal_center_x - (crop_w // 2)

        # Clamp strictly within source video boundaries
        clamped_x = max(0, min(src_w - crop_w, target_x))
        clamped_y = max(0, min(src_h - crop_h, default_y))

        return CropWindow(
            timestamp=timestamp,
            x=clamped_x,
            y=clamped_y,
            width=crop_w,
            height=crop_h,
            layout_type=layout
        )

