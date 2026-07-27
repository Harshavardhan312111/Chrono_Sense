import logging
from datetime import datetime
from typing import Dict, List, Tuple

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store

logger = logging.getLogger(__name__)


class CCTVCamera:
    def __init__(
        self,
        camera_id: int,
        name: str,
        source: str,
        camera_type: str = "rtsp",
        username: str = None,
        password: str = None,
        fps: int = 30,
        resolution: Tuple[int, int] = (800, 600),
        inference_width: int = 960,
        target_fps: float = 8.0,
        recognition_threshold_override: float = None,
        enable_emotion: bool = None,
        enable_activity: bool = None,
        wing: str = None,
        room_number: str = None,
        camera_context: str = None,
        class_name: str = None,
        section_name: str = None,
        front_zone: str = None,
        board_zone: str = None,
        student_seating_zone: str = None,
        faculty_workstation_zone: str = None,
    ):
        self.id = camera_id
        self.name = name
        self.source = source
        self.type = camera_type
        self.username = username
        self.password = password
        self.fps = fps
        self.resolution = resolution
        self.inference_width = inference_width
        self.target_fps = target_fps
        self.recognition_threshold_override = recognition_threshold_override
        self.enable_emotion = enable_emotion
        self.enable_activity = enable_activity
        self.wing = wing
        self.room_number = room_number
        self.camera_context = camera_context
        self.class_name = class_name
        self.section_name = section_name
        self.front_zone = front_zone
        self.board_zone = board_zone
        self.student_seating_zone = student_seating_zone
        self.faculty_workstation_zone = faculty_workstation_zone


class CCTVManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._camera_status: Dict[int, str] = {}
        mongo_store.ensure_connected()
        logger.info("✓ CCTV database initialized")

    def add_camera(
        self,
        name: str,
        source: str,
        camera_type: str = "rtsp",
        username: str = None,
        password: str = None,
        fps: int = 30,
        resolution: Tuple[int, int] = (800, 600),
        inference_width: int = 960,
        target_fps: float = 8.0,
        recognition_threshold_override: float = None,
        enable_emotion: bool = None,
        enable_activity: bool = None,
        wing: str = None,
        room_number: str = None,
        camera_context: str = None,
        class_name: str = None,
        section_name: str = None,
        front_zone: str = None,
        board_zone: str = None,
        student_seating_zone: str = None,
        faculty_workstation_zone: str = None,
    ) -> int:
        try:
            camera_id = mongo_store.next_id("cctv_cameras")
            mongo_store.collection("cctv_cameras").insert_one(
                {
                    "_id": camera_id,
                    "name": name,
                    "source": source,
                    "camera_type": camera_type,
                    "type": camera_type,
                    "username": username,
                    "password": password,
                    "fps": fps,
                    "resolution": list(resolution),
                    "inference_width": inference_width,
                    "target_fps": target_fps,
                    "recognition_threshold_override": recognition_threshold_override,
                    "enable_emotion": enable_emotion,
                    "enable_activity": enable_activity,
                    "wing": wing,
                    "room_number": room_number,
                    "camera_context": camera_context,
                    "class_name": class_name,
                    "section_name": section_name,
                    "front_zone": front_zone,
                    "board_zone": board_zone,
                    "student_seating_zone": student_seating_zone,
                    "faculty_workstation_zone": faculty_workstation_zone,
                    "enabled": True,
                    "created_at": datetime.utcnow(),
                    "last_modified": datetime.utcnow(),
                }
            )
            return camera_id
        except Exception as exc:
            logger.error(f"Failed to add camera: {exc}")
            return -1

    def get_all_cameras(self) -> List[Dict]:
        try:
            cameras = []
            for doc in mongo_store.collection("cctv_cameras").find().sort("_id", 1):
                resolution = tuple(doc.get("resolution", [800, 600]))
                cameras.append(
                    {
                        "id": doc["_id"],
                        "name": doc["name"],
                        "source": doc["source"],
                        "type": doc.get("camera_type") or doc.get("type", "rtsp"),
                        "username": doc.get("username"),
                        "password": doc.get("password"),
                        "fps": doc.get("fps", 30),
                        "resolution": resolution,
                        "inference_width": int(doc.get("inference_width", 960) or 960),
                        "target_fps": float(doc.get("target_fps", 8.0) or 8.0),
                        "recognition_threshold_override": doc.get("recognition_threshold_override"),
                        "enable_emotion": doc.get("enable_emotion"),
                        "enable_activity": doc.get("enable_activity"),
                        "wing": doc.get("wing"),
                        "room_number": doc.get("room_number"),
                        "camera_context": doc.get("camera_context"),
                        "class_name": doc.get("class_name"),
                        "section_name": doc.get("section_name"),
                        "front_zone": doc.get("front_zone"),
                        "board_zone": doc.get("board_zone"),
                        "student_seating_zone": doc.get("student_seating_zone"),
                        "faculty_workstation_zone": doc.get("faculty_workstation_zone"),
                        "enabled": bool(doc.get("enabled", True)),
                    }
                )
            return cameras
        except Exception as exc:
            logger.error(f"Failed to get cameras: {exc}")
            return []

    def update_camera(
        self,
        camera_id: int,
        name: str,
        source: str,
        camera_type: str = "rtsp",
        username: str = None,
        password: str = None,
        fps: int = 30,
        resolution: Tuple[int, int] = (800, 600),
        inference_width: int = 960,
        target_fps: float = 8.0,
        recognition_threshold_override: float = None,
        enable_emotion: bool = None,
        enable_activity: bool = None,
        wing: str = None,
        room_number: str = None,
        camera_context: str = None,
        class_name: str = None,
        section_name: str = None,
        front_zone: str = None,
        board_zone: str = None,
        student_seating_zone: str = None,
        faculty_workstation_zone: str = None,
    ) -> bool:
        try:
            result = mongo_store.collection("cctv_cameras").update_one(
                {"_id": camera_id},
                {
                    "$set": {
                        "name": name,
                        "source": source,
                        "camera_type": camera_type,
                        "type": camera_type,
                        "username": username,
                        "password": password,
                        "fps": fps,
                        "resolution": list(resolution),
                        "inference_width": inference_width,
                        "target_fps": target_fps,
                        "recognition_threshold_override": recognition_threshold_override,
                        "enable_emotion": enable_emotion,
                        "enable_activity": enable_activity,
                        "wing": wing,
                        "room_number": room_number,
                        "camera_context": camera_context,
                        "class_name": class_name,
                        "section_name": section_name,
                        "front_zone": front_zone,
                        "board_zone": board_zone,
                        "student_seating_zone": student_seating_zone,
                        "faculty_workstation_zone": faculty_workstation_zone,
                        "last_modified": datetime.utcnow(),
                    }
                },
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update camera {camera_id}: {exc}")
            return False

    def get_wing_options(self) -> List[str]:
        try:
            wings = mongo_store.collection("cctv_cameras").distinct(
                "wing", {"wing": {"$nin": [None, ""]}}
            )
            return sorted(wings)
        except Exception as exc:
            logger.error(f"Failed to get wing options: {exc}")
            return []

    def remove_camera(self, camera_id: int) -> bool:
        try:
            result = mongo_store.collection("cctv_cameras").delete_one({"_id": camera_id})
            self._camera_status.pop(camera_id, None)
            return result.deleted_count > 0
        except Exception as exc:
            logger.error(f"Failed to remove camera {camera_id}: {exc}")
            return False

    def set_camera_enabled(self, camera_id: int, enabled: bool) -> bool:
        try:
            result = mongo_store.collection("cctv_cameras").update_one(
                {"_id": camera_id},
                {"$set": {"enabled": bool(enabled), "last_modified": datetime.utcnow()}},
            )
            if result.modified_count > 0 and not enabled:
                self._camera_status[camera_id] = "disabled"
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to set enabled={enabled} for camera {camera_id}: {exc}")
            return False

    def update_camera_status(self, camera_id: int, status: str, error_message: str = None):
        self._camera_status[camera_id] = status
        if error_message:
            logger.warning(f"Camera {camera_id} status: {status} - {error_message}")

    def get_camera_latest_status(self, camera_id: int) -> str:
        return self._camera_status.get(camera_id, "unknown")
