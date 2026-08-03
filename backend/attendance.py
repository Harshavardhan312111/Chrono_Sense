"""
Attendance tracking for ChronoSense using MongoDB only.
"""

import csv
import io
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store
try:
    from time_utils import APP_TIMEZONE, UTC, app_now
except ImportError:
    from backend.time_utils import APP_TIMEZONE, UTC, app_now

logger = logging.getLogger(__name__)
LOW_SIGNAL_EMOTION = "LowSignal"


def _display_emotion_label(emotion, emotion_data=None):
    value = emotion or (emotion_data or {}).get("smoothed_emotion") or (emotion_data or {}).get("raw_emotion") or LOW_SIGNAL_EMOTION
    if value == LOW_SIGNAL_EMOTION:
        return "Neutral"
    return value
ATTENDANCE_RECOGNITION_FLOOR = 0.39
def to_ist_time(utc_time_str):
    try:
        if not utc_time_str:
            return None
        dt = datetime.fromisoformat(str(utc_time_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        ist_dt = dt.astimezone(APP_TIMEZONE)
        return ist_dt.strftime("%H:%M:%S")
    except Exception:
        return utc_time_str


class DetectionCache:
    def __init__(self, deduplicate_window=60):
        self.cache = {}
        self.deduplicate_window = deduplicate_window * 60

    def should_log(self, profile_id):
        now = time.time()
        if profile_id not in self.cache:
            return True
        return (now - self.cache[profile_id]) >= self.deduplicate_window

    def mark_logged(self, profile_id):
        self.cache[profile_id] = time.time()

    def clear_old_entries(self, max_age=3600):
        now = time.time()
        to_remove = [pid for pid, ts in self.cache.items() if (now - ts) > max_age]
        for pid in to_remove:
            del self.cache[pid]


class ActivityCache:
    def __init__(self, deduplicate_window_seconds=5):
        self.cache = {}
        self.deduplicate_window = deduplicate_window_seconds

    def should_log(self, profile_id, unknown_face_id, location):
        now = time.time()
        key = (profile_id, unknown_face_id, location)
        if key not in self.cache:
            return True
        last_log, _ = self.cache[key]
        return (now - last_log) >= self.deduplicate_window

    def mark_logged(self, profile_id, unknown_face_id, location, activity):
        self.cache[(profile_id, unknown_face_id, location)] = (time.time(), activity)

    def clear_old_entries(self, max_age=3600):
        now = time.time()
        to_remove = [k for k, (ts, _) in self.cache.items() if (now - ts) > max_age]
        for key in to_remove:
            del self.cache[key]


class ClassActivityCache:
    def __init__(self, deduplicate_window_seconds=10):
        self.cache = {}
        self.deduplicate_window = deduplicate_window_seconds

    def should_log(self, camera_id, student_label, faculty_label, context_label):
        now = time.time()
        key = (camera_id, student_label, faculty_label, context_label)
        if key not in self.cache:
            return True
        return (now - self.cache[key]) >= self.deduplicate_window

    def mark_logged(self, camera_id, student_label, faculty_label, context_label):
        self.cache[(camera_id, student_label, faculty_label, context_label)] = time.time()

    def clear_old_entries(self, max_age=3600):
        now = time.time()
        to_remove = [key for key, ts in self.cache.items() if (now - ts) > max_age]
        for key in to_remove:
            del self.cache[key]


class AttendanceTracker:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "mongo")
        mongo_store.ensure_connected()
        self.detection_cache = DetectionCache(deduplicate_window=60)
        self.activity_cache = ActivityCache(deduplicate_window_seconds=5)
        self.class_activity_cache = ClassActivityCache(deduplicate_window_seconds=10)
        self.min_emotion_confidence = float(os.getenv("CHRONOSENSE_EMOTION_CONFIDENCE_THRESHOLD", "0.45"))
        configured_attendance_threshold = os.getenv(
            "CHRONOSENSE_ATTENDANCE_RECOGNITION_THRESHOLD",
            os.getenv("CHRONOSENSE_RECOGNITION_THRESHOLD", str(ATTENDANCE_RECOGNITION_FLOOR)),
        )
        try:
            self.min_attendance_recognition_confidence = max(
                ATTENDANCE_RECOGNITION_FLOOR,
                float(configured_attendance_threshold),
            )
        except (TypeError, ValueError):
            self.min_attendance_recognition_confidence = ATTENDANCE_RECOGNITION_FLOOR
        self.init_attendance_table()

    @staticmethod
    def _day_bounds(date_str):
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = start + timedelta(days=1)
        return start, end

    @staticmethod
    def _timestamp_to_iso(value):
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def _time_component(value):
        if isinstance(value, datetime):
            return value.strftime("%H:%M:%S")
        if isinstance(value, str) and "T" in value:
            return value.split("T", 1)[1][:8]
        if isinstance(value, str) and " " in value:
            return value.split(" ", 1)[1][:8]
        return value

    @staticmethod
    def _normalize_time_string(value):
        if not value:
            return None
        value = str(value).strip()
        if len(value) == 5:
            return f"{value}:00"
        return value[:8]

    def _parse_time_value(self, value):
        normalized = self._normalize_time_string(value)
        if not normalized:
            return None
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    def _profiles_collection(self):
        return mongo_store.collection("profiles")

    def _attendance_collection(self):
        return mongo_store.collection("attendance_log")

    def _attendance_summary_collection(self):
        return mongo_store.collection("attendance_summary")

    def _activity_collection(self):
        return mongo_store.collection("activity_log")

    def _activity_summary_collection(self):
        return mongo_store.collection("activity_summary")

    def _emotion_events_collection(self):
        return mongo_store.collection("emotion_events")

    def _class_activity_collection(self):
        return mongo_store.collection("class_activity_log")

    def _class_activity_summary_collection(self):
        return mongo_store.collection("class_activity_summary")

    def _schedule_collection(self):
        return mongo_store.collection("class_schedule")

    def init_attendance_table(self):
        mongo_store.ensure_connected()
        logger.info("✓ Attendance collections initialized via MongoDB")

    def _get_profile(self, profile_id):
        return self._profiles_collection().find_one({"_id": profile_id})

    def _schedule_for(self, date_str, class_name="Default"):
        return self._schedule_collection().find_one({"date": date_str, "class_name": class_name})

    def _is_late(self, profile, seen_at, date_str):
        class_name = profile.get("class_name") or "Default"
        schedule = self._schedule_for(date_str, class_name)
        reference = schedule.get("start_time") if schedule else profile.get("check_in_time")
        if not reference:
            return False
        arrival = seen_at.strftime("%H:%M:%S")
        return arrival > reference

    def _checkout_reference_time(self, profile, date_str):
        class_name = profile.get("class_name") or "Default"
        schedule = self._schedule_for(date_str, class_name)
        return (schedule or {}).get("end_time") or profile.get("check_out_time")

    def _summary_record(self, doc):
        return {
            "id": doc.get("_id"),
            "profile_id": doc.get("profile_id"),
            "name": doc.get("name"),
            "date": doc.get("date"),
            "check_in_time": doc.get("check_in_time"),
            "check_out_time": doc.get("check_out_time"),
            "status": doc.get("status", "absent"),
            "duration_minutes": doc.get("duration_minutes", 0),
            "is_late": bool(doc.get("is_late", False)),
            "continuous_detections": doc.get("continuous_detections", 0),
            "location": doc.get("location"),
        }

    def _profile_row(self, profile, summary=None):
        summary = summary or {}
        status = summary.get("status", "absent")
        return {
            "profile_id": profile["_id"],
            "name": profile["name"],
            "profile_type": profile.get("profile_type", "faculty"),
            "class_name": profile.get("class_name"),
            "section_name": profile.get("section_name"),
            "roll_number": profile.get("roll_number"),
            "status": status,
            "check_in_time": summary.get("check_in_time"),
            "check_out_time": summary.get("check_out_time"),
            "duration_minutes": summary.get("duration_minutes", 0),
            "is_late": bool(summary.get("is_late", False)),
            "continuous_detections": summary.get("continuous_detections", 0),
            "location": summary.get("location"),
            "last_location": summary.get("location"),
            "frame_path": summary.get("frame_path"),
            "camera_id": summary.get("camera_id"),
        }

    def _latest_detection_map(self, date_str, profile_ids=None):
        query = {}
        if profile_ids:
            query["profile_id"] = {"$in": list(profile_ids)}
        if date_str:
            start, end = self._day_bounds(date_str)
            query["timestamp"] = {"$gte": start, "$lt": end}

        latest = {}
        cursor = self._attendance_collection().find(query).sort(
            [("profile_id", 1), ("timestamp", -1)]
        )

        for doc in cursor:
            profile_id = doc.get("profile_id")
            if not profile_id or profile_id in latest:
                continue

            latest[profile_id] = {
                "frame_path": doc.get("frame_path"),
                "location": doc.get("location"),
                "timestamp": doc.get("timestamp"),
                "camera_id": self._camera_id_from_location(doc.get("location")),
            }

        return latest

    def _camera_id_from_location(self, location):
        if not location:
            return None
        try:
            camera = mongo_store.collection("cctv_cameras").find_one(
                {"name": location},
                {"_id": 1},
            )
            return camera.get("_id") if camera else None
        except Exception as exc:
            logger.debug(f"Failed to resolve camera id for location '{location}': {exc}")
            return None

    def log_detection(
        self,
        profile_id,
        name,
        status="present",
        confidence=0.0,
        emotion=LOW_SIGNAL_EMOTION,
        emotion_data=None,
        frame_path=None,
        location=None,
        camera_id=None,
    ):
        try:
            numeric_confidence = float(confidence or 0.0)
            if profile_id and profile_id > 0 and numeric_confidence < self.min_attendance_recognition_confidence:
                logger.warning(
                    "Skipping attendance write below strict recognition floor: "
                    "profile_id=%s name=%s confidence=%.4f required=%.4f",
                    profile_id,
                    name,
                    numeric_confidence,
                    self.min_attendance_recognition_confidence,
                )
                return False
            now = app_now()
            date_str = now.strftime("%Y-%m-%d")
            if profile_id and profile_id > 0:
                if not self.detection_cache.should_log(profile_id):
                    return False
                self.detection_cache.mark_logged(profile_id)

            emotion_data = emotion_data or {}
            resolved_emotion = _display_emotion_label(emotion, emotion_data)
            emotion_confidence = float(
                emotion_data.get("emotion_confidence",
                emotion_data.get("smoothed_confidence",
                emotion_data.get("raw_confidence",
                emotion_data.get("confidence", 0.0))))
            )
            all_emotions = (
                emotion_data.get("all_emotions")
                or emotion_data.get("smoothed_scores")
                or emotion_data.get("raw_scores")
                or emotion_data.get("all_scores")
                or {}
            )
            entry_id = mongo_store.next_id("attendance_log")
            self._attendance_collection().insert_one(
                {
                    "_id": entry_id,
                    "profile_id": profile_id,
                    "name": name,
                    "timestamp": now,
                    "status": status,
                    "confidence": numeric_confidence,
                    "emotion": resolved_emotion,
                    "emotion_confidence": emotion_confidence,
                    "emotion_intensity": emotion_data.get("emotion_intensity", emotion_data.get("intensity", "low")),
                    "all_emotions": all_emotions,
                    "raw_emotion": emotion_data.get("raw_emotion"),
                    "raw_confidence": float(emotion_data.get("raw_confidence") or 0.0),
                    "smoothed_emotion": emotion_data.get("smoothed_emotion"),
                    "smoothed_confidence": float(emotion_data.get("smoothed_confidence") or 0.0),
                    "derived_emotion": emotion_data.get("derived_emotion"),
                    "educational_state": emotion_data.get("educational_state"),
                    "classroom_state": emotion_data.get("classroom_state"),
                    "quality_score": float(emotion_data.get("quality_score") or 0.0),
                    "attention": float(emotion_data.get("attention") or 0.0),
                    "engagement": float(emotion_data.get("engagement") or 0.0),
                    "emotion_model": emotion_data.get("emotion_model"),
                    "pipeline_version": emotion_data.get("pipeline_version"),
                    "low_signal_state": bool(emotion_data.get("low_signal_state")),
                    "quality_band": emotion_data.get("quality_band"),
                    "face_size_px": int(emotion_data.get("face_size_px") or emotion_data.get("face_size") or 0),
                    "preprocess_variant": emotion_data.get("preprocess_variant"),
                    "recovery_stage": emotion_data.get("recovery_stage"),
                    "temporal_consensus": float(emotion_data.get("temporal_consensus") or 0.0),
                    "decision_reason": emotion_data.get("decision_reason"),
                    "weak_match_threshold": float(emotion_data.get("weak_match_threshold") or 0.0),
                    "emotion_unavailable_reason": emotion_data.get("emotion_unavailable_reason"),
                    "legacy_emotion_source": emotion_data.get("legacy_emotion_source"),
                    "frame_path": frame_path,
                    "location": location,
                    "camera_id": camera_id,
                }
            )
            logger.info(
                "Attendance logged: profile_id=%s name=%s status=%s location=%s camera_id=%s confidence=%.3f",
                profile_id,
                name,
                status,
                location or "-",
                camera_id or "-",
                float(numeric_confidence or 0.0),
            )

            if profile_id and profile_id > 0:
                profile = self._get_profile(profile_id) or {"_id": profile_id, "name": name}
                existing = self._attendance_summary_collection().find_one({"profile_id": profile_id, "date": date_str})
                current_time = now.strftime("%H:%M:%S")
                check_in_time = (
                    self._normalize_time_string(existing.get("check_in_time"))
                    if existing and existing.get("check_in_time")
                    else current_time
                )
                existing_checkout_time = (
                    self._normalize_time_string(existing.get("check_out_time"))
                    if existing and existing.get("check_out_time")
                    else None
                )
                checkout_reference = self._checkout_reference_time(profile, date_str)
                checkout_reference_dt = self._parse_time_value(checkout_reference)
                can_set_checkout = (
                    checkout_reference_dt is not None
                    and self._parse_time_value(current_time) is not None
                    and self._parse_time_value(current_time) >= checkout_reference_dt
                )
                check_out_time = existing_checkout_time or (current_time if can_set_checkout else None)
                duration_reference = check_out_time or current_time
                duration_minutes = self._calculate_duration(check_in_time, duration_reference)
                is_late = self._is_late(profile, now, date_str)
                summary_status = "late" if is_late else "present"
                payload = {
                    "profile_id": profile_id,
                    "name": name,
                    "date": date_str,
                    "check_in_time": check_in_time,
                    "check_out_time": check_out_time,
                    "status": summary_status,
                    "duration_minutes": duration_minutes,
                    "is_late": is_late,
                    "continuous_detections": (existing.get("continuous_detections", 0) + 1) if existing else 1,
                    "location": location,
                    "frame_path": frame_path,
                    "camera_id": camera_id,
                    "updated_at": now,
                }
                self._attendance_summary_collection().update_one(
                    {"profile_id": profile_id, "date": date_str},
                    {
                        "$set": payload,
                        "$setOnInsert": {
                            "_id": mongo_store.next_id("attendance_summary"),
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
                logger.info(
                    "Attendance summary updated: profile_id=%s name=%s date=%s check_in=%s check_out=%s status=%s detections=%s",
                    profile_id,
                    name,
                    date_str,
                    check_in_time,
                    check_out_time or "-",
                    summary_status,
                    payload["continuous_detections"],
                )
                self.log_emotion_event(
                    profile_id=profile_id,
                    name=name,
                    location=location,
                    camera_id=camera_id,
                    timestamp=now,
                    frame_path=frame_path,
                    recognition_confidence=numeric_confidence,
                    emotion=emotion,
                    emotion_data=emotion_data,
                )
            return True
        except Exception as exc:
            logger.error(f"Failed to log detection: {exc}")
            return False

    def log_emotion_event(
        self,
        profile_id,
        name,
        location,
        camera_id,
        timestamp,
        frame_path,
        recognition_confidence,
        emotion,
        emotion_data=None,
        unknown_face_id=None,
    ):
        emotion_data = emotion_data or {}
        emotion_confidence = float(
            emotion_data.get("emotion_confidence",
            emotion_data.get("smoothed_confidence",
            emotion_data.get("raw_confidence",
            emotion_data.get("confidence", 0.0))))
        )
        resolved_emotion = _display_emotion_label(emotion, emotion_data)
        if not profile_id and unknown_face_id is None:
            return False
        event_id = mongo_store.next_id("emotion_events")
        self._emotion_events_collection().insert_one(
            {
                "_id": event_id,
                "profile_id": profile_id,
                "unknown_face_id": unknown_face_id,
                "person_id": profile_id if profile_id is not None else f"unknown:{unknown_face_id}",
                "name": name,
                "location": location,
                "camera_id": camera_id,
                "timestamp": timestamp,
                "frame_path": frame_path,
                "recognition_confidence": float(recognition_confidence or 0.0),
                "emotion": resolved_emotion,
                "emotion_confidence": emotion_confidence,
                "below_confidence_threshold": emotion_confidence < self.min_emotion_confidence,
                "emotion_intensity": emotion_data.get("emotion_intensity", emotion_data.get("intensity", "low")),
                "all_emotions": (
                    emotion_data.get("all_emotions")
                    or emotion_data.get("smoothed_scores")
                    or emotion_data.get("raw_scores")
                    or emotion_data.get("all_scores")
                    or {}
                ),
                "raw_emotion": emotion_data.get("raw_emotion", resolved_emotion),
                "raw_confidence": float(emotion_data.get("raw_confidence") or 0.0),
                "raw_scores": emotion_data.get("raw_scores") or emotion_data.get("all_scores") or {},
                "smoothed_emotion": emotion_data.get("smoothed_emotion", resolved_emotion),
                "smoothed_confidence": float(
                    emotion_data.get("smoothed_confidence", emotion_confidence) or 0.0
                ),
                "smoothed_scores": emotion_data.get("smoothed_scores") or {},
                "derived_emotion": emotion_data.get("derived_emotion"),
                "educational_state": emotion_data.get("educational_state"),
                "classroom_state": emotion_data.get("classroom_state"),
                "quality_score": float(emotion_data.get("quality_score") or 0.0),
                "face_size": int(emotion_data.get("face_size") or 0),
                "blur_score": float(emotion_data.get("blur_score") or 0.0),
                "brightness": float(emotion_data.get("brightness") or 0.0),
                "yaw": float(emotion_data.get("yaw") or 0.0),
                "pitch": float(emotion_data.get("pitch") or 0.0),
                "roll": float(emotion_data.get("roll") or 0.0),
                "occlusion_score": float(emotion_data.get("occlusion_score") or 0.0),
                "attention": float(emotion_data.get("attention") or 0.0),
                "engagement": float(emotion_data.get("engagement") or 0.0),
                "quality_band": emotion_data.get("quality_band"),
                "face_size_px": int(emotion_data.get("face_size_px") or emotion_data.get("face_size") or 0),
                "preprocess_variant": emotion_data.get("preprocess_variant"),
                "recovery_stage": emotion_data.get("recovery_stage"),
                "emotion_model": emotion_data.get("emotion_model"),
                "reasoning_model": emotion_data.get("reasoning_model"),
                "pipeline_version": emotion_data.get("pipeline_version"),
                "reasoning": emotion_data.get("reasoning"),
                "emotion_provider": emotion_data.get("emotion_provider"),
                "low_quality": bool(emotion_data.get("low_quality")),
                "below_analytics_threshold": bool(emotion_data.get("below_analytics_threshold")),
                "fallback_backend_used": bool(emotion_data.get("fallback_backend_used")),
                "low_signal_state": bool(emotion_data.get("low_signal_state")),
                "temporal_consensus": float(emotion_data.get("temporal_consensus") or 0.0),
                "history_size": int(emotion_data.get("history_size") or 0),
                "decision_reason": emotion_data.get("decision_reason"),
                "weak_match_threshold": float(emotion_data.get("weak_match_threshold") or 0.0),
                "emotion_unavailable_reason": emotion_data.get("emotion_unavailable_reason"),
                "legacy_emotion_source": emotion_data.get("legacy_emotion_source"),
                "date": timestamp.strftime("%Y-%m-%d") if isinstance(timestamp, datetime) else None,
                "created_at": app_now(),
            }
        )
        return True

    def clear_frame_path_references(self, frame_paths):
        try:
            if not frame_paths:
                return True
            self._attendance_collection().update_many(
                {"frame_path": {"$in": list(frame_paths)}},
                {"$set": {"frame_path": None}},
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to clear frame references: {exc}")
            return False

    def log_stream_detections(self, detections, location=None):
        try:
            for detection in detections:
                self.log_activity(
                    profile_id=detection.get("profile_id"),
                    name=detection.get("name", "Unknown"),
                    activity=detection.get("activity", "Detected"),
                    activity_confidence=detection.get("activity_confidence", 0.0),
                    emotion=detection.get("emotion", "Neutral"),
                    emotion_confidence=detection.get("emotion_confidence", 0.0),
                    location=location,
                    unknown_face_id=detection.get("unknown_face_id"),
                )
            return True
        except Exception as exc:
            logger.error(f"Failed to log stream detections: {exc}")
            return False

    def log_activity(self, profile_id, name, activity, activity_confidence, emotion, emotion_confidence, location=None, unknown_face_id=None):
        try:
            if not self.activity_cache.should_log(profile_id, unknown_face_id, location):
                return False
            now = app_now()
            date_str = now.strftime("%Y-%m-%d")
            log_id = mongo_store.next_id("activity_log")
            self._activity_collection().insert_one(
                {
                    "_id": log_id,
                    "profile_id": profile_id,
                    "unknown_face_id": unknown_face_id,
                    "name": name,
                    "activity": activity,
                    "activity_confidence": activity_confidence,
                    "emotion": emotion,
                    "emotion_confidence": emotion_confidence,
                    "location": location,
                    "timestamp": now,
                    "date": date_str,
                }
            )
            self._activity_cache_summary(profile_id, unknown_face_id, name, activity, location, now)
            self.activity_cache.mark_logged(profile_id, unknown_face_id, location, activity)
            return True
        except Exception as exc:
            logger.error(f"Failed to log activity: {exc}")
            return False

    def log_class_activity(self, activity_payload):
        try:
            if not activity_payload:
                return False
            camera_id = activity_payload.get("camera_id")
            student_label = activity_payload.get("student_activity_label")
            faculty_label = activity_payload.get("faculty_activity_label")
            context_label = activity_payload.get("context_label")
            if not self.class_activity_cache.should_log(camera_id, student_label, faculty_label, context_label):
                return False

            now = activity_payload.get("timestamp") if isinstance(activity_payload.get("timestamp"), datetime) else app_now()
            date_str = now.strftime("%Y-%m-%d")
            payload = dict(activity_payload)
            payload["_id"] = mongo_store.next_id("class_activity_log")
            payload["date"] = date_str
            payload["timestamp"] = now
            self._class_activity_collection().insert_one(payload)

            summary_key = {
                "camera_id": camera_id,
                "date": date_str,
                "class_name": payload.get("class_name"),
                "section_name": payload.get("section_name"),
            }
            existing = self._class_activity_summary_collection().find_one(summary_key)
            update_doc = {
                "$set": {
                    "location": payload.get("location"),
                    "camera_context": payload.get("camera_context"),
                    "updated_at": now,
                    "student_activity_label": payload.get("student_activity_label"),
                    "student_activity_confidence": payload.get("student_activity_confidence"),
                    "faculty_activity_label": payload.get("faculty_activity_label"),
                    "faculty_activity_confidence": payload.get("faculty_activity_confidence"),
                    "context_label": payload.get("context_label"),
                    "context_confidence": payload.get("context_confidence"),
                    "recognized_student_count": payload.get("recognized_student_count", 0),
                    "recognized_faculty_count": payload.get("recognized_faculty_count", 0),
                    "unknown_count": payload.get("unknown_count", 0),
                    "activity_version": payload.get("activity_version"),
                    "last_window_started_at": payload.get("window_started_at"),
                    "last_window_ended_at": payload.get("window_ended_at"),
                },
                "$inc": {"window_count": 1},
            }
            if existing:
                self._class_activity_summary_collection().update_one({"_id": existing["_id"]}, update_doc)
            else:
                create_doc = dict(summary_key)
                create_doc.update(
                    {
                        "_id": mongo_store.next_id("class_activity_summary"),
                        "created_at": now,
                        "window_count": 0,
                    }
                )
                self._class_activity_summary_collection().insert_one(create_doc)
                self._class_activity_summary_collection().update_one({"_id": create_doc["_id"]}, update_doc)

            self.class_activity_cache.mark_logged(camera_id, student_label, faculty_label, context_label)
            return True
        except Exception as exc:
            logger.error(f"Failed to log class activity: {exc}")
            return False

    def get_class_activity_windows(self, location=None, start_time=None, end_time=None, class_name=None, section_name=None):
        try:
            query = {}
            if location:
                query["location"] = location
            if class_name:
                query["class_name"] = class_name
            if section_name:
                query["section_name"] = section_name
            if start_time or end_time:
                timestamp_query = {}
                if start_time:
                    timestamp_query["$gte"] = start_time
                if end_time:
                    timestamp_query["$lt"] = end_time
                query["timestamp"] = timestamp_query
            return list(self._class_activity_collection().find(query).sort("timestamp", 1))
        except Exception as exc:
            logger.error(f"Failed to get class activity windows: {exc}")
            return []

    def _activity_cache_summary(self, profile_id, unknown_face_id, name, activity, location, now):
        if profile_id is None and unknown_face_id is not None:
            return
        date_str = now.strftime("%Y-%m-%d")
        key = {
            "profile_id": profile_id,
            "unknown_face_id": unknown_face_id,
            "date": date_str,
            "location": location,
            "activity": activity,
        }
        existing = self._activity_summary_collection().find_one(key)
        if existing:
            self._activity_summary_collection().update_one(
                {"_id": existing["_id"]},
                {"$inc": {"count": 1}, "$set": {"updated_at": now, "name": name}},
            )
        else:
            payload = dict(key)
            payload.update(
                {
                    "_id": mongo_store.next_id("activity_summary"),
                    "name": name,
                    "count": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            self._activity_summary_collection().insert_one(payload)

    def _daily_summaries(self, date_str):
        cursor = self._attendance_summary_collection().find({"date": date_str}).sort("name", 1)
        return [self._summary_record(doc) for doc in cursor]

    def get_today_presence(self):
        return self.get_daily_report(app_now().strftime("%Y-%m-%d"))

    def get_daily_report(self, date_str=None):
        date_str = date_str or app_now().strftime("%Y-%m-%d")
        try:
            profiles = list(self._profiles_collection().find().sort("name", 1))
            summaries = {row["profile_id"]: row for row in self._daily_summaries(date_str)}
            latest_detections = self._latest_detection_map(
                date_str,
                profile_ids=[profile["_id"] for profile in profiles],
            )
            records = []
            for profile in profiles:
                profile_id = profile["_id"]
                merged_summary = {
                    **(summaries.get(profile_id) or {}),
                    **(latest_detections.get(profile_id) or {}),
                }
                records.append(self._profile_row(profile, merged_summary))
            present_count = sum(1 for row in records if row["status"] in {"present", "late"})
            late_count = sum(1 for row in records if row["status"] == "late")
            absent_count = len(records) - present_count
            attendance_rate = round((present_count / len(records)) * 100, 2) if records else 0.0
            return {
                "date": date_str,
                "total_registered": len(records),
                "present_count": present_count,
                "absent_count": absent_count,
                "late_count": late_count,
                "attendance_rate": attendance_rate,
                "records": records,
            }
        except Exception as exc:
            logger.error(f"Failed to get daily report: {exc}")
            return {"date": date_str, "total_registered": 0, "present_count": 0, "absent_count": 0, "late_count": 0, "attendance_rate": 0.0, "records": []}

    def get_weekly_summary(self):
        try:
            today = app_now().date()
            days = []
            for offset in range(6, -1, -1):
                current = (today - timedelta(days=offset)).isoformat()
                report = self.get_daily_report(current)
                days.append(
                    {
                        "date": current,
                        "present_count": report["present_count"],
                        "absent_count": report["absent_count"],
                        "late_count": report["late_count"],
                        "attendance_rate": report["attendance_rate"],
                    }
                )
            return {
                "week_start": days[0]["date"] if days else None,
                "week_end": days[-1]["date"] if days else None,
                "days": days,
            }
        except Exception as exc:
            logger.error(f"Failed to get weekly summary: {exc}")
            return {"week_start": None, "week_end": None, "days": []}

    def get_attendance_summary_range(self, start_date=None, end_date=None):
        start_date = start_date or app_now().strftime("%Y-%m-%d")
        end_date = end_date or start_date
        try:
            start, _ = self._day_bounds(start_date)
            _, end = self._day_bounds(end_date)
            rows = list(
                self._attendance_summary_collection().find(
                    {
                        "date": {
                            "$gte": start_date,
                            "$lte": end_date,
                        }
                    }
                ).sort([("date", 1), ("name", 1)])
            )
            summaries = [self._summary_record(doc) for doc in rows]
            present_count = sum(1 for row in summaries if row["status"] in {"present", "late"})
            late_count = sum(1 for row in summaries if row["status"] == "late")
            return {
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
                "record_count": len(summaries),
                "present_count": present_count,
                "late_count": late_count,
                "records": summaries,
            }
        except Exception as exc:
            logger.error(f"Failed to get attendance summary range: {exc}")
            return {"start_date": start_date, "end_date": end_date, "record_count": 0, "present_count": 0, "late_count": 0, "records": []}

    def _format_seconds_to_hhmmss(self, total_seconds):
        total_seconds = int(total_seconds or 0)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _average_time_string(self, time_values):
        seconds = []
        for value in time_values:
            if not value:
                continue
            try:
                hour, minute, second = [int(part) for part in str(value).split(":")[:3]]
                seconds.append(hour * 3600 + minute * 60 + second)
            except Exception:
                continue
        if not seconds:
            return None
        return self._format_seconds_to_hhmmss(sum(seconds) / len(seconds))

    def get_attendance_dashboard_analytics(self, dashboard_date=None, start_date=None, end_date=None, role_scope="faculty", class_name=None, section_name=None):
        selected_date = dashboard_date or app_now().strftime("%Y-%m-%d")
        selected_start = start_date or selected_date
        selected_end = end_date or selected_date
        try:
            profile_query = {}
            normalized_role_scope = (role_scope or "faculty").strip().lower()
            if normalized_role_scope == "student":
                profile_query["profile_type"] = "student"
                if class_name:
                    profile_query["class_name"] = class_name
                if section_name:
                    profile_query["section_name"] = section_name
            else:
                profile_query["profile_type"] = {"$ne": "student"}

            profiles = list(self._profiles_collection().find(profile_query).sort("name", 1))
            profile_ids = {profile["_id"] for profile in profiles}
            selected_day = self.get_daily_report(selected_date)
            range_rows = list(
                self._attendance_summary_collection().find(
                    {"date": {"$gte": selected_start, "$lte": selected_end}, "profile_id": {"$in": list(profile_ids)}}
                )
            )
            present_count = sum(1 for row in selected_day["records"] if row["profile_id"] in profile_ids and row["status"] in {"present", "late"})
            absent_count = len(profiles) - present_count
            late_count = sum(1 for row in selected_day["records"] if row["profile_id"] in profile_ids and row["status"] == "late")
            avg_duration = round(
                sum(row.get("duration_minutes", 0) for row in range_rows) / len(range_rows), 2
            ) if range_rows else 0.0
            unique_present = len({row["profile_id"] for row in range_rows})
            return {
                "date": selected_date,
                "start_date": selected_start,
                "end_date": selected_end,
                "role_scope": normalized_role_scope,
                "class_name": class_name,
                "section_name": section_name,
                "total_registered": len(profiles),
                "present_count": present_count,
                "absent_count": absent_count,
                "late_count": late_count,
                "attendance_rate": round((present_count / len(profiles)) * 100, 2) if profiles else 0.0,
                "average_duration_minutes": avg_duration,
                "unique_present_count": unique_present,
                "records": [row for row in selected_day["records"] if row["profile_id"] in profile_ids],
            }
        except Exception as exc:
            logger.error(f"Failed to get dashboard analytics: {exc}")
            return {"date": selected_date, "start_date": selected_start, "end_date": selected_end, "role_scope": role_scope, "class_name": class_name, "section_name": section_name, "total_registered": 0, "present_count": 0, "absent_count": 0, "late_count": 0, "attendance_rate": 0.0, "average_duration_minutes": 0.0, "unique_present_count": 0, "records": []}

    def get_check_in_check_out(self, date_str=None):
        report = self.get_daily_report(date_str)
        return {
            "date": report["date"],
            "records": [
                {
                    "profile_id": row["profile_id"],
                    "name": row["name"],
                    "check_in_time": row["check_in_time"],
                    "check_out_time": row["check_out_time"],
                    "duration_minutes": row["duration_minutes"],
                    "status": row["status"],
                    "frame_path": row.get("frame_path"),
                    "camera_id": row.get("camera_id"),
                    "location": row.get("location"),
                    "last_location": row.get("last_location"),
                }
                for row in report["records"]
            ],
        }

    def _calculate_duration(self, check_in_str, check_out_str):
        if not check_in_str or not check_out_str:
            return 0
        try:
            check_in = self._parse_time_value(check_in_str)
            check_out = self._parse_time_value(check_out_str)
            if not check_in or not check_out:
                return 0
            return max(0, int((check_out - check_in).total_seconds() / 60))
        except Exception:
            return 0

    def get_continuous_presence_report(self, min_detections=5):
        try:
            rows = list(
                self._attendance_summary_collection().find(
                    {"continuous_detections": {"$gte": min_detections}}
                ).sort([("date", -1), ("continuous_detections", -1)])
            )
            return {
                "min_detections": min_detections,
                "records": [self._summary_record(doc) for doc in rows],
            }
        except Exception as exc:
            logger.error(f"Failed to get continuous presence report: {exc}")
            return {"min_detections": min_detections, "records": []}

    def get_absent_members(self, date_str=None):
        report = self.get_daily_report(date_str)
        absent = [row for row in report["records"] if row["status"] == "absent"]
        return {"date": report["date"], "records": absent, "count": len(absent)}

    def set_class_schedule(self, date_str, start_time, end_time, class_name="Default"):
        try:
            existing = self._schedule_collection().find_one({"date": date_str, "class_name": class_name})
            if existing:
                self._schedule_collection().update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"start_time": start_time, "end_time": end_time, "updated_at": app_now()}},
                )
            else:
                self._schedule_collection().insert_one(
                    {
                        "_id": mongo_store.next_id("class_schedule"),
                        "date": date_str,
                        "class_name": class_name,
                        "start_time": start_time,
                        "end_time": end_time,
                        "created_at": app_now(),
                    }
                )
            return True
        except Exception as exc:
            logger.error(f"Failed to set class schedule: {exc}")
            return False

    def get_late_arrivals(self, date_str=None):
        date_str = date_str or app_now().strftime("%Y-%m-%d")
        try:
            cursor = self._attendance_summary_collection().find(
                {"date": date_str, "is_late": True}
            ).sort("name", 1)
            rows = [self._summary_record(doc) for doc in cursor]
            for row in rows:
                row["minutes_late"] = self._minutes_late(row.get("check_in_time"), self._late_reference_time(row["profile_id"], date_str))
            return {"date": date_str, "records": rows, "count": len(rows)}
        except Exception as exc:
            logger.error(f"Failed to get late arrivals: {exc}")
            return {"date": date_str, "records": [], "count": 0}

    def _late_reference_time(self, profile_id, date_str):
        profile = self._get_profile(profile_id) or {}
        class_name = profile.get("class_name") or "Default"
        schedule = self._schedule_for(date_str, class_name)
        return (schedule or {}).get("start_time") or profile.get("check_in_time")

    def _minutes_late(self, arrival_time, class_start):
        if not arrival_time or not class_start:
            return 0
        try:
            arrival = datetime.strptime(arrival_time, "%H:%M:%S")
            start = datetime.strptime(class_start, "%H:%M:%S")
            return max(0, int((arrival - start).total_seconds() / 60))
        except Exception:
            return 0

    def export_attendance_csv(self, date_str=None):
        report = self.get_daily_report(date_str)
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=["profile_id", "name", "profile_type", "class_name", "section_name", "roll_number", "status", "check_in_time", "check_out_time", "duration_minutes", "is_late", "location"],
        )
        writer.writeheader()
        writer.writerows(report["records"])
        return buffer.getvalue()

    def export_attendance_summary_csv(self, start_date=None, end_date=None):
        report = self.get_attendance_summary_range(start_date, end_date)
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=["profile_id", "name", "date", "check_in_time", "check_out_time", "status", "duration_minutes", "is_late", "continuous_detections", "location"],
        )
        writer.writeheader()
        writer.writerows(report["records"])
        return buffer.getvalue()

    def export_attendance_pdf(self, date_str=None):
        report = self.get_daily_report(date_str)
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
            from reportlab.lib import colors
        except Exception:
            logger.warning("reportlab not installed - PDF export unavailable")
            return None

        fd, path = tempfile.mkstemp(prefix="chronosense-attendance-", suffix=".pdf")
        os.close(fd)
        data = [["Name", "Status", "Check In", "Check Out", "Duration", "Location"]]
        for row in report["records"]:
            data.append(
                [
                    row["name"],
                    row["status"],
                    row.get("check_in_time") or "-",
                    row.get("check_out_time") or "-",
                    str(row.get("duration_minutes", 0)),
                    row.get("location") or "-",
                ]
            )
        doc = SimpleDocTemplate(path, pagesize=letter)
        table = Table(data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        doc.build([table])
        return path

    def update_check_in_out_times(self, profile_id, date_str, check_in_time, check_out_time):
        try:
            duration_minutes = self._calculate_duration(check_in_time, check_out_time)
            result = self._attendance_summary_collection().update_one(
                {"profile_id": profile_id, "date": date_str},
                {
                    "$set": {
                        "check_in_time": check_in_time,
                        "check_out_time": check_out_time,
                        "duration_minutes": duration_minutes,
                        "updated_at": app_now(),
                    }
                },
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update check in/out times: {exc}")
            return False
