"""
Class-level activity recognition pipeline.

This phase treats activity as a classroom-scoped signal per camera/window
instead of assigning per-person activity labels.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime
import logging
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

STUDENT_ACTIVITY_LABELS = [
    "students_attentive",
    "students_writing",
    "students_reading",
    "students_peer_discussion",
    "students_off_task",
    "students_low_energy",
    "students_mixed",
    "students_uncertain",
]

FACULTY_ACTIVITY_LABELS = [
    "faculty_lecturing",
    "faculty_board_work",
    "faculty_monitoring",
    "faculty_one_to_one_support",
    "faculty_computer_work",
    "faculty_staff_discussion",
    "faculty_admin_non_computer",
    "faculty_absent_from_scene",
    "faculty_mixed",
    "faculty_uncertain",
]

CONTEXT_LABELS = [
    "class_in_session",
    "transition_period",
    "high_motion_classroom",
    "low_activity_classroom",
    "uncertain_context",
]

PIPELINE_VERSION = "class-activity-v1"


def _parse_zone(zone, frame_shape) -> Optional[Tuple[int, int, int, int]]:
    if not zone:
        return None
    if isinstance(zone, str):
        parts = [part.strip() for part in zone.split(",")]
    elif isinstance(zone, (list, tuple)):
        parts = list(zone)
    else:
        return None
    if len(parts) != 4:
        return None
    try:
        values = [float(part) for part in parts]
    except (TypeError, ValueError):
        return None
    h, w = frame_shape[:2]
    if all(0.0 <= value <= 1.0 for value in values):
        x1 = int(values[0] * w)
        y1 = int(values[1] * h)
        x2 = int(values[2] * w)
        y2 = int(values[3] * h)
    else:
        x1, y1, x2, y2 = [int(value) for value in values]
    x1 = max(0, min(w - 1, x1))
    y1 = max(0, min(h - 1, y1))
    x2 = max(x1 + 1, min(w, x2))
    y2 = max(y1 + 1, min(h, y2))
    return (x1, y1, x2, y2)


def _bbox_center(bbox) -> Tuple[float, float]:
    x, y, w, h = bbox
    return (x + (w / 2.0), y + (h / 2.0))


def _bbox_overlap_ratio(bbox, zone) -> float:
    if not bbox or not zone:
        return 0.0
    x, y, w, h = bbox
    x1, y1, x2, y2 = zone
    bx2 = x + w
    by2 = y + h
    overlap_x1 = max(x, x1)
    overlap_y1 = max(y, y1)
    overlap_x2 = min(bx2, x2)
    overlap_y2 = min(by2, y2)
    if overlap_x2 <= overlap_x1 or overlap_y2 <= overlap_y1:
        return 0.0
    overlap = float((overlap_x2 - overlap_x1) * (overlap_y2 - overlap_y1))
    area = max(1.0, float(w * h))
    return overlap / area


class ClassActivityPipeline:
    def __init__(self, window_size: int = 8):
        self.window_size = max(3, int(window_size))
        self._prev_gray: Dict[str, np.ndarray] = {}
        self._history = defaultdict(lambda: deque(maxlen=self.window_size))

    def analyze_scene(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        runtime_config: Dict,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Dict]:
        timestamp = timestamp or datetime.utcnow()
        camera_context = (runtime_config.get("camera_context") or "mixed").strip().lower()
        if camera_context != "classroom":
            return None

        camera_key = str(runtime_config.get("camera_name") or runtime_config.get("camera_id") or "camera")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        prev_gray = self._prev_gray.get(camera_key)
        motion_score = float(cv2.absdiff(gray, prev_gray).mean()) if prev_gray is not None else 0.0
        self._prev_gray[camera_key] = gray.copy()

        edge_density = float(np.count_nonzero(cv2.Canny(gray, 50, 150)) / max(1, gray.shape[0] * gray.shape[1]))

        student_zone = _parse_zone(runtime_config.get("student_seating_zone"), frame.shape)
        front_zone = _parse_zone(runtime_config.get("front_zone"), frame.shape)
        board_zone = _parse_zone(runtime_config.get("board_zone"), frame.shape)
        workstation_zone = _parse_zone(runtime_config.get("faculty_workstation_zone"), frame.shape)

        students = [d for d in detections if d.get("profile_type") == "student"]
        faculty = [d for d in detections if d.get("profile_type") == "faculty"]
        unknown_faces = [d for d in detections if not d.get("profile_type")]
        unknown_count = len(unknown_faces)

        student_label, student_conf = self._student_activity(
            students, unknown_faces, motion_score, edge_density, student_zone, frame.shape
        )
        faculty_label, faculty_conf = self._faculty_activity(
            faculty, students, unknown_faces, motion_score, front_zone, board_zone, workstation_zone
        )
        context_label, context_conf = self._context_activity(
            total_faces=len(detections),
            student_count=len(students),
            faculty_count=len(faculty),
            motion_score=motion_score,
        )

        class_name, section_name = self._resolve_scope(students, runtime_config)

        payload = {
            "camera_id": runtime_config.get("camera_id"),
            "location": runtime_config.get("camera_name"),
            "camera_context": camera_context,
            "class_name": class_name,
            "section_name": section_name,
            "student_activity_label": student_label,
            "student_activity_confidence": round(float(student_conf), 4),
            "faculty_activity_label": faculty_label,
            "faculty_activity_confidence": round(float(faculty_conf), 4),
            "context_label": context_label,
            "context_confidence": round(float(context_conf), 4),
            "recognized_student_count": len(students),
            "recognized_faculty_count": len(faculty),
            "unknown_count": int(unknown_count),
            "activity_version": PIPELINE_VERSION,
            "window_started_at": timestamp,
            "window_ended_at": timestamp,
            "timestamp": timestamp,
            "student_labels_supported": STUDENT_ACTIVITY_LABELS,
            "faculty_labels_supported": FACULTY_ACTIVITY_LABELS,
            "context_labels_supported": CONTEXT_LABELS,
            "reason": self._build_reason(
                recognized_students=len(students),
                recognized_faculty=len(faculty),
                unknown_count=unknown_count,
                motion_score=motion_score,
                student_label=student_label,
                faculty_label=faculty_label,
                context_label=context_label,
            ),
        }

        history = self._history[camera_key]
        history.append(payload)
        smoothed = self._smooth_payload(list(history))
        return smoothed

    def _resolve_scope(self, students: List[Dict], runtime_config: Dict) -> Tuple[Optional[str], Optional[str]]:
        class_counter = Counter()
        section_counter = Counter()
        for student in students:
            if student.get("class_name"):
                class_counter[student["class_name"]] += 1
            if student.get("section_name"):
                section_counter[student["section_name"]] += 1
        class_name = class_counter.most_common(1)[0][0] if class_counter else runtime_config.get("class_name")
        section_name = section_counter.most_common(1)[0][0] if section_counter else runtime_config.get("section_name")
        return class_name, section_name

    def _student_activity(self, students, unknown_faces, motion_score, edge_density, student_zone, frame_shape):
        effective_students = students or unknown_faces
        if not effective_students:
            return "students_uncertain", 0.2
        in_seating_ratio = 0.0
        if student_zone:
            in_seating = sum(1 for student in effective_students if _bbox_overlap_ratio(student.get("bbox"), student_zone) >= 0.25)
            in_seating_ratio = in_seating / max(1, len(effective_students))
        avg_face_area = np.mean([max(1.0, float(student["bbox"][2] * student["bbox"][3])) for student in effective_students if student.get("bbox")]) if effective_students else 0.0
        if motion_score < 2.0 and edge_density < 0.03:
            return "students_low_energy", 0.72
        if motion_score > 18 and len(effective_students) >= 4:
            return "students_peer_discussion", 0.68
        if edge_density > 0.08 and motion_score < 10 and in_seating_ratio >= 0.5:
            return "students_writing", 0.76
        if edge_density > 0.05 and motion_score < 6:
            return "students_reading", 0.67
        if motion_score > 26:
            return "students_off_task", 0.64
        if avg_face_area > 0 and motion_score < 12:
            return "students_attentive", 0.69
        return "students_mixed", 0.55

    def _faculty_activity(self, faculty, students, unknown_faces, motion_score, front_zone, board_zone, workstation_zone):
        if not faculty:
            candidate = self._pick_faculty_candidate(unknown_faces, front_zone, board_zone, workstation_zone)
            if candidate:
                inferred_label = self._faculty_label_for_candidate(
                    candidate, students, motion_score, front_zone, board_zone, workstation_zone, fallback=True
                )
                if inferred_label:
                    return inferred_label
            return "faculty_absent_from_scene", 0.95
        if len(faculty) >= 2 and motion_score > 10:
            return "faculty_staff_discussion", 0.73

        return self._faculty_label_for_candidate(
            faculty[0], students, motion_score, front_zone, board_zone, workstation_zone, fallback=False
        )

    def _faculty_label_for_candidate(self, faculty_member, students, motion_score, front_zone, board_zone, workstation_zone, fallback=False):
        bbox = faculty_member.get("bbox")
        movement = float(faculty_member.get("movement_score", 0.0))
        board_overlap = _bbox_overlap_ratio(bbox, board_zone) if board_zone else 0.0
        front_overlap = _bbox_overlap_ratio(bbox, front_zone) if front_zone else 0.0
        workstation_overlap = _bbox_overlap_ratio(bbox, workstation_zone) if workstation_zone else 0.0

        if workstation_overlap >= 0.25 and movement < 8 and motion_score < 10:
            return "faculty_computer_work", 0.84
        if workstation_overlap <= 0.0 and front_zone and front_overlap < 0.15 and movement < 4 and motion_score < 7:
            return "faculty_admin_non_computer", 0.65 if not fallback else 0.58
        if board_overlap >= 0.25 and movement >= 4:
            return "faculty_board_work", 0.79 if not fallback else 0.63
        if front_overlap >= 0.25 and movement >= 6:
            return "faculty_lecturing", 0.78 if not fallback else 0.62
        if students and movement < 6 and front_overlap < 0.2:
            return "faculty_one_to_one_support", 0.61 if not fallback else 0.52
        if movement >= 8:
            return "faculty_monitoring", 0.7 if not fallback else 0.56
        if movement < 4 and (front_overlap >= 0.15 or board_overlap >= 0.15):
            return "faculty_monitoring", 0.58 if not fallback else 0.5
        return "faculty_uncertain", 0.4

    def _pick_faculty_candidate(self, unknown_faces, front_zone, board_zone, workstation_zone):
        best_candidate = None
        best_score = 0.0
        for face in unknown_faces:
            bbox = face.get("bbox")
            if not bbox:
                continue
            score = max(
                _bbox_overlap_ratio(bbox, workstation_zone) if workstation_zone else 0.0,
                _bbox_overlap_ratio(bbox, board_zone) if board_zone else 0.0,
                _bbox_overlap_ratio(bbox, front_zone) if front_zone else 0.0,
            )
            if score > best_score:
                best_candidate = face
                best_score = score
        return best_candidate

    def _context_activity(self, total_faces, student_count, faculty_count, motion_score):
        if total_faces == 0:
            return "uncertain_context", 0.2
        if motion_score > 25:
            return "high_motion_classroom", 0.74
        if total_faces <= 2 and motion_score > 8:
            return "transition_period", 0.66
        if student_count > 0 and faculty_count >= 0 and motion_score < 12:
            return "class_in_session", 0.73
        if motion_score < 3:
            return "low_activity_classroom", 0.69
        return "uncertain_context", 0.45

    def _smooth_payload(self, history: List[Dict]) -> Dict:
        latest = dict(history[-1])
        for key in ("student_activity_label", "faculty_activity_label", "context_label"):
            labels = [item.get(key) for item in history if item.get(key)]
            if labels:
                latest[key] = Counter(labels).most_common(1)[0][0]
        for key in (
            "student_activity_confidence",
            "faculty_activity_confidence",
            "context_confidence",
            "recognized_student_count",
            "recognized_faculty_count",
            "unknown_count",
        ):
            values = [float(item.get(key) or 0.0) for item in history]
            latest[key] = round(sum(values) / max(1, len(values)), 4)
        latest["window_started_at"] = history[0].get("window_started_at")
        latest["window_ended_at"] = history[-1].get("window_ended_at")
        return latest

    def _build_reason(
        self,
        recognized_students: int,
        recognized_faculty: int,
        unknown_count: int,
        motion_score: float,
        student_label: str,
        faculty_label: str,
        context_label: str,
    ) -> str:
        return (
            f"recognized_students={recognized_students}, recognized_faculty={recognized_faculty}, "
            f"unknown_count={unknown_count}, motion={motion_score:.2f}, "
            f"student={student_label}, faculty={faculty_label}, context={context_label}"
        )
