import logging
import os
import signal
import sys
import time

import numpy as np
from dotenv import load_dotenv
from logging_setup import configure_logging

load_dotenv()

from ai_engine import ChronoEngine
from attendance import AttendanceTracker
from cctv_manager import CCTVManager
from cctv_recognition import CCTVRecognitionEngine
from database import ProfileDatabase
from recognition_runtime import (
    DEFAULT_WORKER_ID,
    list_desired_states,
    set_runtime_state,
    update_worker_heartbeat,
)

configure_logging(os.getenv("CHRONOSENSE_SERVICE_NAME") or "recognition-worker")
logger = logging.getLogger(__name__)

ENABLE_EMOTION_DETECTION = os.getenv("CHRONOSENSE_EMOTION_ENABLED_DEFAULT", "true").lower() == "true"
ENABLE_ACTIVITY_DETECTION = os.getenv("CHRONOSENSE_ACTIVITY_ENABLED_DEFAULT", "false").lower() == "true"
ENABLE_UNKNOWN_FACE_TRACKING = os.getenv(
    "CHRONOSENSE_UNKNOWN_FACE_TRACKING",
    "true" if (ENABLE_EMOTION_DETECTION or ENABLE_ACTIVITY_DETECTION) else "false",
).lower() == "true"
WORKER_POLL_INTERVAL = max(0.25, float(os.getenv("CHRONOSENSE_RECOGNITION_WORKER_POLL_SECONDS", "0.5")))
HEARTBEAT_INTERVAL = max(1.0, float(os.getenv("CHRONOSENSE_RECOGNITION_WORKER_HEARTBEAT_SECONDS", "2")))
PROFILE_REFRESH_INTERVAL = max(1.0, float(os.getenv("CHRONOSENSE_RECOGNITION_PROFILE_REFRESH_SECONDS", "5")))
CAMERA_FAILURE_BACKOFF_SECONDS = max(
    5.0,
    float(os.getenv("CHRONOSENSE_CAMERA_FAILURE_BACKOFF_SECONDS", "20")),
)
DEFAULT_RECOGNITION_THRESHOLD = float(os.getenv("CHRONOSENSE_RECOGNITION_THRESHOLD", "0.28"))


class RecognitionWorker:
    def __init__(self):
        self.worker_id = os.getenv("CHRONOSENSE_RECOGNITION_WORKER_ID", DEFAULT_WORKER_ID)
        self.running = True
        self.last_heartbeat_at = 0.0
        self.last_profile_refresh_at = 0.0
        self.camera_retry_after = {}

        self.engine = ChronoEngine(
            recognition_threshold=DEFAULT_RECOGNITION_THRESHOLD,
            matching_metric="hybrid",
            enable_emotion_detection=False,
        )
        self.profile_db = ProfileDatabase()
        self.attendance_tracker = AttendanceTracker(self.profile_db.db_path)
        self.cctv_manager = CCTVManager(self.profile_db.db_path)
        self.recognition_engine = CCTVRecognitionEngine(
            db_path=self.profile_db.db_path,
            ai_engine=self.engine,
            attendance_tracker=self.attendance_tracker,
            profile_db=self.profile_db,
            enable_emotion_detection=ENABLE_EMOTION_DETECTION,
            enable_activity_detection=ENABLE_ACTIVITY_DETECTION,
            enable_unknown_face_tracking=ENABLE_UNKNOWN_FACE_TRACKING,
        )

    def refresh_profiles(self, force=False):
        now = time.time()
        if not force and (now - self.last_profile_refresh_at) < PROFILE_REFRESH_INTERVAL:
            return False

        all_profiles = self.profile_db.get_all_profiles()
        if not all_profiles:
            logger.warning("No profiles found for recognition worker startup.")
            return False

        next_profiles = {}
        for profile in all_profiles:
            profile_id = profile["id"]
            embedding = profile["embedding"]
            view_embeddings = profile.get("view_embeddings") or {}
            next_profiles[profile_id] = {
                "name": profile["name"],
                "embedding": embedding,
                "view_embeddings": view_embeddings,
                "created_at": profile["created_at"],
            }
            if not isinstance(embedding, np.ndarray):
                logger.warning(f"Profile {profile['name']} embedding is {type(embedding)}")

        self.engine.profiles = next_profiles
        self.last_profile_refresh_at = now
        logger.info(f"Recognition worker loaded {len(all_profiles)} profiles into memory.")
        return True

    def stop(self, *_args):
        logger.info("Recognition worker shutdown requested.")
        self.running = False

    def _heartbeat(self, status="running", error=None):
        now = time.time()
        if status != "running" or (now - self.last_heartbeat_at) >= HEARTBEAT_INTERVAL:
            active_camera_ids = [
                camera_id
                for camera_id, active in self.recognition_engine.recognition_active.items()
                if active
            ]
            update_worker_heartbeat(
                worker_id=self.worker_id,
                state={
                    "status": status,
                    "pid": os.getpid(),
                    "active_camera_ids": active_camera_ids,
                    "active_camera_count": len(active_camera_ids),
                    "error": error,
                },
            )
            self.last_heartbeat_at = now

    def _reconcile_camera(self, camera, desired_map):
        camera_id = camera["id"]
        camera_type = (camera.get("type") or "").upper()
        if camera_type == "LOCAL_WEBCAM":
            return

        desired_doc = desired_map.get(camera_id) or {}
        desired = bool(desired_doc.get("desired_running", False))
        desired_mode = desired_doc.get("mode", "attendance")
        current = self.recognition_engine.get_recognition_status(camera_id)
        is_running = bool(current.get("is_running"))

        enable_emotion = desired_mode == "emotion" or bool(camera.get("enable_emotion"))
        self.recognition_engine.enable_emotion_detection = enable_emotion
        if desired_mode == "activity":
            self.recognition_engine.enable_activity_detection = True
        elif desired_mode in {"attendance", "emotion"}:
            self.recognition_engine.enable_activity_detection = False

        retry_after = float(self.camera_retry_after.get(camera_id, 0.0) or 0.0)
        now = time.time()
        if desired and not is_running and retry_after > now:
            remaining = retry_after - now
            set_runtime_state(
                camera_id,
                {
                    "camera_name": camera["name"],
                    "is_running": False,
                    "status": "backoff",
                    "message": f"Waiting {remaining:.1f}s before retry after camera failure",
                    "worker_id": self.worker_id,
                },
            )
            return

        if camera.get("enabled", True) and desired and not is_running:
            logger.info(f"Starting worker recognition for camera {camera_id} ({camera['name']})")
            self.recognition_engine.start_recognition(camera_id)
        elif (not camera.get("enabled", True) or not desired) and is_running:
            logger.info(f"Stopping worker recognition for camera {camera_id} ({camera['name']})")
            self.recognition_engine.stop_recognition(camera_id)
        elif not camera.get("enabled", True) and not current.get("status"):
            set_runtime_state(
                camera_id,
                {
                    "camera_name": camera["name"],
                    "is_running": False,
                    "status": "disabled",
                    "message": "Camera disabled",
                    "worker_id": self.worker_id,
                },
            )

    def _stop_orphaned_cameras(self, known_camera_ids, desired_map):
        active_ids = list(self.recognition_engine.recognition_active.keys())
        for camera_id in active_ids:
            desired = bool((desired_map.get(camera_id) or {}).get("desired_running", False))
            if camera_id not in known_camera_ids or not desired:
                if self.recognition_engine.recognition_active.get(camera_id):
                    logger.info(f"Stopping orphaned or undesired camera {camera_id}")
                    self.recognition_engine.stop_recognition(camera_id)

    def run_forever(self):
        self.refresh_profiles(force=True)
        self._heartbeat(status="starting")

        while self.running:
            try:
                self.refresh_profiles()
                cameras = self.cctv_manager.get_all_cameras()
                desired_map = {doc["_id"]: doc for doc in list_desired_states()}
                known_camera_ids = {camera["id"] for camera in cameras}

                self._stop_orphaned_cameras(known_camera_ids, desired_map)

                for camera in cameras:
                    self._reconcile_camera(camera, desired_map)

                for camera_id, state in self.recognition_engine.recognition_stats.items():
                    if state.get("status") == "error":
                        self.camera_retry_after[camera_id] = time.time() + CAMERA_FAILURE_BACKOFF_SECONDS

                self._heartbeat(status="running")
                time.sleep(WORKER_POLL_INTERVAL)
            except Exception as exc:
                logger.exception("Recognition worker loop failed: %s", exc)
                self._heartbeat(status="error", error=str(exc))
                time.sleep(min(2.0, WORKER_POLL_INTERVAL * 2))

        for camera_id, active in list(self.recognition_engine.recognition_active.items()):
            if active:
                self.recognition_engine.stop_recognition(camera_id)
        self._heartbeat(status="stopped")


def main():
    worker = RecognitionWorker()
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
