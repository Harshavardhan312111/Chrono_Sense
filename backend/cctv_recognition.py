"""
CCTV Camera Face Recognition Engine
Real-time face detection, recognition, and attendance logging from CCTV streams
Integrates with existing AI engine, database, and attendance system
"""

import cv2
import numpy as np
import json
import threading
import time
import logging
import base64
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store

try:
    from recognition_runtime import set_latest_detections, set_runtime_state
except ImportError:
    from backend.recognition_runtime import set_latest_detections, set_runtime_state

try:
    from class_activity_pipeline import ClassActivityPipeline
except ImportError:
    from backend.class_activity_pipeline import ClassActivityPipeline

logger = logging.getLogger(__name__)
SNAPSHOT_RETENTION_HOURS = 24
MAX_UNKNOWN_SNAPSHOTS_PER_CAMERA = 20
UNKNOWN_PERSISTENCE_MIN_FRAMES = 3
UNKNOWN_PERSISTENCE_MIN_SECONDS = 1.0
ATTENDANCE_RECOGNITION_FLOOR = 0.39
EMOTION_INFERENCE_WIDTH_FLOOR = 1280


def build_camera_source_url(source, camera_type=None, username=None, password=None):
    source = (source or "").strip()
    if not source or not username or password is None:
        return source

    normalized_type = (camera_type or "").strip().lower()
    if normalized_type not in ["rtsp", "mjpeg", "http"]:
        return source

    if "://" not in source:
        return source

    protocol, rest = source.split("://", 1)
    host_and_path = rest.rsplit("@", 1)[-1]
    encoded_username = quote(str(username), safe="")
    encoded_password = quote(str(password), safe="")
    return f"{protocol}://{encoded_username}:{encoded_password}@{host_and_path}"

# Try to import emotion pipeline
try:
    from emotion_pipeline import EmotionPipeline, LOW_SIGNAL_EMOTION, PIPELINE_VERSION
    EMOTION_DETECTION_AVAILABLE = True
except ImportError:
    try:
        from backend.emotion_pipeline import EmotionPipeline, LOW_SIGNAL_EMOTION, PIPELINE_VERSION
        EMOTION_DETECTION_AVAILABLE = True
    except ImportError:
        EMOTION_DETECTION_AVAILABLE = False
        logger.warning("⚠️ Emotion pipeline not available - emotion detection will be skipped")

# Try to import activity detector (Lightweight OpenCV-based detection)
try:
    from lite_pose_detector import LitePoseDetector
    ACTIVITY_DETECTION_AVAILABLE = True
except ImportError:
    ACTIVITY_DETECTION_AVAILABLE = False
    logger.warning("⚠️ Lite pose detector not available - activity detection will be skipped")

# IST timezone offset: UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)


class CCTVRecognitionEngine:
    """
    Real-time face recognition on CCTV camera streams.
    Features:
    - Multi-camera support with independent processing threads
    - Face detection with confidence thresholds
    - Recognition against stored embeddings (0.6+ similarity)
    - Automatic attendance logging with deduplication (1 log per person per hour)
    - Graceful stream handling and error recovery
    """
    
    def __init__(
        self,
        db_path,
        ai_engine,
        attendance_tracker,
        profile_db=None,
        enable_emotion_detection=False,
        enable_activity_detection=False,
        enable_unknown_face_tracking=False
    ):
        """
        Initialize CCTV recognition engine.
        
        Args:
            db_path: Mongo-backed runtime root path
            ai_engine: InsightFaceRecognizer instance
            attendance_tracker: AttendanceTracker instance
            profile_db: ProfileDatabase instance for persistent unknown face tracking
        """
        self.db_path = db_path
        self.ai_engine = ai_engine
        self.attendance_tracker = attendance_tracker
        self.profile_db = profile_db
        self.enable_emotion_detection = enable_emotion_detection
        self.enable_activity_detection = enable_activity_detection
        self.enable_unknown_face_tracking = enable_unknown_face_tracking
        
        # Initialize emotion pipeline (optional, doesn't block attendance)
        self.emotion_pipeline = None
        if self.enable_emotion_detection and EMOTION_DETECTION_AVAILABLE:
            try:
                self.emotion_pipeline = EmotionPipeline()
                logger.info(
                    "✓ Emotion pipeline initialized successfully "
                    f"({self.emotion_pipeline.describe_backend()})"
                )
            except Exception as e:
                logger.warning(f"⚠️ Emotion pipeline initialization failed: {e}")
        
        # Initialize activity detector (optional, doesn't block attendance)
        self.activity_detector = None
        if self.enable_activity_detection and ACTIVITY_DETECTION_AVAILABLE:
            try:
                self.activity_detector = LitePoseDetector()
                logger.info("✓ Activity detector initialized successfully (LitePose - OpenCV-based, 10 activities)")
            except Exception as e:
                logger.warning(f"⚠️ Activity detector initialization failed: {e}")
        elif self.enable_activity_detection:
            logger.warning("⚠️ Activity detection not available")
        
        # Recognition thread management
        self.recognition_threads = {}  # {camera_id: thread}
        self.recognition_active = {}   # {camera_id: bool}
        self.recognition_stats = {}    # {camera_id: stats}
        self.stop_events = {}          # {camera_id: threading.Event}
        self.active_captures = {}      # {camera_id: cv2.VideoCapture}
        
        # Current detection tracking per camera
        self.current_detections = {}   # {camera_id: {updated_at, known_faces: [], unknown_faces: []}}
        self.current_frames = {}       # {camera_id: base64_encoded_frame}
        
        # SIMPLER FACE TRACKING: Position-based instead of embedding-based
        # Track known face positions per camera: {camera_id: [(cx, cy, w, h, person_id), ...]}
        # Updated every frame with current positions of all detected faces
        self.face_position_cache = defaultdict(list)  # flat list per camera
        self.unknown_face_counter = defaultdict(int)
        self.unknown_face_candidates = defaultdict(dict)
        
        # Position matching: if face center is within 80px of a known face, it's the same person
        # At 640x480, 80px is about 12% of frame width — reasonable for a seated person's movement
        self.position_match_threshold = 80  # pixels
        
        # Create snapshots directory for unknown faces
        self.snapshots_dir = os.path.join(os.path.dirname(db_path), 'face_snapshots')
        os.makedirs(self.snapshots_dir, exist_ok=True)
        
        # Similarity threshold for face recognition
        # NOTE: This value is NOT used in current implementation
        # Real threshold is in ai_engine.py: recognition_threshold = 0.32
        # which is proven to work with live camera input (faces score 0.40-0.55)
        self.similarity_threshold = 0.60
        
        # Face detection confidence threshold
        self.detection_confidence = 0.5
        
        self.cpu_core_count = max(1, os.cpu_count() or 1)
        self.persistence_executor = ThreadPoolExecutor(
            max_workers=max(2, min(4, self.cpu_core_count)),
            thread_name_prefix="recognition-persist",
        )
        persistence_backlog = os.getenv("CHRONOSENSE_RECOGNITION_PERSIST_BACKLOG", "256")
        try:
            self.max_persistence_backlog = max(32, int(persistence_backlog))
        except ValueError:
            self.max_persistence_backlog = 256
        self._persistence_slots = threading.BoundedSemaphore(self.max_persistence_backlog)
        self._dropped_persistence_tasks = 0
        self.worker_id = f"recognition-worker-{os.getpid()}"
        self.min_emotion_face_size = max(32, int(os.getenv("CHRONOSENSE_MIN_EMOTION_FACE_SIZE", "64")))
        self.absolute_min_emotion_face_size = max(24, int(os.getenv("CHRONOSENSE_ABSOLUTE_MIN_EMOTION_FACE_SIZE", "32")))
        self.target_emotion_face_size = max(
            self.min_emotion_face_size,
            int(os.getenv("CHRONOSENSE_TARGET_EMOTION_FACE_SIZE", "112")),
        )
        self.last_emotion_detection_at = {}
        self.emotion_detection_error = {}
        self.class_activity_pipeline = ClassActivityPipeline()
        self.latest_class_activity = {}
        self.latest_activity_reason = {}

        # Frame skip for performance (process every Nth frame).
        # Default to 1 so every captured frame is eligible for processing.
        configured_frame_skip = os.getenv("CHRONOSENSE_FRAME_SKIP", "1")
        try:
            self.frame_skip = max(1, int(configured_frame_skip))
        except ValueError:
            self.frame_skip = 1
        configured_target_fps = os.getenv("CHRONOSENSE_RECOGNITION_TARGET_FPS", "8")
        try:
            self.target_processing_fps = max(1.0, float(configured_target_fps))
        except ValueError:
            self.target_processing_fps = 8.0
        self.min_processing_interval = 1.0 / self.target_processing_fps
        
        logger.info(
            "✓ CCTV Recognition Engine initialized "
            f"(emotion={'on' if self.enable_emotion_detection else 'off'}, "
            f"activity={'on' if self.enable_activity_detection else 'off'}, "
            f"unknown_tracking={'on' if self.enable_unknown_face_tracking else 'off'}, "
            f"cpu_cores={self.cpu_core_count}, frame_skip={self.frame_skip}, "
            f"target_fps={self.target_processing_fps})"
        )
        logger.info(
            "Resolved runtime thresholds: recognition_default=%.2f emotion_backend=%s "
            "consensus=%.2f analytics_quality=%.2f emotion_quality=%.2f window_frames=%s "
            "window_seconds=%s alpha=%s",
            float(self.ai_engine.recognition_threshold),
            self._active_emotion_backend().get("backend"),
            float(os.getenv("CHRONOSENSE_EMOTION_CONSENSUS_THRESHOLD", "0.25")),
            float(os.getenv("CHRONOSENSE_EMOTION_ANALYTICS_QUALITY_THRESHOLD", "0.32")),
            float(os.getenv("CHRONOSENSE_EMOTION_QUALITY_THRESHOLD", "0.32")),
            os.getenv("CHRONOSENSE_EMOTION_WINDOW_FRAMES", "5"),
            os.getenv("CHRONOSENSE_EMOTION_WINDOW_SECONDS", "1.0"),
            os.getenv("CHRONOSENSE_EMOTION_SMOOTHING_ALPHA", "0.55"),
        )

    def _publish_runtime_state(self, camera_id, camera_name=None, **overrides):
        stats = dict(self.recognition_stats.get(camera_id, {}))
        if camera_name:
            stats["camera_name"] = camera_name
        active_backend = self._active_emotion_backend()

        payload = {
            "camera_name": stats.get("camera_name"),
            "is_running": bool(self.recognition_active.get(camera_id, False)),
            "status": stats.get("status", "unknown"),
            "frames_processed": stats.get("frames_processed", 0),
            "faces_recognized": stats.get("faces_recognized", 0),
            "fps": stats.get("fps", 0),
            "message": stats.get("message", ""),
            "reconnect_attempts": stats.get("reconnect_attempts", 0),
            "start_time": stats.get("start_time"),
            "uptime": stats.get("uptime"),
            "worker_id": self.worker_id,
            "emotion_enabled": bool(stats.get("emotion_enabled", self.enable_emotion_detection)),
            "emotion_model_loaded": bool(stats.get("emotion_model_loaded", False)),
            "emotion_backend": stats.get("emotion_backend") or active_backend.get("backend"),
            "emotion_model_name": stats.get("emotion_model_name") or active_backend.get("model_name"),
            "emotion_model_version": stats.get("emotion_model_version") or active_backend.get("model_version"),
            "last_emotion_detection_at": stats.get("last_emotion_detection_at") or self.last_emotion_detection_at.get(camera_id),
            "emotion_detection_error": stats.get("emotion_detection_error") or self.emotion_detection_error.get(camera_id),
        }
        payload.update(overrides)
        try:
            set_runtime_state(camera_id, payload)
        except Exception as exc:
            logger.warning(f"Failed to publish recognition runtime state for camera {camera_id}: {exc}")

    def _publish_current_detections(self, camera_id):
        try:
            detections = self.current_detections.get(camera_id, {
                "updated_at": None,
                "known_faces": [],
                "unknown_faces": [],
                "total_faces": 0,
            })
            set_latest_detections(camera_id, detections)
        except Exception as exc:
            logger.warning(f"Failed to publish detections for camera {camera_id}: {exc}")

    def _get_camera_runtime_config(self, camera_id):
        doc = mongo_store.collection("cctv_cameras").find_one(
            {"_id": camera_id},
            {
                "name": 1,
                "inference_width": 1,
                "target_fps": 1,
                "recognition_threshold_override": 1,
                "enable_emotion": 1,
                "enable_activity": 1,
                "camera_context": 1,
                "class_name": 1,
                "section_name": 1,
                "front_zone": 1,
                "board_zone": 1,
                "student_seating_zone": 1,
                "faculty_workstation_zone": 1,
            },
        ) or {}

        try:
            inference_width = max(640, int(doc.get("inference_width", 960) or 960))
        except (TypeError, ValueError):
            inference_width = 960
        try:
            target_fps = max(1.0, float(doc.get("target_fps", self.target_processing_fps) or self.target_processing_fps))
        except (TypeError, ValueError):
            target_fps = self.target_processing_fps

        threshold_override = doc.get("recognition_threshold_override")
        if threshold_override is not None:
            try:
                threshold_override = float(threshold_override)
            except (TypeError, ValueError):
                threshold_override = None

        emotion_worker_threshold = None
        service_name = (os.getenv("CHRONOSENSE_SERVICE_NAME") or "").strip()
        if service_name == "emotion-worker":
            configured_value = os.getenv("CHRONOSENSE_EMOTION_RECOGNITION_THRESHOLD") or os.getenv("CHRONOSENSE_RECOGNITION_THRESHOLD")
            if configured_value is not None:
                try:
                    emotion_worker_threshold = float(configured_value)
                except (TypeError, ValueError):
                    emotion_worker_threshold = None
            if (doc.get("camera_context") or "").strip().lower() == "classroom":
                inference_width = max(
                    inference_width,
                    int(os.getenv("CHRONOSENSE_EMOTION_INFERENCE_WIDTH", str(EMOTION_INFERENCE_WIDTH_FLOOR))),
                )
        if threshold_override is not None and emotion_worker_threshold is not None:
            threshold_override = min(threshold_override, emotion_worker_threshold)
        if service_name == "attendance-worker":
            configured_value = os.getenv(
                "CHRONOSENSE_ATTENDANCE_RECOGNITION_THRESHOLD",
                os.getenv("CHRONOSENSE_RECOGNITION_THRESHOLD", str(ATTENDANCE_RECOGNITION_FLOOR)),
            )
            try:
                attendance_threshold_floor = max(
                    ATTENDANCE_RECOGNITION_FLOOR,
                    float(configured_value),
                )
            except (TypeError, ValueError):
                attendance_threshold_floor = ATTENDANCE_RECOGNITION_FLOOR

            if threshold_override is None:
                threshold_override = attendance_threshold_floor
            else:
                threshold_override = max(threshold_override, attendance_threshold_floor)

        camera_name = doc.get("name") or str(camera_id)
        if threshold_override is not None:
            self.ai_engine.camera_thresholds[camera_name] = threshold_override
            self.ai_engine.camera_thresholds[camera_id] = threshold_override

        return {
            "camera_name": camera_name,
            "inference_width": inference_width,
            "target_fps": target_fps,
            "recognition_threshold_override": threshold_override,
            "enable_emotion": self.enable_emotion_detection if doc.get("enable_emotion") is None else bool(doc.get("enable_emotion")),
            "enable_activity": self.enable_activity_detection if doc.get("enable_activity") is None else bool(doc.get("enable_activity")),
            "camera_context": doc.get("camera_context") or "mixed",
            "class_name": doc.get("class_name"),
            "section_name": doc.get("section_name"),
            "front_zone": doc.get("front_zone"),
            "board_zone": doc.get("board_zone"),
            "student_seating_zone": doc.get("student_seating_zone"),
            "faculty_workstation_zone": doc.get("faculty_workstation_zone"),
            "camera_id": camera_id,
        }

    @staticmethod
    def _parse_zone(zone, frame_shape):
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

    def _select_inference_region(self, frame, runtime_config):
        try:
            service_name = (os.getenv("CHRONOSENSE_SERVICE_NAME") or "").strip()
            if service_name != "emotion-worker":
                return frame, None
            if (runtime_config.get("camera_context") or "").strip().lower() != "classroom":
                return frame, None

            zone = (
                self._parse_zone(runtime_config.get("student_seating_zone"), frame.shape)
                or self._parse_zone(runtime_config.get("front_zone"), frame.shape)
            )
            if not zone:
                return frame, None

            x1, y1, x2, y2 = zone
            zone_w = max(1, x2 - x1)
            zone_h = max(1, y2 - y1)
            margin_x = int(zone_w * 0.08)
            margin_y = int(zone_h * 0.08)
            crop_x1 = max(0, x1 - margin_x)
            crop_y1 = max(0, y1 - margin_y)
            crop_x2 = min(frame.shape[1], x2 + margin_x)
            crop_y2 = min(frame.shape[0], y2 + margin_y)
            cropped = frame[crop_y1:crop_y2, crop_x1:crop_x2]
            if cropped.size == 0:
                return frame, None
            return cropped, (crop_x1, crop_y1)
        except Exception as exc:
            logger.debug(f"Failed to select emotion inference region: {exc}")
            return frame, None

    def _active_emotion_backend(self):
        backend = getattr(self.emotion_pipeline, "backend", None)
        return {
            "backend": getattr(backend, "name", None),
            "model_name": getattr(backend, "model_name", None),
            "model_version": getattr(backend, "model_version", None),
            "model_loaded": bool(getattr(backend, "model_loaded", False)),
        }

    def _prepare_frame_for_inference(self, frame):
        try:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
            normalized = cv2.merge((l_channel, a_channel, b_channel))
            normalized = cv2.cvtColor(normalized, cv2.COLOR_LAB2BGR)
            blurred = cv2.GaussianBlur(normalized, (0, 0), 1.2)
            return cv2.addWeighted(normalized, 1.15, blurred, -0.15, 0)
        except Exception as exc:
            logger.debug(f"Frame preprocessing failed: {exc}")
            return frame

    def _submit_persistence_task(self, fn, *args, **kwargs):
        if not self._persistence_slots.acquire(blocking=False):
            self._dropped_persistence_tasks += 1
            if self._dropped_persistence_tasks % 25 == 1:
                logger.warning(
                    "Recognition persistence backlog full; dropping write task "
                    f"(dropped={self._dropped_persistence_tasks})"
                )
            return False

        future = self.persistence_executor.submit(fn, *args, **kwargs)

        def _release(_future):
            self._persistence_slots.release()
            try:
                _future.result()
            except Exception as exc:
                logger.error(f"Recognition persistence task failed: {exc}")

        future.add_done_callback(_release)
        return True

    def _persist_recognition_batch(self, recognized_faces, camera_name, camera_id=None, class_activity=None):
        if recognized_faces:
            self.attendance_tracker.log_stream_detections(recognized_faces, location=camera_name)
        if class_activity:
            self.attendance_tracker.log_class_activity(class_activity)

        persisted_known_faces = 0
        for face in recognized_faces:
            emotion_data = {
                'emotion': face.get('emotion', LOW_SIGNAL_EMOTION),
                'confidence': face.get('emotion_confidence', 0.0),
                'intensity': face.get('emotion_intensity', 'low'),
                'all_scores': face.get('all_emotions', {})
            }
            face_profile_id = face.get('profile_id')
            is_unknown_face = face_profile_id in (None, -1) or face.get("unknown_face_id") is not None

            if face.get('frame_path') is None:
                logger.warning(
                    "Persisting face without snapshot path for "
                    f"{face.get('name', 'Unknown')} from {camera_name}"
                )

            if face_profile_id == -1:
                self.attendance_tracker.log_detection(
                    profile_id=-1,
                    name='Unregistered Attendee',
                    status='present',
                    confidence=0.0,
                    emotion=face.get('emotion', LOW_SIGNAL_EMOTION),
                    emotion_data=emotion_data,
                    frame_path=None,
                    location=camera_name,
                    camera_id=camera_id,
                )
            elif is_unknown_face:
                if not face.get("frame_path"):
                    logger.warning(
                        "Skipping unknown emotion persistence without snapshot path for %s from %s",
                        face.get("name", "Unknown"),
                        camera_name,
                    )
                    continue
                self.attendance_tracker.log_emotion_event(
                    profile_id=None,
                    unknown_face_id=face.get("unknown_face_id"),
                    name=face.get("name", "Unknown"),
                    location=camera_name,
                    camera_id=camera_id,
                    timestamp=datetime.utcnow(),
                    frame_path=face.get("frame_path"),
                    recognition_confidence=face.get("confidence", 0.0),
                    emotion=face.get("emotion", LOW_SIGNAL_EMOTION),
                    emotion_data=emotion_data,
                )
            else:
                success = self.attendance_tracker.log_detection(
                    profile_id=face_profile_id,
                    name=face['name'],
                    status='present',
                    confidence=face['confidence'],
                    emotion=face.get('emotion', LOW_SIGNAL_EMOTION),
                    emotion_data=emotion_data,
                    frame_path=face.get('frame_path'),
                    location=camera_name,
                    camera_id=camera_id,
                )
                if success:
                    persisted_known_faces += 1
                if face.get("emotion") is not None:
                    self.attendance_tracker.log_emotion_event(
                        profile_id=face_profile_id,
                        name=face.get("name"),
                        location=camera_name,
                        camera_id=camera_id,
                        timestamp=datetime.utcnow(),
                        frame_path=face.get("frame_path"),
                        recognition_confidence=face.get("confidence", 0.0),
                        emotion=face.get("emotion", LOW_SIGNAL_EMOTION),
                        emotion_data=emotion_data,
                    )

        return persisted_known_faces

    def enqueue_recognition_persistence(self, recognized_faces, camera_name, camera_id=None, class_activity=None):
        return self._submit_persistence_task(
            self._persist_recognition_batch,
            list(recognized_faces or []),
            camera_name,
            camera_id,
            dict(class_activity or {}) if class_activity else None,
        )
    
    def _match_unknown_face(self, face_bbox, camera_id):
        """
        Match unknown face by position. Each camera keeps a flat list of
        (center_x, center_y, person_id) for all tracked people.
        The list is rebuilt every frame via _update_position_cache().
        
        Returns: (person_id, is_new_person)
        """
        try:
            x, y, w, h = int(face_bbox[0]), int(face_bbox[1]), int(face_bbox[2]), int(face_bbox[3])
            cx, cy = x + w // 2, y + h // 2
            
            best_id = None
            best_dist = float('inf')
            
            for (pcx, pcy, pid) in self.face_position_cache[camera_id]:
                dist = ((cx - pcx) ** 2 + (cy - pcy) ** 2) ** 0.5
                if dist < self.position_match_threshold and dist < best_dist:
                    best_dist = dist
                    best_id = pid
            
            if best_id is not None:
                logger.info(f"✓ MATCHED face → ID {best_id} (dist={best_dist:.0f}px)")
                return best_id, False
            
            # New person — use NEGATIVE IDs to avoid collision with profile_id
            self.unknown_face_counter[camera_id] += 1
            new_id = -self.unknown_face_counter[camera_id]
            logger.info(f"🆕 NEW face ID {new_id} at ({cx},{cy})")
            return new_id, True
        
        except Exception as e:
            logger.error(f"ERROR in _match_unknown_face: {e}")
            self.unknown_face_counter[camera_id] += 1
            return -self.unknown_face_counter[camera_id], True

    def _should_persist_unknown_face(self, camera_id, persistent_unknown_id, snapshot_path):
        now = time.time()
        state = self.unknown_face_candidates[camera_id].get(persistent_unknown_id)
        if state is None:
            state = {
                "first_seen_at": now,
                "last_seen_at": now,
                "consecutive_frames": 1,
                "persisted": False,
                "snapshot_path": snapshot_path,
            }
            self.unknown_face_candidates[camera_id][persistent_unknown_id] = state
        else:
            state["last_seen_at"] = now
            state["consecutive_frames"] += 1
            if snapshot_path:
                state["snapshot_path"] = snapshot_path

        if state["persisted"]:
            return False, state

        elapsed = now - state["first_seen_at"]
        if state["consecutive_frames"] >= UNKNOWN_PERSISTENCE_MIN_FRAMES or elapsed >= UNKNOWN_PERSISTENCE_MIN_SECONDS:
            if not state.get("snapshot_path"):
                logger.warning("unknown_snapshot_write_failed: camera=%s unknown=%s", camera_id, persistent_unknown_id)
                return False, state
            state["persisted"] = True
            return True, state
        return False, state

    def _prune_unknown_candidates(self, camera_id, active_unknown_ids):
        active_unknown_ids = set(active_unknown_ids or [])
        now = time.time()
        candidates = self.unknown_face_candidates.get(camera_id, {})
        stale_ids = [
            unknown_id
            for unknown_id, state in candidates.items()
            if unknown_id not in active_unknown_ids and (now - state.get("last_seen_at", now)) > 2.0
        ]
        for unknown_id in stale_ids:
            del candidates[unknown_id]
    
    def _process_frame(self, frame, camera_id, runtime_config=None):
        """
        Process a single frame for face detection and recognition.
        Also detects emotions and activities for all faces.
        
        Args:
            frame: Video frame (BGR)
            camera_id: Camera identifier
        
        Returns:
            List of recognized faces with frame paths: [{'profile_id', 'name', 'confidence', 'frame_path'}, ...]
        """
        try:
            runtime_config = runtime_config or {}
            prepared_frame = self._prepare_frame_for_inference(frame)
            # Keep only the native InsightFace detection stage serialized. The
            # rest of the per-camera pipeline can run concurrently, which gives
            # better CPU distribution across camera workers while preserving the
            # macOS stability guard around shared model runtime access.
            with self.ai_engine.runtime_lock:
                detected_faces = self.ai_engine.detect_faces_with_landmarks(prepared_frame)
            
            if not detected_faces:
                return []
            
            # Update classroom student count
            if self.activity_detector:
                self.activity_detector.update_student_count(len(detected_faces))
            
            known_faces = []
            unknown_faces = []
            frame_debug_counts = {
                "recognized": 0,
                "unknown_rejected_threshold": 0,
                "unknown_rejected_gap": 0,
            }
            classroom_emotions = []  # For logging unknown face emotions
            
            for i, face_data in enumerate(detected_faces):
                face_bbox = face_data['bbox']
                landmarks = face_data.get('landmark')
                face_obj = face_data.get('face_obj')  # ← Get pre-computed embedding object
                
                # FIRST: Crop the face with minimal padding for isolation
                # This ensures clean, isolated face region for recognition and emotion detection
                face_crop = self._crop_face(prepared_frame, face_bbox)
                if face_crop is None:
                    # Retry crop once — frame may have been momentarily corrupted
                    logger.debug(f"Face crop failed for bbox {face_bbox}, retrying...")
                    face_crop = self._crop_face(prepared_frame, face_bbox)
                    if face_crop is None:
                        continue
                
                # SECOND: Try to recognize the CROPPED face (better validation)
                # Pass face_obj so recognition can use pre-computed embedding
                # Pass camera_id for camera-specific thresholds
                match = self._recognize_face(
                    face_crop,
                    prepared_frame,
                    face_bbox,
                    landmarks=landmarks,
                    face_obj=face_obj,
                    camera_id=runtime_config.get("camera_name", camera_id),
                    enable_emotion=runtime_config.get("enable_emotion", self.enable_emotion_detection),
                    enable_activity=runtime_config.get("enable_activity", self.enable_activity_detection),
                )
                
                if match and match.get("recognized"):  # Known face
                    # Save cropped face snapshot; retry once if save fails
                    snapshot_path = self._save_face_snapshot(face_crop, camera_id, match['name'], match.get('profile_id'))
                    if snapshot_path is None:
                        logger.warning(f"Snapshot save failed for {match['name']}, re-cropping and retrying...")
                        face_crop_retry = self._crop_face(prepared_frame, face_bbox)
                        if face_crop_retry is not None:
                            snapshot_path = self._save_face_snapshot(face_crop_retry, camera_id, match['name'], match.get('profile_id'))
                    match['frame_path'] = snapshot_path
                    match['bbox'] = list(face_bbox)[:4] if len(face_bbox) >= 4 else []
                    
                    known_faces.append(match)
                    frame_debug_counts["recognized"] += 1
                    if match.get("emotion_available"):
                        self.last_emotion_detection_at[camera_id] = datetime.utcnow().isoformat()
                        self.emotion_detection_error[camera_id] = None
                    elif match.get("emotion_unavailable_reason"):
                        self.emotion_detection_error[camera_id] = match.get("emotion_unavailable_reason")
                    logger.info(f"✓ Recognized from camera {camera_id}: {match['name']} (conf={match['confidence']:.3f})")
                    logger.debug(f"   → Added to known_faces list. Total known_faces: {len(known_faces)}")
                    logger.debug(f"   → Detection dict keys: {list(match.keys())}")
                    logger.debug(f"   → Activity: {match.get('activity', 'KEY_NOT_FOUND')} | Confidence: {match.get('activity_confidence', 'KEY_NOT_FOUND')}")
                else:  # Unknown face - save snapshot and persist to database / analytics
                    if not self.enable_unknown_face_tracking and not runtime_config.get("enable_activity", self.enable_activity_detection):
                        continue

                    # Save cropped face snapshot; retry once if save fails
                    snapshot_path = self._save_unknown_face_snapshot(face_crop, camera_id)
                    if snapshot_path is None:
                        logger.warning(f"Unknown face snapshot save failed, re-cropping and retrying...")
                        face_crop_retry = self._crop_face(prepared_frame, face_bbox)
                        if face_crop_retry is not None:
                            snapshot_path = self._save_unknown_face_snapshot(face_crop_retry, camera_id)
                    
                    # MATCH UNKNOWN FACE by position (same person stays in ~same location)
                    # Using position-based tracking instead of embedding for reliability
                    persistent_unknown_id, is_new_person = self._match_unknown_face(face_bbox, camera_id)
                    should_persist_unknown, unknown_state = self._should_persist_unknown_face(
                        camera_id,
                        persistent_unknown_id,
                        snapshot_path,
                    )
                    recognition_debug = (match or {}).get("recognition_debug") or {}
                    rejection_reason = recognition_debug.get("recognition_rejection_reason")
                    if rejection_reason == "gap":
                        frame_debug_counts["unknown_rejected_gap"] += 1
                    else:
                        frame_debug_counts["unknown_rejected_threshold"] += 1
                    
                    # Only persist to database if this is a new person
                    # (Don't create duplicate DB entries for same person across frames)
                    unknown_id = None
                    if should_persist_unknown and self.profile_db and self.enable_unknown_face_tracking:
                        unknown_id = self.profile_db.add_unknown_face(
                            camera_id,
                            unknown_state.get("snapshot_path"),
                            list(face_bbox)[:4] if len(face_bbox) >= 4 else [],
                            unknown_face_id=persistent_unknown_id
                        )
                        logger.info(
                            "✓ New unknown person detected (persistent ID: %s, DB: %s, frames=%s): %s",
                            persistent_unknown_id,
                            unknown_id,
                            unknown_state.get("consecutive_frames"),
                            unknown_state.get("snapshot_path"),
                        )
                    
                    # DETECT ACTIVITY FOR UNKNOWN FACES (for classroom analytics)
                    activity = 'Unknown'
                    activity_confidence = 0.0
                    if self.activity_detector is not None:
                        try:
                            activity, activity_confidence = self.activity_detector.detect_activity(
                                prepared_frame, face_bbox
                            )
                        except Exception as e:
                            logger.debug(f"Activity detection failed for unknown face: {e}")

                    # DETECT EMOTION FOR UNKNOWN FACES (for classroom analytics)
                    emotion_data = None
                    if runtime_config.get("enable_emotion", self.enable_emotion_detection):
                        emotion_data = self._infer_emotion_signal(
                            face_crop=face_crop,
                            face_bbox=face_bbox,
                            landmarks=landmarks,
                            camera_key=runtime_config.get("camera_name", camera_id),
                            track_key=f"{camera_id}:unknown:{persistent_unknown_id}",
                            enable_emotion=runtime_config.get("enable_emotion", self.enable_emotion_detection),
                            activity=activity,
                            activity_confidence=activity_confidence,
                            face_obj=face_obj,
                        )

                    flattened_emotion = dict(emotion_data or {})
                    
                    unknown_faces.append({
                        'face_id': len(unknown_faces),
                        'persistent_unknown_id': persistent_unknown_id,  # Persistent ID for same person across frames
                        'unknown_id': unknown_id,  # Database ID (only set for new people)
                        'name': f"Unknown person {persistent_unknown_id}",
                        'profile_id': None,
                        'recognized': False,
                        'confidence': 0.0,
                        'snapshot_path': snapshot_path,
                        'bbox': list(face_bbox)[:4] if len(face_bbox) >= 4 else [],
                        'emotion_data': emotion_data,
                        'activity': activity,
                        'activity_confidence': activity_confidence,
                        'embedding_similarity': None,  # Will be set if matched to existing person
                        'recognition_debug': recognition_debug,
                        'ready_for_persistence': bool(should_persist_unknown and unknown_state.get("snapshot_path")),
                        'frame_path': unknown_state.get("snapshot_path") if should_persist_unknown else None,
                        **flattened_emotion,
                    })
                    
                    # Note: Unknown faces are NOT logged to attendance/activity logs
                    # Only registered students (known faces) are tracked for activity monitoring
                    # Unknown faces are saved as snapshots for security purposes only
            
            # REBUILD position cache for this camera from THIS frame's detections
            # This ensures next frame's matching uses current positions
            new_cache = []
            for uf in unknown_faces:
                bbox = uf.get('bbox', [])
                pid = uf.get('persistent_unknown_id')
                if len(bbox) >= 4 and pid is not None:
                    x, y, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                    new_cache.append((x + w // 2, y + h // 2, pid))
            self.face_position_cache[camera_id] = new_cache
            self._prune_unknown_candidates(camera_id, [face.get('persistent_unknown_id') for face in unknown_faces])
            logger.info(f"📍 Position cache updated: {len(new_cache)} faces tracked for camera {camera_id}")
            
            # Update current detections
            self.current_detections[camera_id] = {
                'updated_at': datetime.now().isoformat(),
                'known_faces': known_faces,
                'unknown_faces': unknown_faces,
                'total_faces': len(known_faces) + len(unknown_faces)
            }
            class_activity = None
            if runtime_config.get("enable_activity", self.enable_activity_detection):
                class_activity_inputs = []
                for face in known_faces:
                    class_activity_inputs.append(
                        {
                            "profile_id": face.get("profile_id"),
                            "profile_type": face.get("profile_type"),
                            "bbox": face.get("bbox"),
                            "class_name": face.get("class_name"),
                            "section_name": face.get("section_name"),
                            "movement_score": float(face.get("activity_confidence") or 0.0) * 10.0,
                        }
                    )
                for face in unknown_faces:
                    class_activity_inputs.append(
                        {
                            "unknown_face_id": face.get("persistent_unknown_id"),
                            "bbox": face.get("bbox"),
                        }
                    )
                class_activity = self.class_activity_pipeline.analyze_scene(
                    frame=prepared_frame,
                    detections=class_activity_inputs,
                    runtime_config=runtime_config,
                    timestamp=datetime.utcnow(),
                )
                if class_activity:
                    self.latest_class_activity[camera_id] = class_activity
                    self.current_detections[camera_id]["class_activity"] = class_activity
                    self.latest_activity_reason[camera_id] = class_activity.get("reason")
                    logger.info(
                        "Class activity: camera=%s student=%s(%.2f) faculty=%s(%.2f) context=%s(%.2f) students=%s faculty=%s unknown=%s reason=%s",
                        camera_id,
                        class_activity.get("student_activity_label"),
                        float(class_activity.get("student_activity_confidence") or 0.0),
                        class_activity.get("faculty_activity_label"),
                        float(class_activity.get("faculty_activity_confidence") or 0.0),
                        class_activity.get("context_label"),
                        float(class_activity.get("context_confidence") or 0.0),
                        int(class_activity.get("recognized_student_count") or 0),
                        int(class_activity.get("recognized_faculty_count") or 0),
                        int(class_activity.get("unknown_count") or 0),
                        class_activity.get("reason") or "-",
                    )
                else:
                    self.latest_class_activity.pop(camera_id, None)
                    self.latest_activity_reason.pop(camera_id, None)
            else:
                self.latest_class_activity.pop(camera_id, None)
                self.latest_activity_reason.pop(camera_id, None)
            self._publish_current_detections(camera_id)
            
            # Return ALL detections for activity logging
            # Unknown faces now included with activity data for classroom activity analytics
            # Uses persistent_unknown_id for proper tracking across frames
            classroom_activities = []
            for unknown_face in unknown_faces:
                # Include ALL activities (even "Unknown") to capture all detections
                activity = unknown_face.get('activity', 'Unknown')
                
                # Use detected emotion if available, otherwise default to Neutral
                emotion_data = unknown_face.get('emotion_data') or {}
                emotion = emotion_data.get('emotion', LOW_SIGNAL_EMOTION)
                
                # Safeguard: Never log 'Unknown' as an emotion - use Neutral instead
                if not emotion or emotion == 'Unknown':
                    emotion = LOW_SIGNAL_EMOTION
                
                emotion_confidence = emotion_data.get('confidence', 0.0)
                emotion_intensity = emotion_data.get('intensity', 'low')
                all_emotions = emotion_data.get('all_scores', {})
                
                classroom_activities.append({
                    'profile_id': None,  # Unknown face
                    'unknown_face_id': unknown_face.get('persistent_unknown_id'),  # Persistent ID across frames
                    'name': f"Unknown Student ({unknown_face['persistent_unknown_id']})",
                    'confidence': 0.0,
                    'emotion': emotion,  # Use detected emotion, not hardcoded 'Unknown'
                    'emotion_confidence': emotion_confidence,
                    'emotion_intensity': emotion_intensity,
                    'all_emotions': all_emotions,
                    'emotion_data': emotion_data,
                    'activity': activity,
                    'activity_confidence': unknown_face.get('activity_confidence', 0.0),
                    'frame_path': unknown_face.get('frame_path'),
                    'recognition_debug': unknown_face.get('recognition_debug') or {},
                })
            
            # Return known faces + unknown classroom activities (for activity logging)
            all_detections = known_faces + classroom_activities
            
            # === Detect group activities (Playing/Fighting) based on proximity ===
            if self.activity_detector and len(all_detections) >= 2:
                try:
                    all_detections = self.activity_detector.detect_group_activities(all_detections)
                except Exception as e:
                    logger.debug(f"Group activity detection failed: {e}")
            
            if all_detections:
                logger.info(f"📤 Returning {len(all_detections)} detections from process_frame (known={len(known_faces)}, unknown_activities={len(classroom_activities)})")
                # Log activity data for first detection to verify it's being passed
                first_detection = all_detections[0]
                logger.debug(f"   → First detection dict keys: {list(first_detection.keys())}")
                logger.debug(f"   → First detection activity: {first_detection.get('activity', 'MISSING')} | conf: {first_detection.get('activity_confidence', 'MISSING')}")
            logger.info(
                "Recognition frame summary: camera=%s recognized=%s unknown_rejected_threshold=%s unknown_rejected_gap=%s",
                camera_id,
                frame_debug_counts["recognized"],
                frame_debug_counts["unknown_rejected_threshold"],
                frame_debug_counts["unknown_rejected_gap"],
            )
                
            return all_detections
        except Exception as e:
            logger.error(f"Frame processing failed for camera {camera_id}: {e}")
            return []
    
    def process_frame(self, frame, camera_id):
        """
        Public method to process a single frame for CCTV recognition.
        Called from server.py to handle real-time stream processing.
        
        Args:
            frame: Video frame (BGR)
            camera_id: Camera identifier (e.g., 'camera_4')
        
        Returns:
            List of detections with ALL data including activity and emotion:
            [{
                'profile_id': int,
                'name': str,
                'confidence': float,
                'emotion': str,
                'emotion_confidence': float,
                'emotion_intensity': str,
                'all_emotions': dict,
                'activity': str,  # ← NEW: From InsightFace landmark detection
                'activity_confidence': float,  # ← NEW: Activity detection confidence
                'location': str,
                'frame_path': str,
                'timestamp': str
            }, ...]
        """
        # Extract numeric camera_id if it's a string like "camera_4"
        try:
            if isinstance(camera_id, str) and camera_id.startswith('camera_'):
                numeric_camera_id = int(camera_id.split('_')[1])
            else:
                numeric_camera_id = camera_id
        except (ValueError, IndexError):
            numeric_camera_id = camera_id
        
        runtime_config = self._get_camera_runtime_config(numeric_camera_id) if isinstance(numeric_camera_id, int) else {}
        frame, crop_offset = self._select_inference_region(frame, runtime_config)
        if runtime_config.get("inference_width"):
            frame_h, frame_w = frame.shape[:2]
            inference_width = runtime_config["inference_width"]
            if frame_w > inference_width:
                scale = inference_width / float(frame_w)
                frame = cv2.resize(
                    frame,
                    (inference_width, max(1, int(frame_h * scale))),
                    interpolation=cv2.INTER_AREA,
                )
        detections = self._process_frame(frame, numeric_camera_id, runtime_config=runtime_config)
        if crop_offset and detections:
            offset_x, offset_y = crop_offset
            for detection in detections:
                bbox = detection.get("bbox") or []
                if len(bbox) >= 4:
                    detection["bbox"] = [
                        int(bbox[0]) + offset_x,
                        int(bbox[1]) + offset_y,
                        int(bbox[2]),
                        int(bbox[3]),
                    ]
        return detections
    
    def _recognize_face(self, face_image, original_frame, face_bbox, landmarks=None, is_cropped=True, face_obj=None, camera_id=None, enable_emotion=None, enable_activity=None):
        """
        Recognize a face using the ChronoEngine.
        Optional emotion detection runs in parallel without blocking attendance.
        
        Args:
            face_image: Cropped face image for recognition
            original_frame: Full frame for activity detection
            face_bbox: Face bounding box in original frame
            landmarks: 106-point face landmarks from InsightFace (for activity detection)
            is_cropped: If True, face_image is already cropped; use full image as bbox.
                       If False, face_image is full frame (legacy, not recommended)
            face_obj: Optional InsightFace face object with pre-computed embedding
            camera_id: Optional camera name for camera-specific recognition thresholds
        
        Returns:
            dict: {'profile_id', 'name', 'confidence', 'emotion', 'emotion_confidence', 'emotion_intensity', 'all_emotions'} 
                  or None if no match
        """
        try:
            # Create appropriate bbox for recognition
            if is_cropped:
                # For cropped images, use the full image as the face region
                h, w = face_image.shape[:2]
                recognition_bbox = (0, 0, w, h)
                frame_for_emotion = face_image  # Use cropped image directly for emotion
            else:
                # Legacy mode: assumes face_image is full frame (not recommended)
                # This path is kept for backwards compatibility
                logger.warning("Deprecated: passing full frame to _recognize_face")
                return None
            
            # Use the existing ChronoEngine.recognize_face() method
            # Pass face_obj with pre-computed embedding if available
            # Pass camera_id for camera-specific thresholds
            # Returns: (profile_id, name, confidence)
            profile_id, name, confidence, recognition_debug = self.ai_engine.recognize_face(
                face_image,
                recognition_bbox,
                face_obj=face_obj,
                camera_id=camera_id,
            )
            
            # Check if it's a valid match (not 'Unknown')
            if profile_id is None or name == 'Unknown':
                return {
                    "recognized": False,
                    "profile_id": None,
                    "name": "Unknown",
                    "confidence": float(confidence or 0.0),
                    "recognition_debug": recognition_debug,
                    "best_score": recognition_debug.get("best_score"),
                    "second_best_score": recognition_debug.get("second_best_score"),
                    "score_gap": recognition_debug.get("score_gap"),
                    "applied_threshold": recognition_debug.get("applied_threshold"),
                    "applied_min_gap": recognition_debug.get("applied_min_gap"),
                    "matched_view": recognition_debug.get("matched_view"),
                    "recognition_rejection_reason": recognition_debug.get("recognition_rejection_reason"),
                }
            
            result = {
                'recognized': True,
                'profile_id': profile_id,
                'name': name,
                'confidence': float(confidence),
                'recognition_debug': recognition_debug,
                'best_score': recognition_debug.get("best_score"),
                'second_best_score': recognition_debug.get("second_best_score"),
                'score_gap': recognition_debug.get("score_gap"),
                'applied_threshold': recognition_debug.get("applied_threshold"),
                'applied_min_gap': recognition_debug.get("applied_min_gap"),
                'matched_view': recognition_debug.get("matched_view"),
                'recognition_rejection_reason': recognition_debug.get("recognition_rejection_reason"),
            }
            if self.profile_db is not None:
                profile = self.profile_db.get_profile(profile_id)
                if profile:
                    result["profile_type"] = profile.get("profile_type", "faculty")
                    result["class_name"] = profile.get("class_name")
                    result["section_name"] = profile.get("section_name")
            
            # EMOTION DETECTION - Optional, doesn't block attendance
            # Uses isolated cropped face for better detection
            if enable_emotion is None:
                enable_emotion = self.emotion_pipeline is not None
            if enable_activity is None:
                enable_activity = self.enable_activity_detection and self.activity_detector is not None

            h_e, w_e = frame_for_emotion.shape[:2]
            emotion_model_loaded = bool(self.emotion_pipeline and getattr(self.emotion_pipeline.backend, "model_loaded", False))
            emotion_detector_ready = self.emotion_pipeline is not None
            active_backend = self._active_emotion_backend()
            result["emotion_enabled"] = bool(enable_emotion)
            result["emotion_model_loaded"] = emotion_model_loaded
            result["emotion_backend"] = active_backend.get("backend")
            result["emotion_model_name"] = active_backend.get("model_name")
            result["emotion_model_version"] = active_backend.get("model_version")
            result["emotion_fallback_active"] = bool(
                emotion_detector_ready and not emotion_model_loaded
            )

            if enable_emotion and emotion_detector_ready and min(h_e, w_e) >= self.min_emotion_face_size:
                try:
                    emotion_data = self._infer_emotion_signal(
                        face_crop=frame_for_emotion,
                        face_bbox=face_bbox,
                        landmarks=landmarks,
                        camera_key=camera_id,
                        track_key=f"{camera_id}:profile:{profile_id}",
                        enable_emotion=enable_emotion,
                    )
                    result.update(emotion_data or {})
                    logger.info(
                        f"😊 Emotion detected for {name}: "
                        f"{result.get('emotion', 'Neutral')} "
                        f"(conf={float(result.get('emotion_confidence') or 0.0):.2f})"
                    )
                except Exception as e:
                    logger.error(f"❌ Emotion detection failed for {name}: {e}")
                    result.update(self._default_emotion_result("unavailable", str(e)))
            else:
                result.update(self._default_emotion_result("unavailable"))
                if not enable_emotion:
                    result['emotion_unavailable_reason'] = 'emotion_disabled'
                elif not emotion_detector_ready:
                    result['emotion_unavailable_reason'] = 'emotion_detector_unavailable'
                elif not emotion_model_loaded:
                    result['emotion_unavailable_reason'] = getattr(self.emotion_pipeline.backend, "last_error", None) or 'emotion_model_unavailable'
                else:
                    result['emotion_unavailable_reason'] = 'face_too_small_for_emotion'
            
            # ACTIVITY DETECTION - Optional, doesn't block attendance
            # Uses full frame + face bbox for comprehensive activity analysis
            if enable_activity and self.activity_detector is not None:
                try:
                    activity, activity_confidence = self.activity_detector.detect_activity(
                        original_frame, face_bbox
                    )
                    result['activity'] = activity
                    result['activity_confidence'] = float(activity_confidence)
                    logger.info(f"✓ Activity detected: {name} -> {activity} (confidence={activity_confidence:.2f})")
                except Exception as e:
                    logger.error(f"❌ Activity detection failed for {name}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    result['activity'] = 'Unknown'
                    result['activity_confidence'] = 0.0
            else:
                logger.debug(f"Activity detection disabled for {name}")
            
            return result
        except Exception as e:
            logger.error(f"Face recognition failed: {e}")
            return None

    def _default_emotion_result(self, provider="unavailable", reason=None):
        return {
            "emotion": LOW_SIGNAL_EMOTION,
            "emotion_confidence": 0.0,
            "emotion_intensity": "low",
            "all_emotions": {},
            "raw_emotion": LOW_SIGNAL_EMOTION,
            "raw_confidence": 0.0,
            "smoothed_emotion": "LowSignal",
            "smoothed_confidence": 0.0,
            "derived_emotion": "Passive",
            "educational_state": "Waiting",
            "classroom_state": "Calm Classroom",
            "quality_score": 0.0,
            "face_size": 0,
            "blur_score": 0.0,
            "brightness": 0.0,
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
            "occlusion_score": 1.0,
            "attention": 0.0,
            "engagement": 0.0,
            "emotion_available": False,
            "emotion_provider": provider,
            "pipeline_version": PIPELINE_VERSION,
            "fallback_backend_used": False,
            "below_analytics_threshold": True,
            "low_signal_state": True,
            "emotion_unavailable_reason": reason,
            "legacy_emotion_source": "low_signal",
        }

    def _infer_emotion_signal(
        self,
        face_crop,
        face_bbox,
        landmarks,
        camera_key,
        track_key,
        enable_emotion,
        activity=None,
        activity_confidence=0.0,
        face_obj=None,
    ):
        if not enable_emotion or self.emotion_pipeline is None:
            return self._default_emotion_result("unavailable", "emotion_disabled")

        h_e, w_e = face_crop.shape[:2]
        original_face_size = int(min(h_e, w_e))
        if original_face_size < self.absolute_min_emotion_face_size:
            result = self._default_emotion_result("unavailable", "face_too_small_for_emotion")
            result["face_size"] = original_face_size
            return result

        prepared_face_crop = self._prepare_face_crop_for_emotion(face_crop)

        detection_confidence = 1.0
        if face_obj is not None:
            detection_confidence = float(getattr(face_obj, "det_score", 1.0) or 1.0)

        emotion_data = self.emotion_pipeline.analyze_face(
            face_roi=prepared_face_crop,
            landmarks=landmarks,
            detection_confidence=detection_confidence,
            track_key=str(track_key),
            timestamp=datetime.utcnow(),
            activity=activity,
            activity_confidence=activity_confidence,
        )
        emotion_data["face_size"] = original_face_size
        emotion_data["emotion_input_face_size"] = int(min(prepared_face_crop.shape[:2]))
        emotion_data["emotion_model_loaded"] = bool(getattr(self.emotion_pipeline.backend, "model_loaded", False))
        emotion_data["emotion_enabled"] = True
        emotion_data["emotion_backend"] = getattr(self.emotion_pipeline.backend, "name", None)
        emotion_data["emotion_model_name"] = getattr(self.emotion_pipeline.backend, "model_name", None)
        emotion_data["emotion_model_version"] = getattr(self.emotion_pipeline.backend, "model_version", None)
        if emotion_data.get("emotion_available"):
            self.last_emotion_detection_at[camera_key] = datetime.utcnow().isoformat()
            self.emotion_detection_error[camera_key] = None
        elif emotion_data.get("emotion_unavailable_reason"):
            self.emotion_detection_error[camera_key] = emotion_data.get("emotion_unavailable_reason")
        return emotion_data

    def _prepare_face_crop_for_emotion(self, face_crop):
        try:
            prepared = face_crop
            min_side = int(min(prepared.shape[:2]))
            if min_side < self.target_emotion_face_size:
                scale = self.target_emotion_face_size / float(max(min_side, 1))
                new_width = max(1, int(round(prepared.shape[1] * scale)))
                new_height = max(1, int(round(prepared.shape[0] * scale)))
                prepared = cv2.resize(prepared, (new_width, new_height), interpolation=cv2.INTER_CUBIC)

            lab = cv2.cvtColor(prepared, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
            normalized = cv2.merge((l_channel, a_channel, b_channel))
            normalized = cv2.cvtColor(normalized, cv2.COLOR_LAB2BGR)
            return normalized
        except Exception as exc:
            logger.debug(f"Emotion face-crop preparation failed: {exc}")
            return face_crop
    
    def _crop_face(self, frame, face_bbox):
        """
        Extract face region from frame with MINIMAL padding to avoid overlapping crops.
        
        Args:
            frame: Video frame (BGR)
            face_bbox: Face bounding box [x, y, w, h]
        
        Returns:
            Cropped face image or None
        """
        try:
            # Handle different bbox formats
            if len(face_bbox) >= 4:
                x = int(face_bbox[0])
                y = int(face_bbox[1])
                w = int(face_bbox[2])
                h = int(face_bbox[3])
                
                # Ensure we're using width/height, not coordinates
                # If the values look like coordinates, convert them
                if w > 1000 or h > 1000:
                    # These look like x2, y2 coordinates instead of width/height
                    w = w - x
                    h = h - y
            else:
                return None
            
            # Use BALANCED padding (10 pixels) for optimal face isolation without overlap
            # 2px was too tight and cut off facial features causing recognition failures
            # 10px includes full face + some margins, standard for face recognition
            pad = 10
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(frame.shape[1], x + w + pad)
            y2 = min(frame.shape[0], y + h + pad)
            
            # Extract and return the face crop
            face_crop = frame[y1:y2, x1:x2].copy()
            
            # Verify we got a valid crop
            if face_crop.size == 0:
                logger.warning(f"Empty face crop at bbox {face_bbox}")
                return None
            
            return face_crop
        except Exception as e:
            logger.warning(f"Failed to crop face: {e}")
            return None

    def _camera_snapshot_dir(self, camera_id):
        return os.path.join(self.snapshots_dir, f'camera_{camera_id}')

    def _sanitize_snapshot_token(self, value):
        normalized = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value or '').strip())
        return normalized.strip('._') or "person"

    def _write_snapshot_atomic(self, image, filepath):
        """Write JPEG data atomically so the UI never reads a partial file."""
        try:
            success, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                return False

            encoded_bytes = encoded.tobytes()
            decoded = cv2.imdecode(np.frombuffer(encoded_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if decoded is None or decoded.size == 0:
                return False

            temp_path = f"{filepath}.tmp"
            with open(temp_path, 'wb') as snapshot_file:
                snapshot_file.write(encoded_bytes)
                snapshot_file.flush()
                os.fsync(snapshot_file.fileno())

            os.replace(temp_path, filepath)
            return True
        except Exception as e:
            logger.error(f"Failed atomic snapshot write for {filepath}: {e}")
            try:
                temp_path = f"{filepath}.tmp"
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False

    def _delete_snapshot_file(self, camera_id, filename):
        if not filename:
            return False

        try:
            filepath = os.path.join(self._camera_snapshot_dir(camera_id), filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception as e:
            logger.warning(f"Failed to delete snapshot {filename}: {e}")

        return False

    def _cleanup_snapshot_retention(self, camera_id):
        """Keep snapshots for 24h, cap unknown captures at 20, and clear stale references."""
        camera_dir = self._camera_snapshot_dir(camera_id)
        deleted_recognized = []

        if not os.path.exists(camera_dir):
            return

        cutoff = time.time() - (SNAPSHOT_RETENTION_HOURS * 3600)

        try:
            for filename in os.listdir(camera_dir):
                filepath = os.path.join(camera_dir, filename)
                if not os.path.isfile(filepath):
                    continue

                try:
                    if os.path.getmtime(filepath) <= cutoff:
                        os.remove(filepath)
                        if filename.startswith('recognized_'):
                            deleted_recognized.append(filename)
                except FileNotFoundError:
                    continue

            if self.profile_db:
                for snapshot_name in self.profile_db.cleanup_unknown_faces(
                    camera_id,
                    retention_hours=SNAPSHOT_RETENTION_HOURS,
                    keep_latest=MAX_UNKNOWN_SNAPSHOTS_PER_CAMERA
                ):
                    self._delete_snapshot_file(camera_id, snapshot_name)

            unknown_files = []
            for filename in os.listdir(camera_dir):
                filepath = os.path.join(camera_dir, filename)
                if os.path.isfile(filepath) and filename.startswith('unknown_face_'):
                    unknown_files.append((filename, os.path.getmtime(filepath)))

            if len(unknown_files) > MAX_UNKNOWN_SNAPSHOTS_PER_CAMERA:
                unknown_files.sort(key=lambda item: item[1], reverse=True)
                overflow = unknown_files[MAX_UNKNOWN_SNAPSHOTS_PER_CAMERA:]
                for filename, _ in overflow:
                    self._delete_snapshot_file(camera_id, filename)

            if deleted_recognized:
                self.attendance_tracker.clear_frame_path_references(deleted_recognized)
        except Exception as e:
            logger.warning(f"Snapshot cleanup failed for camera {camera_id}: {e}")
    
    def _save_unknown_face_snapshot(self, face_crop, camera_id):
        """
        Save unknown face snapshot to disk (cropped face only).
        
        Args:
            face_crop: Cropped face image (just the detected face region with minimal padding)
            camera_id: Camera identifier
        
        Returns:
            Path to saved snapshot
        """
        try:
            self._cleanup_snapshot_retention(camera_id)
            camera_dir = self._camera_snapshot_dir(camera_id)
            os.makedirs(camera_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # Include milliseconds
            filename = f'unknown_face_{timestamp}.jpg'
            filepath = os.path.join(camera_dir, filename)
            
            if not self._write_snapshot_atomic(face_crop, filepath):
                return None

            self._cleanup_snapshot_retention(camera_id)
            return filename
        except Exception as e:
            logger.error(f"Failed to save face snapshot: {e}")
            return None
    
    def _save_face_snapshot(self, face_crop, camera_id, person_name, profile_id=None):
        """
        Save recognized face snapshot to disk for attendance validation.
        Stores just the detected face region with minimal padding.
        
        Args:
            face_crop: Cropped face image (just the detected face region with minimal padding)
            camera_id: Camera identifier
            person_name: Name of recognized person
        
        Returns:
            Filename of saved snapshot (for storing in attendance_log)
        """
        try:
            self._cleanup_snapshot_retention(camera_id)
            camera_dir = self._camera_snapshot_dir(camera_id)
            os.makedirs(camera_dir, exist_ok=True)
            
            safe_name = self._sanitize_snapshot_token(person_name)
            identifier = self._sanitize_snapshot_token(profile_id if profile_id is not None else person_name)
            filename = f'recognized_{identifier}_{safe_name}.jpg'
            filepath = os.path.join(camera_dir, filename)
            
            if not self._write_snapshot_atomic(face_crop, filepath):
                return None

            return filename
        except Exception as e:
            logger.error(f"Failed to save recognized face snapshot: {e}")
            return None
    
    def get_current_detections(self, camera_id):
        """
        Get current detection results for a camera.
        
        Args:
            camera_id: Camera identifier
        
        Returns:
            dict with known_faces, unknown_faces, and timestamp
        """
        return self.current_detections.get(camera_id, {
            'updated_at': None,
            'known_faces': [],
            'unknown_faces': [],
            'total_faces': 0
        })
    
    def get_unknown_face_snapshots(self, camera_id, limit=50):
        """
        Get list of unknown face snapshots for a camera.
        
        Args:
            camera_id: Camera identifier
            limit: Maximum snapshots to return
        
        Returns:
            List of snapshot info dicts
        """
        try:
            self._cleanup_snapshot_retention(camera_id)
            camera_dir = self._camera_snapshot_dir(camera_id)
            if not os.path.exists(camera_dir):
                return []
            
            files = [name for name in sorted(os.listdir(camera_dir), reverse=True) if name.startswith('unknown_face_')][:limit]
            snapshots = []
            
            for filename in files:
                filepath = os.path.join(camera_dir, filename)
                if not os.path.isfile(filepath):
                    continue
                stat = os.stat(filepath)
                snapshots.append({
                    'filename': filename,
                    'size_kb': stat.st_size / 1024,
                    'timestamp': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            
            return snapshots
        except Exception as e:
            logger.warning(f"Failed to get snapshots: {e}")
            return []
    
    def get_snapshot_image(self, camera_id, filename):
        """
        Get base64-encoded snapshot image.
        
        Args:
            camera_id: Camera identifier
            filename: Snapshot filename
        
        Returns:
            Base64-encoded image data
        """
        try:
            filepath = os.path.join(self.snapshots_dir, f'camera_{camera_id}', filename)
            
            # Security check: ensure path is within snapshots directory
            real_path = os.path.realpath(filepath)
            safe_dir = os.path.realpath(self.snapshots_dir)
            if not real_path.startswith(safe_dir):
                logger.warning(f"Attempted path traversal: {filepath}")
                return None
            
            if not os.path.exists(real_path):
                return None
            
            with open(real_path, 'rb') as f:
                image_data = f.read()
            
            return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to get snapshot image: {e}")
            return None
    
    def _get_camera_stream(self, camera_id, max_retries=3):
        """
        Get camera stream from database and open CV2 VideoCapture.
        
        Args:
            camera_id: Camera database ID
            max_retries: Number of connection retry attempts
        
        Returns:
            tuple: (cap, camera_name) or (None, None) on failure
        """
        try:
            doc = mongo_store.collection("cctv_cameras").find_one(
                {"_id": camera_id, "enabled": True}
            )
            if not doc:
                logger.error(f"Camera {camera_id} not found or disabled")
                return None, None
            row = (
                doc["_id"],
                doc["name"],
                doc["source"],
                doc.get("camera_type") or doc.get("type"),
                doc.get("username"),
                doc.get("password"),
            )

            if not row:
                logger.error(f"Camera {camera_id} not found or disabled")
                return None, None
            
            camera_id, camera_name, source, camera_type, username, password = row

            # Normalize type because rows are stored as lowercase in this project,
            # while older logic here only handled uppercase values.
            normalized_camera_type = (camera_type or '').strip().lower()

            # Build connection URL with credentials
            url = build_camera_source_url(
                source=source,
                camera_type=normalized_camera_type,
                username=username,
                password=password,
            )
            
            logger.info(f"Opening camera stream: {camera_name} from {camera_type} source")
            
            # Attempt to open stream with retries and timeout
            for attempt in range(max_retries):
                try:
                    # Open camera with threading wrapper to enforce timeout
                    import queue
                    result_queue = queue.Queue()
                    
                    def open_camera_with_timeout():
                        try:
                            cap = cv2.VideoCapture(url)
                            # Try to grab to ensure it's actually connected
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            result_queue.put(cap if cap.isOpened() else None)
                        except Exception as e:
                            logger.warning(f"Exception opening camera: {e}")
                            result_queue.put(None)
                    
                    thread = threading.Thread(target=open_camera_with_timeout, daemon=True)
                    thread.start()
                    thread.join(timeout=8)  # 8 second timeout for camera opening
                    
                    if not result_queue.empty():
                        cap = result_queue.get_nowait()
                        if cap is not None:
                            logger.info(f"✓ Camera stream opened: {camera_name}")
                            return cap, camera_name
                        else:
                            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Camera failed to open {camera_name}")
                    else:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries}: Timeout opening {camera_name} (camera unreachable or slow)")
                        
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries}: Error opening {camera_name}: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait 1 second before retry
            
            logger.error(f"Failed to open camera stream after {max_retries} attempts: {camera_name}")
            return None, None
        except Exception as e:
            logger.error(f"Error getting camera stream: {e}")
            return None, None
    
    def _stream_worker(self, camera_id):
        """
        Worker thread for processing a single camera stream with automatic reconnection.
        
        Args:
            camera_id: Camera database ID
        """
        cap = None
        camera_name = ""
        frame_count = 0
        recognized_count = 0
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        
        try:
            stop_event = self.stop_events.get(camera_id)
            runtime_config = self._get_camera_runtime_config(camera_id)
            min_processing_interval = 1.0 / max(1.0, runtime_config.get("target_fps", self.target_processing_fps))

            # Open camera stream with retry logic
            cap, camera_name = self._get_camera_stream(camera_id, max_retries=5)
            if cap is None:
                active_backend = self._active_emotion_backend()
                self.recognition_active[camera_id] = False
                self.recognition_stats[camera_id] = {
                    'status': 'error',
                    'message': 'Failed to open camera stream',
                    'frames_processed': 0,
                    'faces_recognized': 0,
                    'emotion_enabled': runtime_config.get("enable_emotion", False),
                    'emotion_model_loaded': active_backend.get("model_loaded", False),
                    'emotion_backend': active_backend.get("backend"),
                    'emotion_model_name': active_backend.get("model_name"),
                    'emotion_model_version': active_backend.get("model_version"),
                }
                self._publish_runtime_state(camera_id, camera_name, is_running=False)
                return

            self.active_captures[camera_id] = cap
            active_backend = self._active_emotion_backend()
            self.recognition_stats[camera_id] = {
                **self.recognition_stats.get(camera_id, {}),
                'status': 'running',
                'camera_name': camera_name,
                'message': '',
                'emotion_enabled': runtime_config.get("enable_emotion", False),
                'emotion_model_loaded': active_backend.get("model_loaded", False),
                'emotion_backend': active_backend.get("backend"),
                'emotion_model_name': active_backend.get("model_name"),
                'emotion_model_version': active_backend.get("model_version"),
            }
            self._publish_runtime_state(camera_id, camera_name, is_running=True)
            
            logger.info(f"Started recognition thread for camera: {camera_name}")
            reconnect_attempts = 0
            
            frame_skip_counter = 0
            consecutive_read_errors = 0
            max_consecutive_errors = 30
            
            while self.recognition_active.get(camera_id, False) and not (stop_event and stop_event.is_set()):
                try:
                    loop_started_at = time.perf_counter()
                    if stop_event and stop_event.is_set():
                        logger.info(f"Stop requested for camera {camera_id} before frame read")
                        break

                    ret, frame = cap.read()

                    if stop_event and stop_event.is_set():
                        logger.info(f"Stop requested for camera {camera_id} after frame read")
                        break
                    
                    # Handle frame read failures with reconnection logic
                    if not ret or frame is None:
                        consecutive_read_errors += 1
                        logger.warning(f"Failed to read frame from {camera_name} (error #{consecutive_read_errors}/{max_consecutive_errors})")
                        
                        # If too many consecutive errors, try to reconnect
                        if consecutive_read_errors > max_consecutive_errors:
                            logger.warning(f"Too many read errors for {camera_name}, attempting reconnection...")
                            if cap:
                                cap.release()
                                self.active_captures.pop(camera_id, None)
                            
                            # Try to reconnect
                            if reconnect_attempts < max_reconnect_attempts:
                                if stop_event and stop_event.wait(timeout=2):
                                    logger.info(f"Stop requested for camera {camera_id} during reconnect wait")
                                    break
                                cap, _ = self._get_camera_stream(camera_id, max_retries=3)
                                if cap is not None:
                                    self.active_captures[camera_id] = cap
                                    consecutive_read_errors = 0
                                    reconnect_attempts += 1
                                    logger.info(f"Reconnected to {camera_name} (attempt {reconnect_attempts})")
                                    continue
                                else:
                                    logger.error(f"Failed to reconnect to {camera_name}")
                                    break
                            else:
                                logger.error(f"Max reconnection attempts reached for {camera_name}")
                                break
                        continue
                    
                    # Reset consecutive error counter on successful frame read
                    consecutive_read_errors = 0
                    frame_count += 1
                    frame_skip_counter += 1
                    
                    # Skip frames for performance
                    if frame_skip_counter < self.frame_skip:
                        continue
                    
                    frame_skip_counter = 0
                    
                    # Resize frame adaptively for inference instead of forcing a single size.
                    frame_h, frame_w = frame.shape[:2]
                    inference_width = runtime_config.get("inference_width", 960)
                    if frame_w > inference_width:
                        scale = inference_width / float(frame_w)
                        inference_frame = cv2.resize(
                            frame,
                            (inference_width, max(1, int(frame_h * scale))),
                            interpolation=cv2.INTER_AREA,
                        )
                    else:
                        inference_frame = frame

                    recognized_faces = self._process_frame(inference_frame, camera_id, runtime_config=runtime_config)
                    
                    if recognized_faces or self.latest_class_activity.get(camera_id):
                        self.enqueue_recognition_persistence(
                            recognized_faces,
                            camera_name,
                            camera_id=camera_id,
                            class_activity=self.latest_class_activity.get(camera_id),
                        )
                        recognized_count += sum(
                            1 for face in recognized_faces
                            if face.get('profile_id', 0) not in (-1, None) and face.get('frame_path') is not None
                        )
                    
                    # Update stats every 100 frames
                    if frame_count % 100 == 0:
                        self.recognition_stats[camera_id] = {
                            'status': 'running',
                            'frames_processed': frame_count,
                            'faces_recognized': recognized_count,
                            'fps': frame_count / (time.time() - self.recognition_stats.get(camera_id, {}).get('start_time', time.time())),
                            'reconnect_attempts': reconnect_attempts,
                            'camera_name': camera_name,
                            'emotion_enabled': runtime_config.get("enable_emotion", False),
                            'emotion_model_loaded': active_backend.get("model_loaded", False),
                            'emotion_backend': active_backend.get("backend"),
                            'emotion_model_name': active_backend.get("model_name"),
                            'emotion_model_version': active_backend.get("model_version"),
                            'last_emotion_detection_at': self.last_emotion_detection_at.get(camera_id),
                            'emotion_detection_error': self.emotion_detection_error.get(camera_id),
                        }
                        self._publish_runtime_state(camera_id, camera_name, is_running=True)

                    elapsed = time.perf_counter() - loop_started_at
                    remaining = min_processing_interval - elapsed
                    if remaining > 0:
                        if stop_event and stop_event.wait(timeout=remaining):
                            break
                        time.sleep(0)
                    
                except Exception as e:
                    logger.error(f"Error processing frame from {camera_name}: {e}")
                    consecutive_read_errors += 1
                    continue
        
        except Exception as e:
            logger.error(f"Recognition thread error for camera {camera_id}: {e}")
            self.recognition_stats[camera_id] = {
                **self.recognition_stats.get(camera_id, {}),
                'status': 'error',
                'message': str(e),
                'camera_name': camera_name,
            }
            self._publish_runtime_state(camera_id, camera_name, is_running=False)
        
        finally:
            # Cleanup
            if cap is not None:
                cap.release()
            self.active_captures.pop(camera_id, None)
            self.stop_events.pop(camera_id, None)
            self.recognition_threads.pop(camera_id, None)
            
            self.recognition_active[camera_id] = False
            self.recognition_stats[camera_id] = {
                'status': 'stopped',
                'camera_name': camera_name,
                'frames_processed': frame_count,
                'faces_recognized': recognized_count,
                'reconnect_attempts': reconnect_attempts,
                'uptime': time.time() - self.recognition_stats.get(camera_id, {}).get('start_time', time.time())
            }
            self._publish_runtime_state(camera_id, camera_name, is_running=False)
            
            logger.info(f"✓ Recognition stopped for {camera_name} (frames: {frame_count}, recognized: {recognized_count}, reconnects: {reconnect_attempts})")
    
    def start_recognition(self, camera_id):
        """
        Start face recognition on a camera.
        
        Args:
            camera_id: Camera database ID
        
        Returns:
            dict: Status message
        """
        # Skip LOCAL_WEBCAM - it's handled by the background thread in server.py
        try:
            doc = mongo_store.collection("cctv_cameras").find_one(
                {"_id": camera_id},
                {"camera_type": 1, "type": 1},
            )
            row = ((doc or {}).get("camera_type") or (doc or {}).get("type"),) if doc else None
            
            if row and row[0] == 'LOCAL_WEBCAM':
                return {
                    'success': True,
                    'message': f'Camera {camera_id} is LOCAL_WEBCAM - using background thread for recognition'
                }
        except Exception as e:
            logger.warning(f"Failed to check camera type: {e}")
        
        # Check if already running
        if self.recognition_active.get(camera_id, False):
            return {
                'success': False,
                'message': f'Recognition already running for camera {camera_id}'
            }
        
        try:
            # Start recognition thread
            self.recognition_active[camera_id] = True
            stop_event = threading.Event()
            self.stop_events[camera_id] = stop_event
            self.recognition_stats[camera_id] = {
                'status': 'starting',
                'start_time': time.time()
            }
            self._publish_runtime_state(camera_id, is_running=True)
            
            thread = threading.Thread(
                target=self._stream_worker,
                args=(camera_id,),
                daemon=True,
                name=f"recognition-camera-{camera_id}"
            )
            thread.start()
            self.recognition_threads[camera_id] = thread
            
            logger.info(f"✓ Recognition started for camera {camera_id}")
            return {
                'success': True,
                'message': f'Recognition started for camera {camera_id}'
            }
        except Exception as e:
            logger.error(f"Failed to start recognition: {e}")
            return {
                'success': False,
                'message': f'Failed to start recognition: {str(e)}'
            }
    
    def stop_recognition(self, camera_id):
        """
        Stop face recognition on a camera.
        
        Args:
            camera_id: Camera database ID
        
        Returns:
            dict: Status message with stats
        """
        if not self.recognition_active.get(camera_id, False):
            return {
                'success': False,
                'message': f'Recognition not running for camera {camera_id}'
            }
        
        try:
            self.recognition_active[camera_id] = False
            self.recognition_stats[camera_id] = {
                **self.recognition_stats.get(camera_id, {}),
                'status': 'stopping'
            }
            self._publish_runtime_state(camera_id, is_running=False)

            stop_event = self.stop_events.get(camera_id)
            if stop_event:
                stop_event.set()

            cap = self.active_captures.get(camera_id)
            if cap is not None:
                try:
                    cap.release()
                except Exception as release_error:
                    logger.warning(f"Failed to release capture for camera {camera_id}: {release_error}")
            
            # Wait for thread to finish (with timeout)
            thread = self.recognition_threads.get(camera_id)
            if thread:
                thread.join(timeout=1.5)
            
            stats = self.recognition_stats.get(camera_id, {})
            thread_stopped = not thread or not thread.is_alive()
            logger.info(f"✓ Recognition stop requested for camera {camera_id}: {stats}")
            
            return {
                'success': True,
                'message': (
                    f'Recognition stopped for camera {camera_id}'
                    if thread_stopped else
                    f'Recognition stop requested for camera {camera_id}'
                ),
                'stats': stats
            }
        except Exception as e:
            logger.error(f"Error stopping recognition: {e}")
            return {
                'success': False,
                'message': f'Error stopping recognition: {str(e)}'
            }
    
    def get_recognition_status(self, camera_id):
        """
        Get recognition status for a camera.
        
        Args:
            camera_id: Camera database ID
        
        Returns:
            dict: Current recognition status and stats
        """
        is_active = self.recognition_active.get(camera_id, False)
        stats = self.recognition_stats.get(camera_id, {})
        
        return {
            'camera_id': camera_id,
            'is_running': is_active,
            'status': stats.get('status', 'unknown'),
            'frames_processed': stats.get('frames_processed', 0),
            'faces_recognized': stats.get('faces_recognized', 0),
            'message': stats.get('message', '')
        }
    
    def get_all_recognition_status(self):
        """
        Get recognition status for all cameras.
        
        Returns:
            dict: Status for each camera
        """
        status_list = []
        
        try:
            rows = [
                (doc["_id"], doc["name"])
                for doc in mongo_store.collection("cctv_cameras").find(
                    {"enabled": True},
                    {"name": 1}
                ).sort("_id", 1)
            ]

            for row in rows:
                camera_id, camera_name = row
                cam_status = self.get_recognition_status(camera_id)
                cam_status['camera_name'] = camera_name
                status_list.append(cam_status)
        except Exception as e:
            logger.error(f"Failed to get all recognition status: {e}")
        
        return status_list
    
    def get_recognition_logs(self, camera_id=None, limit=100):
        """
        Get recognition logs from attendance records.
        
        Args:
            camera_id: Optional camera ID filter (currently doesn't filter by camera)
            limit: Maximum number of records to return
        
        Returns:
            List of recognition logs
        """
        try:
            query = {"status": "present"}
            cursor = mongo_store.collection("attendance_log").find(query).sort("timestamp", -1).limit(limit)
            return [
                {
                    'id': doc["_id"],
                    'profile_id': doc.get("profile_id"),
                    'name': doc.get("name"),
                    'status': doc.get("status"),
                    'confidence': doc.get("confidence"),
                    'emotion': doc.get("emotion"),
                    'timestamp': doc.get("timestamp"),
                }
                for doc in cursor
            ]
        except Exception as e:
            logger.error(f"Failed to get recognition logs: {e}")
            return []
