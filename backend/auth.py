"""
Authentication manager for ChronoSense.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
try:
    from rbac import get_role_capabilities, get_role_label, get_user_scope
except ImportError:
    from backend.rbac import get_role_capabilities, get_role_label, get_user_scope

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store

logger = logging.getLogger(__name__)


class AuthManager:
    def __init__(self, db_path=None):
        self.db_path = db_path
        mongo_store.ensure_connected()
        self._seed_default_users()

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def _seed_default_users(self):
        users = mongo_store.collection("users")
        assignments = mongo_store.collection("class_assignments")
        now = datetime.utcnow()
        default_users = [
            ("admin", "admin123", "admin@chronosense.local", "admin", "System", "Administrator"),
            ("manager", "manager123", "manager@chronosense.local", "manager", "Campus", "Manager"),
            ("principal", "principal123", "principal@chronosense.local", "principal", "School", "Principal"),
            ("director", "director123", "director@chronosense.local", "director", "Demo", "Director"),
            ("teacher", "teacher123", "teacher@chronosense.local", "class_teacher", "Class", "Teacher"),
        ]
        user_ids = {}
        for username, password, email, role, first_name, last_name in default_users:
            existing = users.find_one({"username": username})
            if existing:
                users.update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "email": email,
                            "role": role,
                            "first_name": first_name,
                            "last_name": last_name,
                            "is_active": True,
                            "updated_at": now,
                        }
                    },
                )
                user_ids[username] = existing["_id"]
                continue
            user_id = mongo_store.next_id("users")
            users.insert_one(
                {
                    "_id": user_id,
                    "username": username,
                    "password_hash": self._hash_password(password),
                    "email": email,
                    "role": role,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                    "check_in_time": "09:00",
                    "check_out_time": "17:00",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            user_ids[username] = user_id

        teacher_id = user_ids.get("teacher")
        if teacher_id and not assignments.find_one({"user_id": teacher_id, "class_name": "K1", "section_name": "A"}):
            assignments.insert_one(
                {
                    "_id": mongo_store.next_id("class_assignments"),
                    "user_id": teacher_id,
                    "class_name": "K1",
                    "section_name": "A",
                    "camera_ids": [],
                    "camera_names": [],
                    "created_at": now,
                    "updated_at": now,
                }
            )

    def _build_user_payload(self, user, expires_at):
        payload = {
            "user_id": user["_id"],
            "username": user["username"],
            "role": user.get("role", "user"),
            "role_label": get_role_label(user.get("role", "user")),
            "capabilities": get_role_capabilities(user.get("role", "user")),
            "scope": get_user_scope({"user_id": user["_id"], "role": user.get("role", "user")}),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "expires_at": expires_at.isoformat(),
        }
        return payload

    def login(self, username, password):
        try:
            user = mongo_store.collection("users").find_one(
                {"username": username, "is_active": True}
            )
            if not user or user.get("password_hash") != self._hash_password(password):
                return None

            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=1)
            mongo_store.collection("sessions").insert_one(
                {
                    "_id": token,
                    "token": token,
                    "user_id": user["_id"],
                    "created_at": datetime.utcnow(),
                    "expires_at": expires_at,
                }
            )
            return {"token": token, **self._build_user_payload(user, expires_at)}
        except Exception as exc:
            logger.error(f"Login error: {exc}")
            return None

    def verify_token(self, token):
        try:
            session = mongo_store.collection("sessions").find_one(
                {"_id": token, "expires_at": {"$gt": datetime.utcnow()}}
            )
            if not session:
                return None

            user = mongo_store.collection("users").find_one(
                {"_id": session["user_id"], "is_active": True}
            )
            if not user:
                return None

            return self._build_user_payload(user, session["expires_at"])
        except Exception as exc:
            logger.error(f"Token verification error: {exc}")
            return None

    def logout(self, token):
        try:
            mongo_store.collection("sessions").delete_one({"_id": token})
            return True
        except Exception as exc:
            logger.error(f"Logout error: {exc}")
            return False
