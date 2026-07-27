"""
One-time SQLite to Mongo seed for retained ChronoSense operational data.

Imports:
- users
- profiles
- cctv_cameras
- class_schedule

Skips historical log-heavy tables on purpose:
- attendance_log
- attendance_summary
- unknown_faces
- activity_log
- activity_summary
"""

import json
import os
import sqlite3
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

for candidate in (PROJECT_ROOT, BACKEND_DIR):
    if candidate and candidate not in sys.path:
        sys.path.insert(0, candidate)

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store


SQLITE_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles.db.before_log_trim.bak"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles.db.empty_bak"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "profiles.db"),
]


def parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def choose_sqlite_source():
    best_path = None
    best_profiles = -1
    for path in SQLITE_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM profiles")
            count = cur.fetchone()[0]
            conn.close()
            if count > best_profiles:
                best_profiles = count
                best_path = path
        except Exception:
            continue
    if not best_path:
        raise FileNotFoundError("No usable SQLite source with a profiles table was found.")
    return best_path


def fetch_rows(conn, query):
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query)
    return [dict(row) for row in cur.fetchall()]


def seed_users(conn):
    rows = fetch_rows(conn, "SELECT * FROM users ORDER BY id")
    collection = mongo_store.collection("users")
    imported = 0
    for row in rows:
        payload = {
            "_id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "email": row.get("email"),
            "role": row.get("role", "user"),
            "first_name": row.get("first_name"),
            "last_name": row.get("last_name"),
            "is_active": bool(row.get("is_active", 1)),
            "check_in_time": row.get("check_in_time") or "09:00",
            "check_out_time": row.get("check_out_time") or "17:00",
            "created_at": parse_timestamp(row.get("created_at")) or datetime.utcnow(),
            "updated_at": parse_timestamp(row.get("updated_at")) or datetime.utcnow(),
        }
        collection.replace_one({"_id": payload["_id"]}, payload, upsert=True)
        imported += 1
    return imported


def seed_profiles(conn):
    rows = fetch_rows(conn, "SELECT * FROM profiles ORDER BY id")
    collection = mongo_store.collection("profiles")
    imported = 0
    for row in rows:
        embedding = json.loads(row["embedding"]) if row.get("embedding") else []
        payload = {
            "_id": row["id"],
            "name": row["name"],
            "embedding": embedding,
            "profile_type": row.get("profile_type") or "faculty",
            "email": row.get("email"),
            "department": row.get("department"),
            "class_name": row.get("class_name"),
            "section_name": row.get("section_name"),
            "roll_number": row.get("roll_number"),
            "check_in_time": row.get("check_in_time") or "09:00",
            "check_out_time": row.get("check_out_time") or "17:00",
            "created_at": parse_timestamp(row.get("created_at")) or datetime.utcnow(),
            "image_path": row.get("image_path"),
        }
        collection.replace_one({"_id": payload["_id"]}, payload, upsert=True)
        imported += 1
    return imported


def seed_cameras(conn):
    rows = fetch_rows(conn, "SELECT * FROM cctv_cameras ORDER BY id")
    collection = mongo_store.collection("cctv_cameras")
    imported = 0
    for row in rows:
        payload = {
            "_id": row["id"],
            "name": row["name"],
            "source": row["source"],
            "camera_type": row.get("camera_type") or "rtsp",
            "type": row.get("camera_type") or "rtsp",
            "username": row.get("username"),
            "password": row.get("password"),
            "fps": row.get("fps") or 30,
            "resolution": [row.get("resolution_width") or 800, row.get("resolution_height") or 600],
            "enabled": bool(row.get("enabled", 1)),
            "created_at": parse_timestamp(row.get("created_at")) or datetime.utcnow(),
            "last_modified": parse_timestamp(row.get("last_modified")) or datetime.utcnow(),
            "wing": row.get("wing"),
            "room_number": row.get("room_number"),
        }
        collection.replace_one({"_id": payload["_id"]}, payload, upsert=True)
        imported += 1
    return imported


def seed_class_schedule(conn):
    try:
        rows = fetch_rows(conn, "SELECT * FROM class_schedule ORDER BY id")
    except sqlite3.OperationalError:
        return 0
    collection = mongo_store.collection("class_schedule")
    imported = 0
    for row in rows:
        payload = {
            "_id": row["id"],
            "date": row["date"],
            "class_name": row["class_name"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
        }
        collection.replace_one({"_id": payload["_id"]}, payload, upsert=True)
        imported += 1
    return imported


def update_counters(counts):
    counters = mongo_store.collection("counters")
    now = datetime.utcnow()
    for name, value in counts.items():
        counters.update_one(
            {"_id": name},
            {
                "$set": {"value": value, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )


def main():
    sqlite_path = choose_sqlite_source()
    mongo_store.ensure_connected()
    conn = sqlite3.connect(sqlite_path)
    try:
        users = seed_users(conn)
        profiles = seed_profiles(conn)
        cameras = seed_cameras(conn)
        schedules = seed_class_schedule(conn)
        update_counters(
            {
                "users": max(users, mongo_store.collection("users").count_documents({})),
                "profiles": max(profiles, mongo_store.collection("profiles").count_documents({})),
                "cctv_cameras": max(cameras, mongo_store.collection("cctv_cameras").count_documents({})),
                "class_schedule": max(schedules, mongo_store.collection("class_schedule").count_documents({})),
            }
        )
        print(
            json.dumps(
                {
                    "sqlite_source": sqlite_path,
                    "imported": {
                        "users": users,
                        "profiles": profiles,
                        "cctv_cameras": cameras,
                        "class_schedule": schedules,
                    },
                },
                indent=2,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
