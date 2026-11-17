from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class VideoMetadata:
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    pixel_format: str
    rotation: int = 0
    has_audio: bool = True
    audio_codec: Optional[str] = None
    audio_channels: int = 2

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(1, self.height)

    @property
    def is_landscape(self) -> bool:
        return self.aspect_ratio > 1.1

    @property
    def is_vertical(self) -> bool:
        return self.aspect_ratio < 0.9

    @property
    def is_square(self) -> bool:
        return 0.9 <= self.aspect_ratio <= 1.1


@dataclass
class DetectedFace:
    # Normalized coordinates [0.0, 1.0]
    norm_x: float
    norm_y: float
    norm_w: float
    norm_h: float
    confidence: float
    timestamp: float

    # Pixel coordinates inside source video frame
    px_x: int = 0
    px_y: int = 0
    px_w: int = 0
    px_h: int = 0
    center_x: int = 0
    center_y: int = 0
    subject_id: Optional[int] = None

    def compute_pixels(self, frame_w: int, frame_h: int):
        self.px_x = int(self.norm_x * frame_w)
        self.px_y = int(self.norm_y * frame_h)
        self.px_w = int(self.norm_w * frame_w)
        self.px_h = int(self.norm_h * frame_h)
        self.center_x = self.px_x + (self.px_w // 2)
        self.center_y = self.px_y + (self.px_h // 2)


@dataclass
class FrameAnalysis:
    timestamp: float
    frame_idx: int
    faces: List[DetectedFace] = field(default_factory=list)
    primary_subject: Optional[DetectedFace] = None
    is_scene_cut: bool = False


@dataclass
class CropWindow:
    timestamp: float
    x: int
    y: int
    width: int
    height: int
    layout_type: str = "dynamic_smart_crop"


@dataclass
class CropPlan:
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    layout: str
    crop_windows: List[CropWindow] = field(default_factory=list)
    detected_subjects_count: int = 0
    tracking_stability_score: float = 1.0
    fallback_used: bool = False
    fallback_reason: Optional[str] = None


@dataclass
class RenderReport:
    clip_id: str
    source_path: str
    output_path: str
    source_resolution: str
    output_resolution: str
    duration: float
    selected_layout: str
    detected_subjects: int
    tracking_stability: float
    fallback_used: bool
    fallback_reason: Optional[str]
    processing_time_s: float
    render_status: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "source_resolution": self.source_resolution,
            "output_resolution": self.output_resolution,
            "duration": round(self.duration, 2),
            "selected_layout": self.selected_layout,
            "detected_subjects": self.detected_subjects,
            "tracking_stability_score": round(self.tracking_stability, 3),
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "processing_time_seconds": round(self.processing_time_s, 2),
            "render_status": self.render_status,
            "error": self.error
        }

