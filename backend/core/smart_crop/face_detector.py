import os
import urllib.request
from typing import List, Optional
import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .models import DetectedFace
from .config import SmartCropConfig


class FaceDetector:
    """Production-grade face detection engine powered by MediaPipe on-device models."""

    FULL_RANGE_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/latest/blaze_face_full_range.tflite"

    def __init__(self, config: Optional[SmartCropConfig] = None):
        self.config = config or SmartCropConfig()
        self.model_path = self._ensure_model_exists()
        self.detector = self._init_detector()

    def _ensure_model_exists(self) -> str:
        # Check standard models directories
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "models", "blaze_face_full_range.tflite"),
            os.path.join("backend", "models", "blaze_face_full_range.tflite"),
            os.path.join("models", "blaze_face_full_range.tflite"),
        ]
        for c in candidates:
            abs_c = os.path.abspath(c)
            if os.path.exists(abs_c):
                return abs_c

        # Auto-download if missing
        dest_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, "blaze_face_full_range.tflite")
        if not os.path.exists(dest_path):
            print(f"[FaceDetector] Downloading BlazeFace full-range model to {dest_path}...")
            urllib.request.urlretrieve(self.FULL_RANGE_URL, dest_path)
        return dest_path

    def _init_detector(self):
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=self.config.face_min_confidence
        )
        return vision.FaceDetector.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray, timestamp: float = 0.0) -> List[DetectedFace]:
        """
        Detects faces in a BGR frame (from cv2.VideoCapture).
        Returns list of DetectedFace objects with normalized & pixel coordinates.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        h, w = frame_bgr.shape[:2]
        if h == 0 or w == 0:
            return []

        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        try:
            result = self.detector.detect(mp_image)
        except Exception as e:
            print(f"[FaceDetector] Detection error at {timestamp:.2f}s: {e}")
            return []

        faces: List[DetectedFace] = []
        min_h = int(h * self.config.min_face_size_ratio)

        for detection in result.detections:
            bb = detection.bounding_box
            score = detection.categories[0].score if detection.categories else 0.0

            # Filter tiny background artifacts
            if bb.height < min_h:
                continue

            # Normalized coordinates bounded to [0.0, 1.0]
            norm_x = max(0.0, min(1.0, float(bb.origin_x) / float(w)))
            norm_y = max(0.0, min(1.0, float(bb.origin_y) / float(h)))
            norm_w = max(0.0, min(1.0 - norm_x, float(bb.width) / float(w)))
            norm_h = max(0.0, min(1.0 - norm_y, float(bb.height) / float(h)))

            face = DetectedFace(
                norm_x=norm_x,
                norm_y=norm_y,
                norm_w=norm_w,
                norm_h=norm_h,
                confidence=float(score),
                timestamp=timestamp
            )
            face.compute_pixels(w, h)
            faces.append(face)

        # Sort left-to-right
        faces.sort(key=lambda f: f.center_x)
        return faces

    def close(self):
        if hasattr(self, "detector") and self.detector:
            try:
                self.detector.close()
            except Exception:
                pass

