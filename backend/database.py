import logging
import os
import re
from datetime import datetime, timedelta

import numpy as np

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store

logger = logging.getLogger(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "mongo")


class DuplicateProfileError(RuntimeError):
    pass


class ProfileDatabase:
    def __init__(self):
        self.db_path = DB_PATH
        mongo_store.ensure_connected()

    def _serialize_embedding(self, embedding):
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return embedding

    def _serialize_view_embeddings(self, view_embeddings):
        serialized = {}
        for view_name, payload in (view_embeddings or {}).items():
            if not payload:
                continue
            serialized[view_name] = {
                "embedding": self._serialize_embedding(payload.get("embedding")),
                "captured_at": payload.get("captured_at"),
                "image_path": payload.get("image_path"),
            }
        return serialized

    def _normalize_view_embeddings(self, doc):
        normalized = {}
        for view_name, payload in (doc.get("view_embeddings") or {}).items():
            embedding = payload.get("embedding")
            if embedding is None:
                continue
            normalized[view_name] = {
                "embedding": np.array(embedding, dtype=np.float32),
                "captured_at": payload.get("captured_at"),
                "image_path": payload.get("image_path"),
            }
        return normalized

    def _normalize_profile_doc(self, doc):
        if not doc:
            return None
        profile_status = doc.get("profile_status")
        profile_complete = doc.get("profile_complete")
        recognition_trained = doc.get("recognition_trained")
        if profile_complete is None:
            profile_complete = bool(doc.get("embedding")) and bool(doc.get("view_embeddings"))
        if recognition_trained is None:
            recognition_trained = profile_complete
        if not profile_status:
            profile_status = "completed" if profile_complete and recognition_trained else "incomplete"
        return {
            "id": doc["_id"],
            "name": doc["name"],
            "embedding": np.array(doc["embedding"], dtype=np.float32) if doc.get("embedding") is not None else None,
            "view_embeddings": self._normalize_view_embeddings(doc),
            "profile_type": doc.get("profile_type", "faculty"),
            "email": doc.get("email"),
            "department": doc.get("department"),
            "class_name": doc.get("class_name"),
            "section_name": doc.get("section_name"),
            "roll_number": doc.get("roll_number"),
            "check_in_time": doc.get("check_in_time", "09:00"),
            "check_out_time": doc.get("check_out_time", "17:00"),
            "created_at": doc.get("created_at"),
            "image_path": doc.get("image_path"),
            "profile_complete": bool(profile_complete),
            "recognition_trained": bool(recognition_trained),
            "profile_status": profile_status,
        }

    def _build_name_cleanup_patterns(self, name):
        trimmed = (name or "").strip()
        if not trimmed:
            return []

        compact = re.sub(r"\s+", " ", trimmed)
        patterns = [
            re.compile(rf"^{re.escape(trimmed)}$", re.IGNORECASE),
        ]
        if compact != trimmed:
            patterns.append(re.compile(rf"^{re.escape(compact)}$", re.IGNORECASE))
        return patterns

    def normalize_profile_name(self, name):
        return re.sub(r"\s+", " ", (name or "").strip())

    def add_profile(
        self,
        name,
        embedding,
        image_path=None,
        email=None,
        department=None,
        check_in_time="09:00",
        check_out_time="17:00",
        profile_type="faculty",
        class_name=None,
        section_name=None,
        roll_number=None,
        view_embeddings=None,
        profile_complete=None,
        recognition_trained=None,
        profile_status=None,
    ):
        normalized_name = self.normalize_profile_name(name)
        if profile_complete is None:
            profile_complete = bool(embedding is not None and view_embeddings)
        if recognition_trained is None:
            recognition_trained = bool(profile_complete)
        if profile_status is None:
            profile_status = "completed" if profile_complete and recognition_trained else "incomplete"

        try:
            from pymongo.errors import DuplicateKeyError

            profile_id = mongo_store.next_id("profiles")
            mongo_store.collection("profiles").insert_one(
                {
                    "_id": profile_id,
                    "name": normalized_name,
                    "embedding": self._serialize_embedding(embedding),
                    "view_embeddings": self._serialize_view_embeddings(view_embeddings),
                    "profile_type": profile_type,
                    "email": email,
                    "department": department,
                    "class_name": class_name,
                    "section_name": section_name,
                    "roll_number": roll_number,
                    "check_in_time": check_in_time,
                    "check_out_time": check_out_time,
                    "created_at": datetime.utcnow(),
                    "image_path": image_path,
                    "profile_complete": bool(profile_complete),
                    "recognition_trained": bool(recognition_trained),
                    "profile_status": profile_status,
                }
            )
            return profile_id
        except DuplicateKeyError as exc:
            raise DuplicateProfileError(f"Profile '{normalized_name}' already exists") from exc
        except Exception as exc:
            logger.error(f"Failed to add profile: {exc}")
            raise

    def get_profile(self, profile_id):
        try:
            return self._normalize_profile_doc(
                mongo_store.collection("profiles").find_one({"_id": profile_id})
            )
        except Exception as exc:
            logger.error(f"Failed to get profile: {exc}")
            return None

    def get_all_profiles(self, profile_type=None, class_name=None, section_name=None):
        try:
            query = {}
            if profile_type:
                query["profile_type"] = profile_type
            if class_name:
                query["class_name"] = class_name
            if section_name:
                query["section_name"] = section_name
            cursor = mongo_store.collection("profiles").find(query).sort("name", 1)
            return [self._normalize_profile_doc(doc) for doc in cursor]
        except Exception as exc:
            logger.error(f"Failed to get all profiles: {exc}")
            return []

    def delete_profile(self, profile_id):
        try:
            profiles = mongo_store.collection("profiles")
            profile = profiles.find_one({"_id": profile_id}, {"_id": 1, "name": 1})
            if not profile:
                return False

            profile_name = profile.get("name")
            deleted_profile_ids = {profile_id}

            delete_result = profiles.delete_one({"_id": profile_id})

            for name_pattern in self._build_name_cleanup_patterns(profile_name):
                duplicates = list(profiles.find({"name": name_pattern}, {"_id": 1}))
                if duplicates:
                    duplicate_ids = [doc["_id"] for doc in duplicates]
                    deleted_profile_ids.update(duplicate_ids)
                    profiles.delete_many({"_id": {"$in": duplicate_ids}})

            related_collections = [
                "attendance_log",
                "attendance_summary",
                "activity_log",
                "activity_summary",
                "emotion_analytics",
                "emotion_events",
            ]

            for collection_name in related_collections:
                mongo_store.collection(collection_name).delete_many({"profile_id": {"$in": list(deleted_profile_ids)}})

            mongo_store.collection("unknown_faces").delete_many({"profile_id": {"$in": list(deleted_profile_ids)}})

            if profile_name:
                name_filters = [{"name": profile_name}]
                for name_pattern in self._build_name_cleanup_patterns(profile_name):
                    name_filters.append({"name": name_pattern})
                mongo_store.collection("attendance_log").delete_many({"$or": name_filters})
                mongo_store.collection("emotion_events").delete_many({"$or": name_filters})

            return delete_result.deleted_count > 0
        except Exception as exc:
            logger.error(f"Failed to delete profile: {exc}")
            return False

    def update_profile(
        self,
        profile_id,
        name=None,
        email=None,
        department=None,
        check_in_time=None,
        check_out_time=None,
        profile_type=None,
        class_name=None,
        section_name=None,
        roll_number=None,
        profile_complete=None,
        recognition_trained=None,
        profile_status=None,
    ):
        updates = {}
        for key, value in {
            "name": name,
            "email": email,
            "department": department,
            "check_in_time": check_in_time,
            "check_out_time": check_out_time,
            "profile_type": profile_type,
            "class_name": class_name,
            "section_name": section_name,
            "roll_number": roll_number,
            "profile_complete": profile_complete,
            "recognition_trained": recognition_trained,
            "profile_status": profile_status,
        }.items():
            if value is not None:
                updates[key] = value
        if not updates:
            return False
        try:
            result = mongo_store.collection("profiles").update_one({"_id": profile_id}, {"$set": updates})
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update profile: {exc}")
            return False

    def get_profile_by_name(self, name):
        try:
            return self._normalize_profile_doc(mongo_store.collection("profiles").find_one({"name": name}))
        except Exception as exc:
            logger.error(f"Failed to get profile by name: {exc}")
            return None

    def update_profile_embedding(self, profile_id, embedding):
        try:
            result = mongo_store.collection("profiles").update_one(
                {"_id": profile_id},
                {"$set": {"embedding": self._serialize_embedding(embedding)}},
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update embedding: {exc}")
            return False

    def update_profile_view_embeddings(self, profile_id, primary_embedding, view_embeddings):
        try:
            result = mongo_store.collection("profiles").update_one(
                {"_id": profile_id},
                {
                    "$set": {
                        "embedding": self._serialize_embedding(primary_embedding),
                        "view_embeddings": self._serialize_view_embeddings(view_embeddings),
                        "profile_complete": True,
                        "recognition_trained": True,
                        "profile_status": "completed",
                    }
                },
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update view embeddings: {exc}")
            return False

    def get_profile_filters(self):
        try:
            profiles = self.get_all_profiles(profile_type="student")
            classes = sorted({profile.get("class_name") for profile in profiles if profile.get("class_name")})
            sections_by_class = {}
            for profile in profiles:
                class_name = profile.get("class_name")
                section_name = profile.get("section_name")
                if not class_name or not section_name:
                    continue
                sections_by_class.setdefault(class_name, [])
                if section_name not in sections_by_class[class_name]:
                    sections_by_class[class_name].append(section_name)
            for key in sections_by_class:
                sections_by_class[key].sort()
            return {"classes": classes, "sections_by_class": sections_by_class}
        except Exception as exc:
            logger.error(f"Failed to get profile filters: {exc}")
            return {"classes": [], "sections_by_class": {}}

    def get_profile_completion_counts(self):
        try:
            profiles = list(
                mongo_store.collection("profiles").find(
                    {},
                    {
                        "profile_complete": 1,
                        "recognition_trained": 1,
                        "embedding": 1,
                        "view_embeddings": 1,
                    },
                )
            )
            completed = 0
            incomplete = 0
            for doc in profiles:
                is_complete = doc.get("profile_complete")
                if is_complete is None:
                    is_complete = bool(doc.get("embedding")) and bool(doc.get("view_embeddings"))
                is_trained = doc.get("recognition_trained")
                if is_trained is None:
                    is_trained = bool(is_complete)
                if is_complete and is_trained:
                    completed += 1
                else:
                    incomplete += 1
            return {
                "completed": completed,
                "incomplete": incomplete,
                "total": len(profiles),
            }
        except Exception as exc:
            logger.error(f"Failed to get profile completion counts: {exc}")
            return {"completed": 0, "incomplete": 0, "total": 0}

    def add_unknown_face(self, camera_id, snapshot_path, face_bbox, unknown_face_id=None, embedding=None, profile_id=None):
        try:
            unknown_id = mongo_store.next_id("unknown_faces")
            mongo_store.collection("unknown_faces").insert_one(
                mongo_store.normalize_mongo_value(
                    {
                    "_id": unknown_id,
                    "camera_id": camera_id,
                    "unknown_face_id": unknown_face_id,
                    "snapshot_path": snapshot_path,
                    "face_bbox": face_bbox if isinstance(face_bbox, list) else list(face_bbox or []),
                    "embedding": self._serialize_embedding(embedding) if embedding is not None else None,
                    "first_seen": datetime.utcnow(),
                    "last_seen": datetime.utcnow(),
                    "detection_count": 1,
                    "profile_id": profile_id,
                    }
                )
            )
            return unknown_id
        except Exception as exc:
            logger.error(f"Failed to add unknown face: {exc}")
            return None

    def load_unknown_face_embeddings(self, camera_id):
        try:
            faces = self.get_unknown_faces(camera_id, hours=24)
            embeddings = {}
            for face in faces:
                if face.get("embedding") is None:
                    continue
                embeddings[face["unknown_face_id"]] = {
                    "embedding": np.array(face["embedding"], dtype=np.float32),
                    "last_seen": face.get("last_seen"),
                    "count": 0,
                }
            return embeddings
        except Exception as exc:
            logger.warning(f"Failed to load unknown face embeddings: {exc}")
            return {}

    def get_unknown_faces(self, camera_id, hours=24):
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            cursor = mongo_store.collection("unknown_faces").find(
                {"camera_id": camera_id, "last_seen": {"$gt": cutoff}}
            ).sort("last_seen", -1)
            return [
                {
                    "id": doc["_id"],
                    "snapshot_path": doc.get("snapshot_path"),
                    "face_bbox": doc.get("face_bbox", []),
                    "embedding": doc.get("embedding"),
                    "first_seen": doc.get("first_seen"),
                    "last_seen": doc.get("last_seen"),
                    "detection_count": doc.get("detection_count", 1),
                    "profile_id": doc.get("profile_id"),
                    "unknown_face_id": doc.get("unknown_face_id"),
                }
                for doc in cursor
            ]
        except Exception as exc:
            logger.error(f"Failed to get unknown faces: {exc}")
            return []

    def update_unknown_face_detection(self, unknown_face_id, profile_id=None):
        try:
            result = mongo_store.collection("unknown_faces").update_one(
                {"_id": unknown_face_id},
                {"$inc": {"detection_count": 1}, "$set": {"last_seen": datetime.utcnow(), "profile_id": profile_id}},
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update unknown face: {exc}")
            return False

    def delete_unknown_face(self, unknown_face_id):
        try:
            result = mongo_store.collection("unknown_faces").delete_one({"_id": unknown_face_id})
            return result.deleted_count > 0
        except Exception as exc:
            logger.error(f"Failed to delete unknown face: {exc}")
            return False

    def cleanup_unknown_faces(self, camera_id, retention_hours=24, keep_latest=20):
        deleted_snapshot_paths = []
        try:
            cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
            collection = mongo_store.collection("unknown_faces")
            expired = list(collection.find({"camera_id": camera_id, "last_seen": {"$lte": cutoff}}))
            if expired:
                deleted_snapshot_paths.extend([doc.get("snapshot_path") for doc in expired if doc.get("snapshot_path")])
                collection.delete_many({"_id": {"$in": [doc["_id"] for doc in expired]}})
            rows = list(collection.find({"camera_id": camera_id}).sort([("last_seen", -1), ("_id", -1)]))
            if len(rows) > keep_latest:
                overflow = rows[keep_latest:]
                deleted_snapshot_paths.extend([doc.get("snapshot_path") for doc in overflow if doc.get("snapshot_path")])
                collection.delete_many({"_id": {"$in": [doc["_id"] for doc in overflow]}})
            return [path for path in deleted_snapshot_paths if path]
        except Exception as exc:
            logger.error(f"Failed to cleanup unknown faces: {exc}")
            return []
