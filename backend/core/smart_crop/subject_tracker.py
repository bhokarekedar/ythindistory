import math
from typing import List, Optional, Dict
from .models import DetectedFace
from .config import SmartCropConfig


class TrackedSubject:
    def __init__(self, subject_id: int, initial_face: DetectedFace):
        self.subject_id = subject_id
        self.last_face = initial_face
        self.last_seen_timestamp = initial_face.timestamp
        self.center_x = float(initial_face.center_x)
        self.center_y = float(initial_face.center_y)
        self.vx = 0.0  # Horizontal velocity in px/s
        self.frames_tracked = 1
        self.missed_frames = 0
        self.importance_score = self._compute_importance(initial_face)

    def _compute_importance(self, face: DetectedFace) -> float:
        # Larger faces closer to the camera are typically primary speakers
        size_weight = float(face.px_w * face.px_h)
        conf_weight = face.confidence
        return size_weight * conf_weight

    def update(self, face: DetectedFace):
        dt = max(0.001, face.timestamp - self.last_seen_timestamp)
        new_x = float(face.center_x)
        new_y = float(face.center_y)
        self.vx = (new_x - self.center_x) / dt
        self.center_x = new_x
        self.center_y = new_y
        self.last_face = face
        self.last_seen_timestamp = face.timestamp
        self.frames_tracked += 1
        self.missed_frames = 0
        self.importance_score = 0.7 * self.importance_score + 0.3 * self._compute_importance(face)

    def predict(self, timestamp: float):
        dt = max(0.0, timestamp - self.last_seen_timestamp)
        # Dampened velocity extrapolation
        decay = math.exp(-2.0 * dt)
        pred_x = self.center_x + (self.vx * dt * decay)
        self.missed_frames += 1
        return pred_x, self.center_y


class SubjectTracker:
    """Maintains consistent subject identity across sampled frames to prevent erratic crop jumping."""

    def __init__(self, config: Optional[SmartCropConfig] = None):
        self.config = config or SmartCropConfig()
        self.tracks: Dict[int, TrackedSubject] = {}
        self.next_subject_id = 1
        self.primary_subject_id: Optional[int] = None
        self.max_missed_time_s = 0.85  # Retain track for ~0.85s of temporary occlusion/head turns
        self.max_match_dist_ratio = 0.35  # Maximum fraction of frame width to associate face

    def update(self, faces: List[DetectedFace], timestamp: float, frame_w: int, frame_h: int) -> Optional[DetectedFace]:
        """
        Updates tracks with newly detected faces and selects the primary subject.
        Returns the primary DetectedFace to frame.
        """
        max_dist = frame_w * self.max_match_dist_ratio

        # 1. Associate detected faces with existing active tracks
        unmatched_faces = list(faces)
        matched_track_ids = set()

        for track_id, track in list(self.tracks.items()):
            pred_x, pred_y = track.predict(timestamp)
            best_face = None
            best_dist = float("inf")

            for f in unmatched_faces:
                dist = math.hypot(f.center_x - pred_x, f.center_y - pred_y)
                if dist < best_dist and dist < max_dist:
                    best_dist = dist
                    best_face = f

            if best_face:
                track.update(best_face)
                best_face.subject_id = track_id
                unmatched_faces.remove(best_face)
                matched_track_ids.add(track_id)

        # 2. Register new tracks for unassociated faces
        for f in unmatched_faces:
            new_id = self.next_subject_id
            self.next_subject_id += 1
            f.subject_id = new_id
            self.tracks[new_id] = TrackedSubject(new_id, f)
            matched_track_ids.add(new_id)

        # 3. Prune tracks that have been lost for too long
        for track_id in list(self.tracks.keys()):
            track = self.tracks[track_id]
            if (timestamp - track.last_seen_timestamp) > self.max_missed_time_s:
                del self.tracks[track_id]
                if self.primary_subject_id == track_id:
                    self.primary_subject_id = None

        if not self.tracks:
            return None

        # 4. Temporal Hysteresis: Maintain primary subject to avoid ping-ponging
        if self.primary_subject_id not in self.tracks:
            # Pick track with highest importance (size & duration)
            best_id = max(self.tracks.keys(), key=lambda tid: self.tracks[tid].importance_score)
            self.primary_subject_id = best_id
        else:
            # Only switch away from current primary if another subject is substantially larger (> 1.6x)
            current_score = self.tracks[self.primary_subject_id].importance_score
            challenger_id = max(self.tracks.keys(), key=lambda tid: self.tracks[tid].importance_score)
            if challenger_id != self.primary_subject_id:
                challenger_score = self.tracks[challenger_id].importance_score
                if challenger_score > (current_score * 1.6) and self.tracks[challenger_id].frames_tracked >= 3:
                    self.primary_subject_id = challenger_id

        primary_track = self.tracks.get(self.primary_subject_id)
        return primary_track.last_face if primary_track else None

