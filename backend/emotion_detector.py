"""
FERPlus-based emotion detection and Mongo-backed analytics.
"""

import cv2
import numpy as np
import logging
import threading
from collections import Counter
from datetime import datetime

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store

logger = logging.getLogger(__name__)

EMOTION_LABELS = ["Neutral", "Happy", "Surprise", "Sad", "Angry", "Disgust", "Fear", "Contempt"]


class FERPlusEmotionDetector:
    def __init__(self):
        self.model = None
        self._lock = threading.Lock()
        self.model_loaded = False
        self.last_error = None
        self._load_model()

    def _load_model(self):
        try:
            import os

            model_path = os.path.join(os.path.dirname(__file__), "models", "emotion-ferplus-8.onnx")
            if os.path.exists(model_path):
                self.model = cv2.dnn.readNetFromONNX(model_path)
                self.model_loaded = True
                logger.info("✓ FERPlus ONNX emotion model loaded")
            else:
                self.model_loaded = False
                self.last_error = f"FERPlus model not found at {model_path}"
                logger.warning(f"FERPlus model not found at {model_path}, using heuristic fallback")
        except Exception as exc:
            self.model_loaded = False
            self.last_error = str(exc)
            logger.warning(f"Could not load FERPlus model: {exc}, using heuristic fallback")
            self.model = None

    def detect_emotion(self, frame, bbox):
        try:
            x, y, w, h = [int(v) for v in bbox]
            fh, fw = frame.shape[:2]
            x = max(0, x)
            y = max(0, y)
            w = min(w, fw - x)
            h = min(h, fh - y)
            if w < 10 or h < 10:
                return self._default_result()
            face_roi = frame[y : y + h, x : x + w]
            return self._predict_onnx(face_roi) if self.model is not None else self._predict_heuristic(face_roi)
        except Exception as exc:
            logger.debug(f"Emotion detection error: {exc}")
            return self._default_result()

    def _predict_onnx(self, face_roi):
        try:
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (64, 64))
            blob = cv2.dnn.blobFromImage(resized, 1.0 / 255.0, (64, 64), 0, swapRB=False, crop=False)
            with self._lock:
                self.model.setInput(blob)
                output = self.model.forward()
            scores = self._softmax(output[0])
            all_scores = {label: float(round(score, 4)) for label, score in zip(EMOTION_LABELS, scores)}
            best_idx = int(np.argmax(scores))
            emotion = EMOTION_LABELS[best_idx]
            confidence = float(scores[best_idx])
            return {
                "emotion": emotion,
                "confidence": round(confidence, 4),
                "intensity": self._confidence_to_intensity(confidence),
                "all_scores": all_scores,
            }
        except Exception as exc:
            logger.debug(f"ONNX prediction error: {exc}")
            return self._predict_heuristic(face_roi)

    def _predict_heuristic(self, face_roi):
        try:
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY) if len(face_roi.shape) == 3 else face_roi
            mean_val = np.mean(gray)
            std_val = np.std(gray)
            if std_val > 60:
                emotion = "Surprise"
                confidence = min(0.55 + std_val / 500, 0.85)
            elif mean_val > 140:
                emotion = "Happy"
                confidence = min(0.5 + mean_val / 500, 0.80)
            elif mean_val < 80:
                emotion = "Sad"
                confidence = min(0.45 + (130 - mean_val) / 300, 0.75)
            else:
                emotion = "Neutral"
                confidence = 0.60
            all_scores = {label: 0.02 for label in EMOTION_LABELS}
            all_scores[emotion] = round(confidence, 4)
            remaining = 1.0 - confidence
            for label in EMOTION_LABELS:
                if label != emotion:
                    all_scores[label] = round(remaining / (len(EMOTION_LABELS) - 1), 4)
            return {
                "emotion": emotion,
                "confidence": round(confidence, 4),
                "intensity": self._confidence_to_intensity(confidence),
                "all_scores": all_scores,
            }
        except Exception:
            return self._default_result()

    @staticmethod
    def _softmax(x):
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()

    @staticmethod
    def _confidence_to_intensity(confidence):
        if confidence >= 0.7:
            return "high"
        if confidence >= 0.4:
            return "medium"
        return "low"

    @staticmethod
    def _default_result():
        return {
            "emotion": "Neutral",
            "confidence": 0.0,
            "intensity": "low",
            "all_scores": {label: 0.0 for label in EMOTION_LABELS},
        }


class EmotionAnalytics:
    def __init__(self, db_path):
        self.db_path = db_path
        mongo_store.ensure_connected()
        self.collection = mongo_store.collection("emotion_events")
        self.analytics_quality_threshold = float(
            __import__("os").environ.get("CHRONOSENSE_EMOTION_ANALYTICS_QUALITY_THRESHOLD", "0.32")
        )

    @staticmethod
    def _time_bounds(date):
        return (
            datetime.fromisoformat(f"{date}T00:00:00"),
            datetime.fromisoformat(f"{date}T23:59:59.999999"),
        )

    @staticmethod
    def _coalesce_emotion(row, key, fallback_key="emotion"):
        return row.get(key) or row.get(fallback_key)

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _resolve_location(row):
        location = row.get("location")
        if location:
            return location
        camera_id = row.get("camera_id")
        if camera_id not in (None, ""):
            return f"Camera {camera_id}"
        return "Unknown Location"

    def _is_analytics_usable(self, row):
        if row.get("low_signal_state"):
            return False
        if row.get("below_analytics_threshold"):
            return False
        if self._safe_float(row.get("emotion_confidence")) <= 0.0:
            return False
        return self._safe_float(row.get("quality_score")) >= self.analytics_quality_threshold or row.get("quality_score") is None

    def _usable_emotion(self, row, key="smoothed_emotion", fallback_key="emotion"):
        if not self._is_analytics_usable(row):
            return None
        return self._coalesce_emotion(row, key, fallback_key)

    def _measured_emotion(self, row, key="smoothed_emotion", fallback_key="emotion"):
        emotion = self._usable_emotion(row, key=key, fallback_key=fallback_key)
        if emotion:
            return emotion
        raw_emotion = row.get("raw_emotion")
        if raw_emotion and raw_emotion != "LowSignal":
            return raw_emotion
        fallback_emotion = row.get(fallback_key)
        if fallback_emotion and fallback_emotion != "LowSignal":
            return fallback_emotion
        return None

    @staticmethod
    def _displayable_raw_emotion(row, fallback=None):
        raw_emotion = row.get("raw_emotion")
        if raw_emotion and raw_emotion != "LowSignal":
            return raw_emotion
        if fallback and fallback != "LowSignal":
            return fallback
        if row.get("raw_emotion") == "LowSignal" or fallback == "LowSignal":
            return "Neutral"
        return None

    def _query_rows(self, start=None, end=None, profile_list=None, profile_id=None, location=None):
        match = {
            "location": {"$ne": "Local Webcam"},
            "camera_id": {"$ne": "local_webcam"},
        }
        if start is not None and end is not None:
            match["timestamp"] = {"$gte": start, "$lt": end}
        if profile_id is not None:
            match["profile_id"] = profile_id
        elif profile_list:
            match["profile_id"] = {"$in": list(profile_list)}
        if location:
            match["location"] = location
        return list(self.collection.find(match).sort("timestamp", 1))

    @staticmethod
    def _counter_to_percentages(counter):
        total = sum(counter.values()) or 1
        return {key: round((value / total) * 100, 1) for key, value in counter.items()}

    def get_day_wise_distribution(self, date, profile_list=None):
        start, end = self._time_bounds(date)
        rows = self._query_rows(start=start, end=end, profile_list=profile_list)
        distribution = {}
        total = 0
        for row in rows:
            profile_id = row.get("profile_id")
            if not profile_id:
                continue
            pid = str(profile_id)
            total += 1
            distribution.setdefault(
                pid,
                {
                    "name": row.get("name"),
                    "emotions": {},
                    "raw_emotions": {},
                    "derived_emotions": {},
                    "educational_states": {},
                    "dominant_emotion": None,
                    "dominant_raw_emotion": None,
                    "dominant_derived_emotion": None,
                    "dominant_educational_state": None,
                    "average_confidence": 0.0,
                    "average_quality": 0.0,
                    "average_attention": 0.0,
                    "average_engagement": 0.0,
                    "total_detections": 0,
                    "usable_detections": 0,
                    "low_signal_detections": 0,
                },
            )
            entry = distribution[pid]
            previous_total = entry["total_detections"]
            entry["total_detections"] += 1
            emotion = self._measured_emotion(row, "smoothed_emotion")
            raw_emotion = self._displayable_raw_emotion(row, emotion)
            derived = row.get("derived_emotion")
            educational = row.get("educational_state")
            if emotion:
                entry["emotions"][emotion] = entry["emotions"].get(emotion, 0) + 1
            if raw_emotion:
                entry["raw_emotions"][raw_emotion] = entry["raw_emotions"].get(raw_emotion, 0) + 1
            if derived:
                entry["derived_emotions"][derived] = entry["derived_emotions"].get(derived, 0) + 1
            if educational:
                entry["educational_states"][educational] = entry["educational_states"].get(educational, 0) + 1
            if self._is_analytics_usable(row):
                entry["usable_detections"] += 1
            else:
                entry["low_signal_detections"] += 1
            avg_conf = self._safe_float(row.get("smoothed_confidence", row.get("emotion_confidence")))
            entry["average_confidence"] = round(
                ((entry["average_confidence"] * previous_total) + avg_conf) / entry["total_detections"],
                4,
            )
            avg_quality = self._safe_float(row.get("quality_score"))
            entry["average_quality"] = round(
                ((entry["average_quality"] * previous_total) + avg_quality) / entry["total_detections"],
                4,
            )
            avg_attention = self._safe_float(row.get("attention"))
            entry["average_attention"] = round(
                ((entry["average_attention"] * previous_total) + avg_attention) / entry["total_detections"],
                4,
            )
            avg_engagement = self._safe_float(row.get("engagement"))
            entry["average_engagement"] = round(
                ((entry["average_engagement"] * previous_total) + avg_engagement) / entry["total_detections"],
                4,
            )
        for entry in distribution.values():
            if entry["emotions"]:
                entry["dominant_emotion"] = max(entry["emotions"], key=entry["emotions"].get)
            if entry["raw_emotions"]:
                entry["dominant_raw_emotion"] = max(entry["raw_emotions"], key=entry["raw_emotions"].get)
            if entry["derived_emotions"]:
                entry["dominant_derived_emotion"] = max(entry["derived_emotions"], key=entry["derived_emotions"].get)
            if entry["educational_states"]:
                entry["dominant_educational_state"] = max(entry["educational_states"], key=entry["educational_states"].get)
        return {"date": date, "total_detections": total, "distribution": distribution}

    def get_session_wise_distribution(self, session_id=None, course_id=None):
        rows = list(self.collection.find({}).sort("timestamp", 1))
        emotion_totals = Counter()
        student_emotions = {}
        for row in rows:
            emotion = self._measured_emotion(row, "smoothed_emotion")
            if emotion is None:
                continue
            sid = str(row.get("profile_id")) if row.get("profile_id") else row.get("name")
            emotion_totals[emotion] += 1
            student_emotions.setdefault(
                sid,
                {"name": row.get("name"), "emotions": {}, "derived_emotions": {}, "dominant_emotion": None},
            )
            student_emotions[sid]["emotions"][emotion] = student_emotions[sid]["emotions"].get(emotion, 0) + 1
            derived = row.get("derived_emotion")
            if derived:
                student_emotions[sid]["derived_emotions"][derived] = student_emotions[sid]["derived_emotions"].get(derived, 0) + 1
        for entry in student_emotions.values():
            if entry["emotions"]:
                entry["dominant_emotion"] = max(entry["emotions"], key=entry["emotions"].get)
            if entry["derived_emotions"]:
                entry["dominant_derived_emotion"] = max(entry["derived_emotions"], key=entry["derived_emotions"].get)
        avg_mood, class_sentiment = self._compute_mood(emotion_totals)
        return {
            "session_id": session_id,
            "emotion_distribution": dict(emotion_totals),
            "student_emotions": student_emotions,
            "average_mood": avg_mood,
            "class_sentiment": class_sentiment,
        }

    def get_emotion_trends(self, start_date, end_date, profile_id=None):
        rows = self._query_rows(
            start=datetime.fromisoformat(f"{start_date}T00:00:00"),
            end=datetime.fromisoformat(f"{end_date}T23:59:59.999999"),
            profile_id=profile_id,
        )
        daily_trends = {}
        daily_raw_trends = {}
        overall = Counter()
        overall_raw = Counter()
        derived_overall = Counter()
        educational_overall = Counter()
        classroom_overall = Counter()
        quality_total = 0.0
        attention_total = 0.0
        engagement_total = 0.0
        usable = 0
        for row in rows:
            timestamp = row.get("timestamp")
            if not timestamp:
                continue
            day = timestamp.strftime("%Y-%m-%d")
            emotion = self._measured_emotion(row, "smoothed_emotion")
            raw_emotion = self._displayable_raw_emotion(row)
            daily_trends.setdefault(day, {})
            daily_raw_trends.setdefault(day, {})
            if emotion:
                daily_trends[day][emotion] = daily_trends[day].get(emotion, 0) + 1
                overall[emotion] += 1
            if raw_emotion:
                daily_raw_trends[day][raw_emotion] = daily_raw_trends[day].get(raw_emotion, 0) + 1
                overall_raw[raw_emotion] += 1
            derived = row.get("derived_emotion")
            educational = row.get("educational_state")
            classroom_state = row.get("classroom_state")
            if derived:
                derived_overall[derived] += 1
            if educational:
                educational_overall[educational] += 1
            if classroom_state:
                classroom_overall[classroom_state] += 1
            quality_total += self._safe_float(row.get("quality_score"))
            attention_total += self._safe_float(row.get("attention"))
            engagement_total += self._safe_float(row.get("engagement"))
            if self._is_analytics_usable(row):
                usable += 1
        most_common = overall.most_common(1)[0][0] if overall else None
        return {
            "date_range": [start_date, end_date],
            "daily_trends": daily_trends,
            "daily_raw_trends": daily_raw_trends,
            "overall_stats": dict(overall),
            "overall_raw_stats": dict(overall_raw),
            "overall_derived_stats": dict(derived_overall),
            "overall_educational_states": dict(educational_overall),
            "classroom_climate_summary": dict(classroom_overall),
            "most_common_emotion": most_common,
            "most_common_raw_emotion": overall_raw.most_common(1)[0][0] if overall_raw else None,
            "dominant_derived_emotion": derived_overall.most_common(1)[0][0] if derived_overall else None,
            "dominant_educational_state": educational_overall.most_common(1)[0][0] if educational_overall else None,
            "dominant_classroom_state": classroom_overall.most_common(1)[0][0] if classroom_overall else None,
            "average_quality": round(quality_total / len(rows), 4) if rows else 0.0,
            "average_attention": round(attention_total / len(rows), 4) if rows else 0.0,
            "average_engagement": round(engagement_total / len(rows), 4) if rows else 0.0,
            "usable_detection_count": usable,
            "low_signal_detection_count": len(rows) - usable,
            "total_detection_count": len(rows),
        }

    def get_location_distribution(self, date=None, location=None):
        start, end = self._time_bounds(date) if date else (None, None)
        rows = self._query_rows(start=start, end=end, location=location)
        locations = {}
        for row in rows:
            loc = self._resolve_location(row)
            entry = locations.setdefault(
                loc,
                {
                    "emotions": {},
                    "raw_emotions": {},
                    "derived_emotions": {},
                    "educational_states": {},
                    "classroom_states": {},
                    "emotion_percentages": {},
                    "raw_emotion_percentages": {},
                    "derived_emotion_percentages": {},
                    "educational_state_percentages": {},
                    "dominant_emotion": None,
                    "dominant_raw_emotion": None,
                    "dominant_derived_emotion": None,
                    "dominant_educational_state": None,
                    "dominant_classroom_state": None,
                    "total_detections": 0,
                    "usable_detections": 0,
                    "low_signal_detections": 0,
                    "average_confidence": 0.0,
                    "average_quality": 0.0,
                    "average_attention": 0.0,
                    "average_engagement": 0.0,
                    "suppressed_low_confidence_count": 0,
                    "last_updated": None,
                },
            )
            previous_total = entry["total_detections"]
            emotion = self._measured_emotion(row, "smoothed_emotion")
            raw_emotion = self._displayable_raw_emotion(row, emotion)
            derived = row.get("derived_emotion")
            educational = row.get("educational_state")
            classroom_state = row.get("classroom_state")
            if emotion:
                entry["emotions"][emotion] = entry["emotions"].get(emotion, 0) + 1
            if raw_emotion:
                entry["raw_emotions"][raw_emotion] = entry["raw_emotions"].get(raw_emotion, 0) + 1
            if derived:
                entry["derived_emotions"][derived] = entry["derived_emotions"].get(derived, 0) + 1
            if educational:
                entry["educational_states"][educational] = entry["educational_states"].get(educational, 0) + 1
            if classroom_state:
                entry["classroom_states"][classroom_state] = entry["classroom_states"].get(classroom_state, 0) + 1
            entry["total_detections"] += 1
            if self._is_analytics_usable(row):
                entry["usable_detections"] += 1
            else:
                entry["low_signal_detections"] += 1
            if self._safe_float(row.get("emotion_confidence")) < 0.45:
                entry["suppressed_low_confidence_count"] += 1
            avg_conf = self._safe_float(row.get("smoothed_confidence", row.get("emotion_confidence")))
            entry["average_confidence"] = round(
                ((entry["average_confidence"] * previous_total) + avg_conf) / max(1, entry["total_detections"]),
                4,
            )
            avg_quality = self._safe_float(row.get("quality_score"))
            entry["average_quality"] = round(
                ((entry["average_quality"] * previous_total) + avg_quality) / max(1, entry["total_detections"]),
                4,
            )
            avg_attention = self._safe_float(row.get("attention"))
            entry["average_attention"] = round(
                ((entry["average_attention"] * previous_total) + avg_attention) / max(1, entry["total_detections"]),
                4,
            )
            avg_engagement = self._safe_float(row.get("engagement"))
            entry["average_engagement"] = round(
                ((entry["average_engagement"] * previous_total) + avg_engagement) / max(1, entry["total_detections"]),
                4,
            )
            last_seen = row.get("timestamp")
            if last_seen and (entry["last_updated"] is None or last_seen > entry["last_updated"]):
                entry["last_updated"] = last_seen
        for entry in locations.values():
            total = entry["total_detections"]
            if total > 0:
                entry["emotion_percentages"] = self._counter_to_percentages(Counter(entry["emotions"]))
                entry["raw_emotion_percentages"] = self._counter_to_percentages(Counter(entry["raw_emotions"]))
                entry["derived_emotion_percentages"] = self._counter_to_percentages(Counter(entry["derived_emotions"]))
                entry["educational_state_percentages"] = self._counter_to_percentages(Counter(entry["educational_states"]))
                if entry["emotions"]:
                    entry["dominant_emotion"] = max(entry["emotions"], key=entry["emotions"].get)
                elif entry["usable_detections"] == 0:
                    entry["dominant_emotion"] = "Neutral"
                if entry["raw_emotions"]:
                    entry["dominant_raw_emotion"] = max(entry["raw_emotions"], key=entry["raw_emotions"].get)
                if entry["derived_emotions"]:
                    entry["dominant_derived_emotion"] = max(entry["derived_emotions"], key=entry["derived_emotions"].get)
                if entry["educational_states"]:
                    entry["dominant_educational_state"] = max(entry["educational_states"], key=entry["educational_states"].get)
                if entry["classroom_states"]:
                    entry["dominant_classroom_state"] = max(entry["classroom_states"], key=entry["classroom_states"].get)
                if entry["last_updated"] is not None:
                    entry["last_updated"] = entry["last_updated"].isoformat()
        return locations

    def get_student_timeline(self, profile_id, start_date, end_date, location=None):
        rows = self._query_rows(
            start=datetime.fromisoformat(f"{start_date}T00:00:00"),
            end=datetime.fromisoformat(f"{end_date}T23:59:59.999999"),
            profile_id=profile_id,
            location=location,
        )
        if not rows:
            return {
                "profile_id": profile_id,
                "start_date": start_date,
                "end_date": end_date,
                "timeline": [],
                "emotion_distribution": {},
                "raw_emotion_distribution": {},
                "derived_emotion_distribution": {},
                "educational_state_distribution": {},
                "dominant_emotion": None,
                "dominant_raw_emotion": None,
                "dominant_derived_emotion": None,
                "dominant_educational_state": None,
                "average_confidence": 0.0,
                "average_quality": 0.0,
                "average_attention": 0.0,
                "average_engagement": 0.0,
                "total_detections": 0,
                "usable_detections": 0,
                "low_signal_detections": 0,
                "locations": [],
                "name": None,
            }
        emotion_totals = Counter()
        raw_totals = Counter()
        derived_totals = Counter()
        educational_totals = Counter()
        confidence_sum = 0.0
        quality_sum = 0.0
        attention_sum = 0.0
        engagement_sum = 0.0
        usable = 0
        locations = set()
        timeline = []
        name = rows[0].get("name")
        for row in rows:
            emotion = self._measured_emotion(row, "smoothed_emotion")
            raw_emotion = self._displayable_raw_emotion(row, emotion)
            derived = row.get("derived_emotion")
            educational = row.get("educational_state")
            if emotion:
                emotion_totals[emotion] += 1
            if raw_emotion:
                raw_totals[raw_emotion] += 1
            if derived:
                derived_totals[derived] += 1
            if educational:
                educational_totals[educational] += 1
            confidence_sum += self._safe_float(row.get("smoothed_confidence", row.get("emotion_confidence")))
            quality_sum += self._safe_float(row.get("quality_score"))
            attention_sum += self._safe_float(row.get("attention"))
            engagement_sum += self._safe_float(row.get("engagement"))
            if self._is_analytics_usable(row):
                usable += 1
            if row.get("location"):
                locations.add(row["location"])
            timeline.append(
                {
                    "timestamp": row["timestamp"].isoformat() if row.get("timestamp") else None,
                    "emotion": emotion,
                    "raw_emotion": raw_emotion,
                    "smoothed_emotion": row.get("smoothed_emotion", emotion),
                    "all_emotions": row.get("all_emotions") or row.get("smoothed_scores") or row.get("raw_scores") or {},
                    "raw_scores": row.get("raw_scores") or row.get("all_emotions") or {},
                    "smoothed_scores": row.get("smoothed_scores") or row.get("all_emotions") or {},
                    "derived_emotion": derived,
                    "educational_state": educational,
                    "classroom_state": row.get("classroom_state"),
                    "emotion_confidence": self._safe_float(row.get("emotion_confidence")),
                    "raw_confidence": self._safe_float(row.get("raw_confidence")),
                    "smoothed_confidence": self._safe_float(row.get("smoothed_confidence")),
                    "emotion_intensity": row.get("emotion_intensity", "low"),
                    "recognition_confidence": self._safe_float(row.get("recognition_confidence")),
                    "quality_score": self._safe_float(row.get("quality_score")),
                    "attention": self._safe_float(row.get("attention")),
                    "engagement": self._safe_float(row.get("engagement")),
                    "low_signal_state": bool(row.get("low_signal_state")),
                    "below_analytics_threshold": bool(row.get("below_analytics_threshold")),
                    "emotion_model": row.get("emotion_model"),
                    "pipeline_version": row.get("pipeline_version"),
                    "location": row.get("location"),
                    "camera_id": row.get("camera_id"),
                    "frame_path": row.get("frame_path"),
                }
            )
        total = len(rows)
        return {
            "profile_id": profile_id,
            "name": name,
            "start_date": start_date,
            "end_date": end_date,
            "timeline": timeline,
            "emotion_distribution": dict(emotion_totals),
            "raw_emotion_distribution": dict(raw_totals),
            "derived_emotion_distribution": dict(derived_totals),
            "educational_state_distribution": dict(educational_totals),
            "dominant_emotion": max(emotion_totals, key=emotion_totals.get) if emotion_totals else None,
            "dominant_raw_emotion": max(raw_totals, key=raw_totals.get) if raw_totals else None,
            "dominant_derived_emotion": max(derived_totals, key=derived_totals.get) if derived_totals else None,
            "dominant_educational_state": max(educational_totals, key=educational_totals.get) if educational_totals else None,
            "average_confidence": round(confidence_sum / total, 4) if total else 0.0,
            "average_quality": round(quality_sum / total, 4) if total else 0.0,
            "average_attention": round(attention_sum / total, 4) if total else 0.0,
            "average_engagement": round(engagement_sum / total, 4) if total else 0.0,
            "total_detections": total,
            "usable_detections": usable,
            "low_signal_detections": total - usable,
            "locations": sorted(locations),
        }

    @staticmethod
    def _compute_mood(emotion_counts):
        positive = sum(emotion_counts.get(e, 0) for e in ("Happy", "Surprise"))
        negative = sum(emotion_counts.get(e, 0) for e in ("Sad", "Angry", "Disgust", "Fear"))
        neutral = emotion_counts.get("Neutral", 0) + emotion_counts.get("Contempt", 0)
        total = positive + negative + neutral or 1
        if positive / total > 0.5:
            return "Positive", "Students appear engaged and positive"
        if negative / total > 0.4:
            return "Negative", "Students may be disengaged or stressed"
        return "Neutral", "Class mood is mostly neutral"
