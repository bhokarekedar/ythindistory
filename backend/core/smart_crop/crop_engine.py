import os
import time
import json
import cv2
from typing import Optional, List, Dict, Any

from .config import SmartCropConfig
from .models import (
    VideoMetadata,
    DetectedFace,
    FrameAnalysis,
    CropWindow,
    CropPlan,
    RenderReport
)
from .video_analyzer import VideoAnalyzer
from .face_detector import FaceDetector
from .subject_tracker import SubjectTracker
from .crop_planner import CropPlanner
from .crop_smoother import CropSmoother
from .ffmpeg_renderer import FFmpegRenderer


class SmartCropEngine:
    """
    Production-ready AI Smart Video Cropping Engine for reframing landscape videos
    into cinematographic 9:16 vertical videos for YouTube Shorts, Reels, and TikTok.
    """

    def __init__(self, config: Optional[SmartCropConfig] = None):
        self.config = config or SmartCropConfig()
        self.planner = CropPlanner(self.config)
        self.smoother = CropSmoother(self.config)
        self.renderer = FFmpegRenderer(self.config)

    def analyze_and_plan(
        self,
        source_path: str,
        start_time: Optional[float] = None,
        duration: Optional[float] = None,
        preferred_layout: Optional[str] = None
    ) -> CropPlan:
        """
        Analyzes source video frames and generates a smoothed, subject-aware 9:16 CropPlan.
        """
        metadata = VideoAnalyzer.analyze(source_path)
        clip_start = max(0.0, start_time or 0.0)
        clip_duration = min(duration or (metadata.duration - clip_start), metadata.duration - clip_start)
        clip_end = clip_start + clip_duration

        # If source is already vertical (e.g. 9:16 phone video), keep static center framing
        if metadata.is_vertical:
            w, h = self.planner.calculate_crop_dimensions(metadata.width, metadata.height)
            return CropPlan(
                source_width=metadata.width,
                source_height=metadata.height,
                target_width=self.config.target_width,
                target_height=self.config.target_height,
                layout="static_center_crop",
                crop_windows=[CropWindow(timestamp=0.0, x=0, y=0, width=w, height=h)],
                detected_subjects_count=0,
                tracking_stability_score=1.0,
                fallback_used=False
            )

        # Initialize CV modules
        detector = FaceDetector(self.config)
        tracker = SubjectTracker(self.config)

        cap = cv2.VideoCapture(source_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file via OpenCV: {source_path}")

        frame_step = max(1, int(round(metadata.fps / self.config.frame_sampling_fps)))
        start_frame = int(clip_start * metadata.fps)
        end_frame = int(clip_end * metadata.fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        current_frame = start_frame

        raw_windows: List[CropWindow] = []
        sampled_analyses: List[FrameAnalysis] = []
        total_faces_detected = 0
        frames_with_faces = 0

        try:
            while current_frame <= end_frame:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                if (current_frame - start_frame) % frame_step == 0:
                    timestamp = (current_frame - start_frame) / metadata.fps
                    faces = detector.detect(frame, timestamp=timestamp)
                    if faces:
                        frames_with_faces += 1
                        total_faces_detected += len(faces)

                    primary_face = tracker.update(faces, timestamp, metadata.width, metadata.height)
                    analysis = FrameAnalysis(
                        timestamp=timestamp,
                        frame_idx=current_frame,
                        faces=faces,
                        primary_subject=primary_face
                    )
                    sampled_analyses.append(analysis)

                    # Compute raw crop window
                    window = self.planner.plan_window(
                        primary_subject=primary_face,
                        all_faces=faces,
                        timestamp=timestamp,
                        src_w=metadata.width,
                        src_h=metadata.height
                    )
                    raw_windows.append(window)

                current_frame += 1

        finally:
            cap.release()
            detector.close()

        total_sampled = max(1, len(sampled_analyses))
        face_presence_ratio = frames_with_faces / total_sampled

        # Determine optimal layout strategy
        layout = preferred_layout or self.config.default_layout
        fallback_used = False
        fallback_reason = None

        if layout == "dynamic_smart_crop":
            # If faces were detected in fewer than 20% of sampled frames (e.g. gameplay or nature)
            if face_presence_ratio < 0.20:
                layout = self.config.fallback_layout
                fallback_used = True
                fallback_reason = f"Low face presence ({face_presence_ratio:.1%}). Switching to {layout}."
                print(f"[SmartCropEngine] {fallback_reason}")

        # Apply temporal smoothing to raw crop windows
        smoothed_windows = self.smoother.smooth_windows(raw_windows, src_w=metadata.width)

        # Calculate tracking stability score
        stability = 1.0
        if len(smoothed_windows) > 1:
            total_drift = sum(abs(smoothed_windows[i].x - smoothed_windows[i - 1].x) for i in range(1, len(smoothed_windows)))
            avg_drift_per_s = total_drift / max(0.1, clip_duration)
            stability = max(0.0, min(1.0, 1.0 - (avg_drift_per_s / self.config.max_horizontal_velocity_px_s)))

        return CropPlan(
            source_width=metadata.width,
            source_height=metadata.height,
            target_width=self.config.target_width,
            target_height=self.config.target_height,
            layout=layout,
            crop_windows=smoothed_windows,
            detected_subjects_count=tracker.next_subject_id - 1,
            tracking_stability_score=stability,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason
        )

    def process_clip(
        self,
        source_path: str,
        output_path: str,
        clip_id: str = "clip_01",
        start_time: Optional[float] = None,
        duration: Optional[float] = None,
        preferred_layout: Optional[str] = None
    ) -> RenderReport:
        """
        Executes end-to-end smart reframing: analysis, subject tracking, smoothing,
        and FFmpeg 1080x1920 rendering with diagnostic reporting.
        """
        t0 = time.time()
        metadata = VideoAnalyzer.analyze(source_path)

        clip_start = start_time or 0.0
        clip_dur = duration or (metadata.duration - clip_start)

        print(f"\n[SmartCropEngine] Starting Smart Crop on '{clip_id}'...")
        print(f"  Source: {metadata.width}x{metadata.height} @ {metadata.fps}fps, duration: {clip_dur:.2f}s")

        crop_plan = self.analyze_and_plan(
            source_path=source_path,
            start_time=clip_start,
            duration=clip_dur,
            preferred_layout=preferred_layout
        )

        print(f"  Selected Layout: {crop_plan.layout} (Subjects: {crop_plan.detected_subjects_count})")
        print(f"  Rendering 1080x1920 output via FFmpeg...")

        try:
            self.renderer.render(
                source_path=source_path,
                output_path=output_path,
                crop_plan=crop_plan,
                start_time=clip_start,
                duration=clip_dur
            )
            elapsed = time.time() - t0
            print(f"  ✅ Render complete in {elapsed:.2f}s -> {output_path}")

            report = RenderReport(
                clip_id=clip_id,
                source_path=source_path,
                output_path=output_path,
                source_resolution=f"{metadata.width}x{metadata.height}",
                output_resolution=f"{self.config.target_width}x{self.config.target_height}",
                duration=clip_dur,
                selected_layout=crop_plan.layout,
                detected_subjects=crop_plan.detected_subjects_count,
                tracking_stability=crop_plan.tracking_stability_score,
                fallback_used=crop_plan.fallback_used,
                fallback_reason=crop_plan.fallback_reason,
                processing_time_s=elapsed,
                render_status="completed"
            )

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ❌ Render error on {clip_id}: {e}")
            report = RenderReport(
                clip_id=clip_id,
                source_path=source_path,
                output_path=output_path,
                source_resolution=f"{metadata.width}x{metadata.height}",
                output_resolution=f"{self.config.target_width}x{self.config.target_height}",
                duration=clip_dur,
                selected_layout=crop_plan.layout,
                detected_subjects=crop_plan.detected_subjects_count,
                tracking_stability=crop_plan.tracking_stability_score,
                fallback_used=crop_plan.fallback_used,
                fallback_reason=crop_plan.fallback_reason,
                processing_time_s=elapsed,
                render_status="failed",
                error=str(e)
            )

        # Save analysis report JSON alongside clip
        report_path = os.path.splitext(output_path)[0] + "_crop_analysis.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        return report

