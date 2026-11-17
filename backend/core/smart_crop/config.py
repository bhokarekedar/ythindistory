import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class SmartCropConfig:
    """Centralized configuration for the AI Smart Video Cropping Engine."""

    # Target framing
    target_width: int = 1080
    target_height: int = 1920
    target_aspect_ratio: str = "9:16"

    # Computer Vision Sampling
    frame_sampling_fps: float = 4.0  # Analyze 4 frames per sec (CPU-friendly on M1 Mac)
    face_min_confidence: float = 0.55
    min_face_size_ratio: float = 0.03  # Ignore tiny background noise faces (<3% of frame height)

    # Framing & Composition (Rules of Cinematography)
    headroom_margin: float = 0.18     # Headroom between top of crop window and top of head
    face_vertical_center_bias: float = 0.38  # Place eye/face line roughly 38% down from top (rule of thirds)
    deadzone_threshold_px: float = 28.0     # Stationary deadzone: suppress micro-jitter when subject barely moves

    # Smoothing & Temporal Damping
    crop_smoothing_enabled: bool = True
    smoothing_ema_alpha: float = 0.16       # Lower = smoother, cinematic pan; Higher = faster reaction
    max_horizontal_velocity_px_s: float = 420.0  # Maximum camera pan speed in pixels/second

    # Layout Strategies
    default_layout: str = "dynamic_smart_crop"   # dynamic_smart_crop, blurred_background, split_screen, static_center_crop
    fallback_layout: str = "blurred_background"

    # Rendering (FFmpeg)
    output_video_codec: str = "libx264"
    output_audio_codec: str = "aac"
    output_fps: int = 30
    crf: int = 19
    preset: str = "fast"
    faststart: bool = True

    # Debugging & Inspection
    save_debug_frames: bool = False
    debug_dir: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SmartCropConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

