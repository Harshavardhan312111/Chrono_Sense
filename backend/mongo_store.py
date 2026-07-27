import os
from datetime import datetime

from dotenv import load_dotenv
import numpy as np

load_dotenv()


class MongoStoreError(RuntimeError):
    pass


class MongoStore:
    def __init__(self):
        self.uri = os.getenv("MONGO_URI", "").strip()
        self.db_name = os.getenv("MONGO_DB_NAME", "chronosense").strip() or "chronosense"
        self.timeout_ms = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "5000"))
        self._client = None
        self._db = None

    def ensure_connected(self):
        if not self.uri:
            raise MongoStoreError(
                "MongoDB is required. Set MONGO_URI and start a reachable MongoDB instance."
            )

        if self._db is not None:
            return self._db

        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise MongoStoreError(
                "PyMongo is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        self._client = MongoClient(self.uri, serverSelectionTimeoutMS=self.timeout_ms)
        try:
            self._client.admin.command("ping")
        except Exception as exc:
            self._client = None
            self._db = None
            raise MongoStoreError(
                "Failed to connect to MongoDB at "
                f"{self.uri} (db={self.db_name}, timeout_ms={self.timeout_ms}). "
                "Start MongoDB or update MONGO_URI/MONGO_DB_NAME in .env."
            ) from exc
        self._db = self._client[self.db_name]
        self.ensure_indexes()
        return self._db

    @property
    def enabled(self):
        return bool(self.uri)

    def is_available(self):
        self.ensure_connected()
        return True

    @property
    def db(self):
        return self.ensure_connected()

    def collection(self, name):
        return self.db[name]

    def next_id(self, sequence_name):
        from pymongo import ReturnDocument

        result = self.collection("counters").find_one_and_update(
            {"_id": sequence_name},
            {
                "$setOnInsert": {"created_at": datetime.utcnow()},
                "$inc": {"value": 1},
                "$set": {"updated_at": datetime.utcnow()},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(result["value"])

    @staticmethod
    def normalize_mongo_value(value):
        if isinstance(value, dict):
            return {
                str(key): MongoStore.normalize_mongo_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [MongoStore.normalize_mongo_value(item) for item in value]
        if isinstance(value, np.ndarray):
            return [MongoStore.normalize_mongo_value(item) for item in value.tolist()]
        if isinstance(value, np.generic):
            return value.item()
        return value

    def ensure_indexes(self):
        from pymongo import ASCENDING

        self.collection("users").create_index("username", unique=True)
        self.collection("profiles").create_index("name", unique=True)
        self.collection("profiles").create_index(
            [("profile_type", ASCENDING), ("class_name", ASCENDING), ("section_name", ASCENDING)]
        )
        self.collection("class_assignments").create_index(
            [("user_id", ASCENDING), ("class_name", ASCENDING), ("section_name", ASCENDING)],
            unique=True,
        )
        self.collection("cctv_cameras").create_index("name", unique=True)
        self.collection("attendance_log").create_index([("profile_id", ASCENDING), ("timestamp", ASCENDING)])
        self.collection("attendance_log").create_index([("location", ASCENDING), ("timestamp", ASCENDING)])
        self.collection("activity_log").create_index(
            [("profile_id", ASCENDING), ("unknown_face_id", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("activity_log").create_index(
            [("location", ASCENDING), ("activity", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("emotion_analytics").create_index(
            [("profile_id", ASCENDING), ("date", ASCENDING), ("emotion", ASCENDING)]
        )
        self.collection("emotion_events").create_index(
            [("profile_id", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("emotion_events").create_index(
            [("location", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("emotion_events").create_index(
            [("camera_id", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("unknown_faces").create_index([("camera_id", ASCENDING), ("last_seen", ASCENDING)])
        self.collection("camera_logs").create_index([("camera_id", ASCENDING), ("timestamp", ASCENDING)])
        self.collection("attendance_summary").create_index(
            [("profile_id", ASCENDING), ("date", ASCENDING)], unique=True
        )
        self.collection("class_schedule").create_index(
            [("date", ASCENDING), ("class_name", ASCENDING)], unique=True
        )
        self.collection("activity_summary").create_index(
            [("profile_id", ASCENDING), ("unknown_face_id", ASCENDING), ("date", ASCENDING), ("location", ASCENDING), ("activity", ASCENDING)],
            unique=True,
        )
        index_info = self.collection("activity_summary").index_information()
        legacy_activity_summary_index = "profile_id_1_date_1_location_1_activity_1"
        if legacy_activity_summary_index in index_info:
            self.collection("activity_summary").drop_index(legacy_activity_summary_index)
        self.collection("class_activity_log").create_index(
            [("camera_id", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("class_activity_log").create_index(
            [("location", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("class_activity_log").create_index(
            [("class_name", ASCENDING), ("section_name", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.collection("class_activity_summary").create_index(
            [("camera_id", ASCENDING), ("date", ASCENDING), ("class_name", ASCENDING), ("section_name", ASCENDING)],
            unique=True,
        )
        self.collection("sessions").create_index("expires_at", expireAfterSeconds=0)


mongo_store = MongoStore()
