import os
from datetime import datetime

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store


CONTROL_COLLECTION = "recognition_runtime_control"
STATE_COLLECTION = "recognition_runtime_state"
DETECTIONS_COLLECTION = "recognition_runtime_detections"
WORKER_COLLECTION = "recognition_runtime_workers"

DEFAULT_WORKER_ID = os.getenv("CHRONOSENSE_RECOGNITION_WORKER_ID", "primary")


def _utcnow():
    return datetime.utcnow()


def ensure_runtime_indexes():
    from pymongo import ASCENDING

    mongo_store.collection(CONTROL_COLLECTION).create_index([("desired_running", ASCENDING)])
    mongo_store.collection(STATE_COLLECTION).create_index([("is_running", ASCENDING), ("updated_at", ASCENDING)])
    mongo_store.collection(DETECTIONS_COLLECTION).create_index([("updated_at", ASCENDING)])
    mongo_store.collection(WORKER_COLLECTION).create_index([("heartbeat_at", ASCENDING)])


def set_desired_state(camera_id, desired_running, mode="attendance", requested_by="api", extra=None):
    ensure_runtime_indexes()
    payload = {
        "desired_running": bool(desired_running),
        "mode": mode,
        "requested_by": requested_by,
        "updated_at": _utcnow(),
    }
    if extra:
        payload.update(extra)
    mongo_store.collection(CONTROL_COLLECTION).update_one(
        {"_id": camera_id},
        {"$set": payload, "$setOnInsert": {"created_at": _utcnow()}},
        upsert=True,
    )
    return get_desired_state(camera_id)


def get_desired_state(camera_id):
    doc = mongo_store.collection(CONTROL_COLLECTION).find_one({"_id": camera_id}) or {}
    return {
        "camera_id": camera_id,
        "desired_running": bool(doc.get("desired_running", False)),
        "mode": doc.get("mode", "attendance"),
        "requested_by": doc.get("requested_by"),
        "updated_at": doc.get("updated_at"),
    }


def list_desired_states():
    return list(mongo_store.collection(CONTROL_COLLECTION).find())


def set_runtime_state(camera_id, state):
    ensure_runtime_indexes()
    payload = dict(state or {})
    payload["camera_id"] = camera_id
    payload["updated_at"] = _utcnow()
    mongo_store.collection(STATE_COLLECTION).update_one(
        {"_id": camera_id},
        {"$set": payload, "$setOnInsert": {"created_at": _utcnow()}},
        upsert=True,
    )
    return get_runtime_state(camera_id)


def get_runtime_state(camera_id):
    doc = mongo_store.collection(STATE_COLLECTION).find_one({"_id": camera_id}) or {}
    if not doc:
        return {
            "camera_id": camera_id,
            "is_running": False,
            "status": "stopped",
            "frames_processed": 0,
            "faces_recognized": 0,
            "message": "",
        }
    doc["camera_id"] = camera_id
    doc.setdefault("is_running", False)
    doc.setdefault("status", "stopped")
    doc.setdefault("frames_processed", 0)
    doc.setdefault("faces_recognized", 0)
    doc.setdefault("message", "")
    return doc


def list_runtime_states():
    return list(mongo_store.collection(STATE_COLLECTION).find())


def set_latest_detections(camera_id, detections):
    ensure_runtime_indexes()
    payload = mongo_store.normalize_mongo_value(dict(detections or {}))
    payload["camera_id"] = camera_id
    payload["updated_at"] = _utcnow()
    mongo_store.collection(DETECTIONS_COLLECTION).update_one(
        {"_id": camera_id},
        {"$set": payload, "$setOnInsert": {"created_at": _utcnow()}},
        upsert=True,
    )
    return get_latest_detections(camera_id)


def get_latest_detections(camera_id):
    doc = mongo_store.collection(DETECTIONS_COLLECTION).find_one({"_id": camera_id}) or {}
    return {
        "camera_id": camera_id,
        "updated_at": doc.get("updated_at"),
        "known_faces": doc.get("known_faces", []),
        "unknown_faces": doc.get("unknown_faces", []),
        "total_faces": doc.get("total_faces", 0),
    }


def update_worker_heartbeat(worker_id=DEFAULT_WORKER_ID, state=None):
    ensure_runtime_indexes()
    payload = dict(state or {})
    payload["worker_id"] = worker_id
    payload["heartbeat_at"] = _utcnow()
    mongo_store.collection(WORKER_COLLECTION).update_one(
        {"_id": worker_id},
        {"$set": payload, "$setOnInsert": {"created_at": _utcnow()}},
        upsert=True,
    )


def get_worker_state(worker_id=DEFAULT_WORKER_ID):
    doc = mongo_store.collection(WORKER_COLLECTION).find_one({"_id": worker_id}) or {}
    if doc:
        doc["worker_id"] = worker_id
    return doc


def clear_camera_runtime(camera_id):
    mongo_store.collection(CONTROL_COLLECTION).delete_one({"_id": camera_id})
    mongo_store.collection(STATE_COLLECTION).delete_one({"_id": camera_id})
    mongo_store.collection(DETECTIONS_COLLECTION).delete_one({"_id": camera_id})
