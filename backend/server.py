from fastapi import FastAPI, UploadFile, File, Form, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
import cv2
import numpy as np
import uvicorn
import os
import logging
import json
import io
import threading
from datetime import datetime, timedelta
from urllib.parse import quote
import pandas as pd
from dotenv import load_dotenv
from ai_engine import ChronoEngine
from database import ProfileDatabase
from logging_setup import configure_logging
try:
    from database import DuplicateProfileError
except ImportError:
    from backend.database import DuplicateProfileError
from attendance import AttendanceTracker
from auth import AuthManager
from cctv_manager import CCTVManager
from cctv_recognition import CCTVRecognitionEngine
try:
    from rbac import (
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_ATTENDANCE_MANAGE,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_CAMERAS_MANAGE,
        CAPABILITY_CAMERAS_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_PEOPLE_MANAGE,
        CAPABILITY_PEOPLE_VIEW,
        CAPABILITY_RECOGNITION_MANAGE,
        CAPABILITY_RECOGNITION_VIEW,
        CAPABILITY_SYSTEM_ADMIN,
        ROLE_CLASS_TEACHER,
        has_capability,
        get_user_scope,
    )
except ImportError:
    from backend.rbac import (
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_ATTENDANCE_MANAGE,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_CAMERAS_MANAGE,
        CAPABILITY_CAMERAS_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_PEOPLE_MANAGE,
        CAPABILITY_PEOPLE_VIEW,
        CAPABILITY_RECOGNITION_MANAGE,
        CAPABILITY_RECOGNITION_VIEW,
        CAPABILITY_SYSTEM_ADMIN,
        ROLE_CLASS_TEACHER,
        has_capability,
        get_user_scope,
    )
try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store
try:
    from time_utils import APP_TIMEZONE, UTC, app_now
except ImportError:
    from backend.time_utils import APP_TIMEZONE, UTC, app_now
try:
    from recognition_runtime import (
        clear_camera_runtime,
        get_latest_detections as get_runtime_latest_detections,
        get_runtime_state,
        get_worker_state,
        list_runtime_states,
        set_desired_state,
    )
except ImportError:
    from backend.recognition_runtime import (
        clear_camera_runtime,
        get_latest_detections as get_runtime_latest_detections,
        get_runtime_state,
        get_worker_state,
        list_runtime_states,
        set_desired_state,
    )

load_dotenv()

def to_ist(utc_time_str):
    """Convert UTC timestamp to Asia/Kolkata format (HH:MM:SS)."""
    try:
        if not utc_time_str:
            return None
        if isinstance(utc_time_str, str):
            dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        else:
            dt = utc_time_str
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        ist_dt = dt.astimezone(APP_TIMEZONE)
        return ist_dt.strftime('%H:%M:%S')
    except Exception:
        return utc_time_str


def to_ist_time_only(time_str):
    """Convert a HH:MM[:SS] UTC time-of-day string to Asia/Kolkata HH:MM:SS."""
    try:
        if not time_str:
            return None
        value = str(time_str).strip()
        parsed = datetime.strptime(value, "%H:%M:%S" if len(value) == 8 else "%H:%M")
        utc_dt = parsed.replace(tzinfo=UTC)
        ist_dt = utc_dt.astimezone(APP_TIMEZONE)
        return ist_dt.strftime("%H:%M:%S")
    except Exception:
        return time_str

def resolve_attendance_report_range(
    report_type: str = "daily",
    date: str = None,
    week_start: str = None,
    month: str = None,
    start_date: str = None,
    end_date: str = None
):
    """Resolve a report type plus filters into an inclusive YYYY-MM-DD range."""
    today = app_now().strftime("%Y-%m-%d")

    if report_type == "daily":
        resolved_date = date or today
        return resolved_date, resolved_date

    if report_type == "weekly":
        resolved_start = week_start or today
        start_dt = datetime.strptime(resolved_start, "%Y-%m-%d")
        resolved_end = (start_dt + timedelta(days=6)).strftime("%Y-%m-%d")
        return resolved_start, resolved_end

    if report_type == "monthly":
        month_value = month or today[:7]
        month_start = datetime.strptime(f"{month_value}-01", "%Y-%m-%d")
        if month_start.month == 12:
            next_month = datetime(month_start.year + 1, 1, 1)
        else:
            next_month = datetime(month_start.year, month_start.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        return month_start.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")

    if report_type == "custom":
        if not start_date or not end_date:
            raise ValueError("Custom reports require both start_date and end_date.")
        return start_date, end_date

    raise ValueError("Invalid report_type. Use daily, weekly, monthly, or custom.")

# Setup logging
configure_logging()
logger = logging.getLogger(__name__)

SERVICE_NAME = (os.getenv("CHRONOSENSE_SERVICE_NAME") or "backend").strip() or "backend"
app = FastAPI(title=f"ChronoSense {SERVICE_NAME.title()} API")

# Feature flags for demo/runtime control.
ENABLE_EMOTION_DETECTION = os.getenv("CHRONOSENSE_EMOTION_ENABLED_DEFAULT", "true").lower() == "true"
ENABLE_ACTIVITY_DETECTION = os.getenv("CHRONOSENSE_ACTIVITY_ENABLED_DEFAULT", "false").lower() == "true"
ENABLE_UNKNOWN_FACE_TRACKING = False
DEFAULT_RECOGNITION_THRESHOLD = float(os.getenv("CHRONOSENSE_RECOGNITION_THRESHOLD", "0.28"))

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Initialize with live CCTV-calibrated recognition settings
engine = ChronoEngine(
    recognition_threshold=DEFAULT_RECOGNITION_THRESHOLD,
    matching_metric='hybrid',
    enable_emotion_detection=False
)
profile_db = ProfileDatabase()
attendance_tracker = AttendanceTracker(profile_db.db_path)
auth_manager = AuthManager(profile_db.db_path)
cctv_manager = CCTVManager(profile_db.db_path)
cctv_recognition_engine = CCTVRecognitionEngine(
    db_path=profile_db.db_path,
    ai_engine=engine,
    attendance_tracker=attendance_tracker,
    profile_db=profile_db,
    enable_emotion_detection=ENABLE_EMOTION_DETECTION,
    enable_activity_detection=ENABLE_ACTIVITY_DETECTION,
    enable_unknown_face_tracking=ENABLE_UNKNOWN_FACE_TRACKING
)

# Load all profiles from database into engine memory on startup
def load_profiles_on_startup():
    """Load all registered profiles from database into engine on server startup"""
    try:
        all_profiles = profile_db.get_all_profiles()
        
        if not all_profiles:
            logger.error("❌ No profiles found in database - face recognition will not work!")
            return False
        
        for profile in all_profiles:
            profile_id = profile['id']
            embedding = profile['embedding']
            view_embeddings = profile.get("view_embeddings") or {}
            if embedding is None:
                logger.info(f"Skipping incomplete profile '{profile['name']}' during recognition load.")
                continue
            engine.profiles[profile_id] = {
                'name': profile['name'],
                'embedding': embedding,
                'view_embeddings': view_embeddings,
                'created_at': profile['created_at']
            }
            # Debug: log embedding details
            if isinstance(embedding, np.ndarray):
                logger.info(f"✓ Loaded '{profile['name']}': shape={embedding.shape}, dtype={embedding.dtype}, sum={embedding.sum():.4f}")
            else:
                logger.warning(f"⚠ '{profile['name']}': embedding is {type(embedding)}, not ndarray!")
        
        logger.warning(f"" + "=" * 70)
        logger.warning(f"✓✓✓ CRITICAL: {len(all_profiles)} PROFILES LOADED AND READY FOR RECOGNITION ✓✓✓")
        logger.warning(f"=" * 70)
        
        # Log profile names for verification
        profile_names = [p['name'] for p in all_profiles]
        logger.info(f"Loaded profiles: {', '.join(profile_names)}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to load profiles on startup: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# Load profiles on startup
if not load_profiles_on_startup():
    logger.error("❌ FATAL: Profiles not loaded - recognition will fail!")

# ============ LOCAL WEBCAM BACKGROUND RECOGNITION ============
import threading

_webcam_thread = None
_webcam_running = False
_webcam_lock = threading.Lock()
_webcam_latest_frame = None  # Shared frame for /video_feed
_webcam_latest_annotated = None  # Annotated frame for streaming
_webcam_last_detections = None  # Cache last detections for annotating non-processed frames
_webcam_last_detections_time = 0  # Timestamp of last detection update


def _get_webcam_target_fps():
    configured = os.getenv("CHRONOSENSE_WEBCAM_TARGET_FPS", "8")
    try:
        return max(1.0, float(configured))
    except ValueError:
        return 8.0


def using_mongo_runtime():
    mongo_store.ensure_connected()
    return True


def get_registered_profile_count():
    using_mongo_runtime()
    return mongo_store.collection("profiles").count_documents({})


def get_profile_completion_counts():
    using_mongo_runtime()
    return profile_db.get_profile_completion_counts()


def get_unknown_individual_count():
    using_mongo_runtime()
    unknown_ids = mongo_store.collection("activity_log").distinct(
        "unknown_face_id",
        {"unknown_face_id": {"$ne": None}}
    )
    return len([value for value in unknown_ids if value is not None])


def get_recent_unknown_counts_by_camera():
    using_mongo_runtime()
    cutoff = app_now() - timedelta(hours=24)
    rows = mongo_store.collection("unknown_faces").aggregate([
        {"$match": {"last_seen": {"$gte": cutoff}}},
        {"$group": {"_id": "$camera_id", "count": {"$sum": 1}}}
    ])
    return {row["_id"]: row["count"] for row in rows}


def get_recent_detection_activity(limit=5):
    using_mongo_runtime()
    grouped = {}
    for doc in mongo_store.collection("attendance_log").find(
        {},
        {"location": 1, "timestamp": 1}
    ):
        location = doc.get("location")
        timestamp = doc.get("timestamp")
        if not location or not timestamp:
            continue
        existing = grouped.get(location)
        if existing is None or timestamp > existing:
            grouped[location] = timestamp
    return sorted(
        [
            {"location": location, "last_detection": timestamp.isoformat()}
            for location, timestamp in grouped.items()
        ],
        key=lambda item: item["last_detection"],
        reverse=True,
    )[:limit]


def _split_csv_values(raw_value):
    if not raw_value:
        return []
    return [item.strip() for item in str(raw_value).split(",") if item.strip()]


def _build_overview_profile_scope(role_scope="all", class_names=None, section_names=None):
    query = {}
    normalized_role_scope = (role_scope or "all").strip().lower()
    if normalized_role_scope == "student":
        query["profile_type"] = "student"
    elif normalized_role_scope == "faculty":
        query["profile_type"] = {"$ne": "student"}

    normalized_classes = _split_csv_values(class_names)
    normalized_sections = _split_csv_values(section_names)
    if normalized_classes:
        query["class_name"] = {"$in": normalized_classes}
    if normalized_sections:
        query["section_name"] = {"$in": normalized_sections}
    return query, normalized_classes, normalized_sections, normalized_role_scope


def _safe_percent(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _parse_hhmmss_to_hour_bucket(value):
    if not value:
        return None
    try:
        parts = str(value).split(":")
        hour = int(parts[0])
        return f"{hour:02d}:00"
    except Exception:
        return None


def _resolve_group_key(profile, compare_mode):
    compare_mode = (compare_mode or "classes").strip().lower()
    if compare_mode == "sections":
        class_name = profile.get("class_name") or "Unassigned"
        section_name = profile.get("section_name") or "Unassigned"
        return f"{class_name} - {section_name}"
    if profile.get("profile_type") == "student":
        return profile.get("class_name") or "Unassigned"
    return profile.get("department") or "Faculty"


def _group_trend_rows(rows, group_by):
    normalized_group_by = (group_by or "day").strip().lower()
    if normalized_group_by == "day":
        return rows

    grouped = {}
    for row in rows:
        try:
            date_obj = datetime.strptime(row["date"], "%Y-%m-%d")
        except Exception:
            continue
        if normalized_group_by == "week":
            year, week_num, _ = date_obj.isocalendar()
            label = f"{year}-W{week_num:02d}"
        elif normalized_group_by == "month":
            label = date_obj.strftime("%Y-%m")
        else:
            label = row["date"]
        bucket = grouped.setdefault(label, {
            "date": label,
            "present": 0,
            "absent": 0,
            "late": 0,
            "total": 0,
        })
        bucket["present"] += row.get("present", 0)
        bucket["absent"] += row.get("absent", 0)
        bucket["late"] += row.get("late", 0)
        bucket["total"] = max(bucket["total"], row.get("total", 0))

    grouped_rows = []
    for label in sorted(grouped.keys()):
        row = grouped[label]
        row["attendance_rate"] = _safe_percent(row["present"], row["total"])
        grouped_rows.append(row)
    return grouped_rows


def _build_overview_analytics(
    selected_date,
    start_date,
    end_date,
    role_scope="all",
    class_names=None,
    section_names=None,
    group_by="day",
    compare_mode="classes",
):
    using_mongo_runtime()
    profile_query, normalized_classes, normalized_sections, normalized_role_scope = _build_overview_profile_scope(
        role_scope=role_scope,
        class_names=class_names,
        section_names=section_names,
    )

    profiles = list(mongo_store.collection("profiles").find(profile_query).sort("name", 1))
    profile_ids = [profile["_id"] for profile in profiles]
    profile_ids_set = set(profile_ids)
    profile_map = {profile["_id"]: profile for profile in profiles}

    selected_day_report = attendance_tracker.get_daily_report(selected_date) or {"records": []}
    scoped_today_records = [
        row for row in (selected_day_report.get("records") or [])
        if row.get("profile_id") in profile_ids_set
    ]
    today_present = sum(1 for row in scoped_today_records if row.get("status") in {"present", "late"})
    today_late = sum(1 for row in scoped_today_records if row.get("status") == "late")
    total_profiles = len(profiles)
    today_absent = max(total_profiles - today_present, 0)

    completion_counts = profile_db.get_profile_completion_counts()
    scoped_completed = 0
    scoped_incomplete = 0
    for profile in profiles:
        if profile.get("profile_complete") and profile.get("recognition_trained"):
            scoped_completed += 1
        else:
            scoped_incomplete += 1

    cameras = cctv_manager.get_all_cameras()
    recognition_statuses = _get_all_runtime_recognition_status()
    recognition_map = {
        str(item.get("camera_id") or item.get("id")): item
        for item in recognition_statuses
    }
    camera_details = []
    connected_count = 0
    disconnected_count = 0
    running_count = 0
    for camera in cameras:
        live_status = probe_camera_connection(camera)
        connection = live_status.get("connection_status", "disconnected")
        recognition = recognition_map.get(str(camera["id"]), {})
        is_running = bool(recognition.get("is_running"))
        if connection == "connected":
            connected_count += 1
        else:
            disconnected_count += 1
        if is_running:
            running_count += 1
        camera_details.append({
            "id": camera["id"],
            "name": camera.get("name"),
            "location": camera.get("name"),
            "connection": connection,
            "recognition_running": is_running,
            "last_check": live_status.get("last_check"),
            "error": live_status.get("error"),
        })

    range_rows = list(
        mongo_store.collection("attendance_summary").find(
            {
                "date": {"$gte": start_date, "$lte": end_date},
                "profile_id": {"$in": profile_ids},
            }
        ).sort([("date", 1), ("name", 1)])
    ) if profile_ids else []

    trend_by_date = {}
    for day in attendance_tracker.get_attendance_summary_range(start_date, end_date).get("records", []):
        profile_id = day.get("profile_id")
        if profile_id not in profile_ids_set:
            continue
        date_key = day.get("date")
        trend_by_date.setdefault(date_key, {"date": date_key, "present": 0, "late": 0, "total": total_profiles})
        if day.get("status") in {"present", "late"}:
            trend_by_date[date_key]["present"] += 1
        if day.get("status") == "late":
            trend_by_date[date_key]["late"] += 1
    attendance_trend = []
    for date_key in sorted(trend_by_date.keys()):
        present = trend_by_date[date_key]["present"]
        late = trend_by_date[date_key]["late"]
        absent = max(total_profiles - present, 0)
        attendance_trend.append({
            "date": date_key,
            "present": present,
            "absent": absent,
            "late": late,
            "total": total_profiles,
            "attendance_rate": _safe_percent(present, total_profiles),
        })
    attendance_trend = _group_trend_rows(attendance_trend, group_by)

    comparison_rows = {}
    for profile in profiles:
        key = _resolve_group_key(profile, compare_mode)
        comparison_rows.setdefault(key, {
            "group": key,
            "present": 0,
            "absent": 0,
            "late": 0,
            "total": 0,
            "incomplete_profiles": 0,
        })
        comparison_rows[key]["total"] += 1
        if not (profile.get("profile_complete") and profile.get("recognition_trained")):
            comparison_rows[key]["incomplete_profiles"] += 1
    for row in scoped_today_records:
        profile = profile_map.get(row.get("profile_id")) or {}
        key = _resolve_group_key(profile, compare_mode)
        if row.get("status") in {"present", "late"}:
            comparison_rows[key]["present"] += 1
        if row.get("status") == "late":
            comparison_rows[key]["late"] += 1
    class_rollup = []
    for row in comparison_rows.values():
        row["absent"] = max(row["total"] - row["present"], 0)
        row["attendance_rate"] = _safe_percent(row["present"], row["total"])
        class_rollup.append(row)
    class_rollup.sort(key=lambda row: (-row["total"], row["group"]))
    class_comparison = class_rollup[:8] if len(class_rollup) > 8 and not normalized_classes else class_rollup

    status_distribution = [
        {"name": "Present", "value": today_present},
        {"name": "Absent", "value": today_absent},
        {"name": "Late", "value": today_late},
        {"name": "Incomplete Profiles", "value": scoped_incomplete},
    ]

    bucket_counts = {}
    for row in range_rows:
        bucket = _parse_hhmmss_to_hour_bucket(row.get("check_in_time"))
        if not bucket:
            continue
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    check_in_distribution = [
        {"bucket": bucket, "count": bucket_counts[bucket]}
        for bucket in sorted(bucket_counts.keys())
    ]

    recent_attendance_records = []
    for row in sorted(scoped_today_records, key=lambda item: item.get("name") or "")[:12]:
        profile = profile_map.get(row.get("profile_id")) or {}
        recent_attendance_records.append({
            "profile_id": row.get("profile_id"),
            "name": row.get("name"),
            "status": row.get("status"),
            "check_in_time": row.get("check_in_time"),
            "check_out_time": row.get("check_out_time"),
            "last_location": row.get("last_location") or row.get("location"),
            "class_name": profile.get("class_name"),
            "section_name": profile.get("section_name"),
            "profile_type": profile.get("profile_type", "faculty"),
        })

    student_profiles = profile_db.get_all_profiles(profile_type="student")
    sections_by_class = {}
    for profile in student_profiles:
        class_name = profile.get("class_name")
        section_name = profile.get("section_name")
        if not class_name or not section_name:
            continue
        sections_by_class.setdefault(class_name, [])
        if section_name not in sections_by_class[class_name]:
            sections_by_class[class_name].append(section_name)
    for key in sections_by_class:
        sections_by_class[key].sort()

    return {
        "summary": {
            "profiles_completed": scoped_completed,
            "profiles_incomplete": scoped_incomplete,
            "profiles_completed_global": completion_counts.get("completed", 0),
            "profiles_incomplete_global": completion_counts.get("incomplete", 0),
            "cameras_added": len(cameras),
            "cameras_working": connected_count,
            "present_today": today_present,
            "absent_today": today_absent,
            "attendance_rate_today": _safe_percent(today_present, total_profiles),
        },
        "filter_options": {
            "classes": sorted({profile.get("class_name") for profile in student_profiles if profile.get("class_name")}),
            "sections_by_class": sections_by_class,
            "camera_names": sorted([camera.get("name") for camera in cameras if camera.get("name")]),
        },
        "charts": {
            "attendance_trend": attendance_trend,
            "class_comparison": class_comparison,
            "status_distribution": status_distribution,
            "check_in_distribution": check_in_distribution,
            "camera_health": {
                "summary": {
                    "total": len(cameras),
                    "connected": connected_count,
                    "disconnected": disconnected_count,
                    "recognition_running": running_count,
                },
                "records": camera_details,
            },
        },
        "tables": {
            "class_rollup": class_rollup,
            "recent_attendance_records": recent_attendance_records,
        },
        "scope": {
            "date": selected_date,
            "start_date": start_date,
            "end_date": end_date,
            "role_scope": normalized_role_scope,
            "class_names": normalized_classes,
            "section_names": normalized_sections,
            "group_by": (group_by or "day").strip().lower(),
            "compare_mode": (compare_mode or "classes").strip().lower(),
        },
    }


def get_enabled_camera_names():
    return [
        camera["name"]
        for camera in cctv_manager.get_all_cameras()
        if camera.get("enabled") and camera.get("processing_enabled", True)
    ]


def get_camera_record(camera_id, enabled_only=False):
    for camera in cctv_manager.get_all_cameras():
        if camera["id"] != camera_id:
            continue
        if enabled_only and not camera.get("enabled"):
            return None
        return camera
    return None


def get_camera_stream_row(camera_id, enabled_only=False):
    camera = get_camera_record(camera_id, enabled_only=enabled_only)
    if not camera:
        return None
    return (
        camera["id"],
        camera["name"],
        camera["source"],
        camera.get("type"),
        camera.get("username"),
        camera.get("password"),
    )


def build_camera_source_url(source, camera_type=None, username=None, password=None):
    source = (source or "").strip()
    normalized_type = (camera_type or "").strip().lower()

    if normalized_type == "local_webcam":
        return source or "0"

    if not source or not username or password is None:
        return source

    if normalized_type not in ["rtsp", "mjpeg", "http"]:
        return source

    if "://" not in source:
        return source

    protocol, rest = source.split("://", 1)
    host_and_path = rest.rsplit("@", 1)[-1]
    encoded_username = quote(str(username), safe="")
    encoded_password = quote(str(password), safe="")
    return f"{protocol}://{encoded_username}:{encoded_password}@{host_and_path}"


def apply_local_webcam_defaults(name=None, source=None, wing=None, room_number=None):
    return (
        (name or "").strip() or "My Computer Camera",
        (source or "").strip() or "0",
        (wing or "").strip() or "Local",
        (room_number or "").strip() or "USB Camera",
    )


def parse_local_webcam_device_index(source):
    normalized_source = str(source or "").strip() or "0"
    try:
        return max(0, int(normalized_source))
    except (TypeError, ValueError):
        raise ValueError("Local camera source must be a numeric device index like 0, 1, or 2.")


def get_local_webcam_device_index():
    cameras = cctv_manager.get_all_cameras()
    for camera in cameras:
        if (camera.get("type") or "").upper() == "LOCAL_WEBCAM" and camera.get("enabled", True):
            try:
                return parse_local_webcam_device_index(camera.get("source"))
            except ValueError as exc:
                logger.warning(f"Invalid local webcam source for camera {camera.get('id')}: {exc}")
                break
    return 0


def _build_browser_frame_emotion_summary(detections):
    emotion_counts = {}
    derived_counts = {}
    educational_counts = {}
    reliable_people = 0

    for detection in detections or []:
        emotion_available = bool(detection.get("emotion_available"))
        emotion_confidence = float(detection.get("emotion_confidence") or 0.0)
        raw_confidence = float(detection.get("raw_confidence") or 0.0)
        smoothed_confidence = float(detection.get("smoothed_confidence") or 0.0)

        if not emotion_available and emotion_confidence <= 0.0 and raw_confidence <= 0.0 and smoothed_confidence <= 0.0:
            continue

        reliable_people += 1
        emotion_label = detection.get("smoothed_emotion") or detection.get("emotion")
        if emotion_label and emotion_label != "LowSignal":
            emotion_counts[emotion_label] = emotion_counts.get(emotion_label, 0) + 1

        derived_label = detection.get("derived_emotion")
        if derived_label and derived_label != "Passive":
            derived_counts[derived_label] = derived_counts.get(derived_label, 0) + 1

        educational_label = detection.get("educational_state")
        if educational_label and educational_label != "Waiting":
            educational_counts[educational_label] = educational_counts.get(educational_label, 0) + 1

    def dominant_label(values):
        return max(values, key=values.get) if values else None

    def percentages(values):
        total = sum(values.values())
        if not total:
            return {}
        return {
            key: round((count / total) * 100, 1)
            for key, count in values.items()
        }

    return {
        "recognized_people_count": reliable_people,
        "dominant_emotion": dominant_label(emotion_counts),
        "dominant_derived_emotion": dominant_label(derived_counts),
        "dominant_educational_state": dominant_label(educational_counts),
        "emotion_percentages": percentages(emotion_counts),
        "derived_emotion_percentages": percentages(derived_counts),
        "educational_state_percentages": percentages(educational_counts),
    }


def _serialize_emotion_scores(detection):
    return (
        detection.get("all_emotions")
        or detection.get("smoothed_scores")
        or detection.get("raw_scores")
        or {}
    )


def _to_json_safe(value):
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _serialize_browser_detection(detection):
    serialized = {}
    for key, value in (detection or {}).items():
        if key == "face_obj":
            continue
        serialized[key] = _to_json_safe(value)
    serialized["emotion_scores"] = _to_json_safe(_serialize_emotion_scores(detection))
    return serialized


def _build_browser_unknown_detection(face_data, face_crop, browser_camera_id, index):
    emotion_data = cctv_recognition_engine._infer_emotion_signal(
        face_crop=face_crop,
        face_bbox=face_data.get("bbox"),
        landmarks=face_data.get("landmark"),
        camera_key=browser_camera_id,
        track_key=f"{browser_camera_id}:fallback:{index}",
        enable_emotion=True,
        activity=None,
        activity_confidence=0.0,
        face_obj=face_data.get("face_obj"),
    )

    return {
        "profile_id": None,
        "name": f"Unknown person {index + 1}",
        "confidence": 0.0,
        "bbox": list(face_data.get("bbox") or []),
        **(emotion_data or {}),
    }


def _normalize_browser_face_candidates(prepared_image):
    for variant_name, variant_image in _browser_detection_variants(prepared_image):
        landmark_faces = cctv_recognition_engine.ai_engine.detect_faces_with_landmarks(variant_image) or []
        if landmark_faces:
            return landmark_faces, f"landmarks:{variant_name}"

    for variant_name, variant_image in _browser_detection_variants(prepared_image):
        bbox_faces = cctv_recognition_engine.ai_engine.detect_faces(variant_image) or []
        if bbox_faces:
            return [
                {
                    "bbox": bbox,
                    "landmark": None,
                    "face_obj": None,
                }
                for bbox in bbox_faces
            ], f"bbox_fallback:{variant_name}"

    for variant_name, variant_image in _browser_detection_variants(prepared_image):
        opencv_faces = _detect_browser_faces_with_opencv(variant_image)
        if opencv_faces:
            return [
                {
                    "bbox": bbox,
                    "landmark": None,
                    "face_obj": None,
                }
                for bbox in opencv_faces
            ], f"opencv_fallback:{variant_name}"

    return [], "none"


def _ensure_browser_emotion_pipeline():
    if getattr(cctv_recognition_engine, "emotion_pipeline", None) is not None:
        return

    try:
        from cctv_recognition import EmotionPipeline  # local import to avoid startup hard-fail
    except ImportError:
        from backend.cctv_recognition import EmotionPipeline

    try:
        cctv_recognition_engine.emotion_pipeline = EmotionPipeline()
        cctv_recognition_engine.enable_emotion_detection = True
        logger.info(
            "Browser camera endpoint initialized emotion pipeline lazily "
            f"({cctv_recognition_engine.emotion_pipeline.describe_backend()})"
        )
    except Exception as exc:
        logger.error(f"Failed to initialize browser emotion pipeline lazily: {exc}")


def _prepare_browser_analysis_frame(image):
    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side >= 1280:
        return image

    scale = 1280.0 / float(longest_side)
    return cv2.resize(
        image,
        (max(1, int(width * scale)), max(1, int(height * scale))),
        interpolation=cv2.INTER_CUBIC,
    )


def _browser_detection_variants(image):
    variants = [("prepared", image)]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    variants.append(("equalized", cv2.cvtColor(equalized, cv2.COLOR_GRAY2BGR)))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    variants.append(("clahe", cv2.cvtColor(contrast, cv2.COLOR_GRAY2BGR)))

    sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    variants.append(("sharpened", cv2.filter2D(image, -1, sharpen_kernel)))

    return variants


def _detect_browser_faces_with_opencv(image):
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        logger.debug("OpenCV cascade fallback unavailable in this cv2 build; skipping browser cascade detection")
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    cascade_names = [
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt2.xml",
        "haarcascade_profileface.xml",
    ]
    faces = []

    for cascade_name in cascade_names:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
        if cascade.empty():
            continue

        found = cascade.detectMultiScale(
            gray,
            scaleFactor=1.03,
            minNeighbors=3,
            minSize=(28, 28),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        for (x, y, w, h) in found:
            if w <= 0 or h <= 0:
                continue
            faces.append((int(x), int(y), int(w), int(h)))

    if not faces:
        return []

    # Deduplicate overlapping cascade hits by center proximity.
    unique = []
    for face in sorted(faces, key=lambda item: item[2] * item[3], reverse=True):
        x, y, w, h = face
        cx = x + w / 2
        cy = y + h / 2
        duplicate = False
        for ux, uy, uw, uh in unique:
            ucx = ux + uw / 2
            ucy = uy + uh / 2
            if abs(cx - ucx) < max(w, uw) * 0.35 and abs(cy - ucy) < max(h, uh) * 0.35:
                duplicate = True
                break
        if not duplicate:
            unique.append(face)

    return unique


def _center_browser_face_candidate(image):
    height, width = image.shape[:2]
    box_width = int(width * 0.34)
    box_height = int(height * 0.42)
    x = int((width - box_width) / 2)
    y = int(height * 0.18)
    return {
        "bbox": (max(0, x), max(0, y), min(box_width, width), min(box_height, height)),
        "landmark": None,
        "face_obj": None,
    }


def get_current_user_from_authorization(authorization: str):
    token = authorization.split(" ")[-1] if authorization else None
    return auth_manager.verify_token(token) if token else None


def require_authorized_user(authorization: str):
    user = get_current_user_from_authorization(authorization)
    if not user:
        return None, JSONResponse({"error": "Unauthorized"}, status_code=401)
    return user, None


def require_capability_user(authorization: str, capability: str):
    user, error = require_authorized_user(authorization)
    if error:
        return None, error
    if capability and not has_capability(user.get("role"), capability):
        return None, JSONResponse({"error": "Forbidden"}, status_code=403)
    return user, None


def get_user_scope_filters(user):
    scope = get_user_scope(user or {})
    class_names = scope.get("class_names") or []
    section_names = scope.get("section_names") or []
    camera_ids = scope.get("camera_ids") or []
    camera_names = scope.get("camera_names") or []
    return scope, class_names, section_names, camera_ids, camera_names


def ensure_requested_scope_allowed(requested_values, allowed_values, field_name):
    if not requested_values or not allowed_values:
        return requested_values
    normalized_requested = {str(value).strip() for value in requested_values if str(value).strip()}
    normalized_allowed = {str(value).strip() for value in allowed_values if str(value).strip()}
    if normalized_requested and not normalized_requested.issubset(normalized_allowed):
        raise PermissionError(f"Requested {field_name} is outside assigned scope.")
    return [value for value in requested_values if str(value).strip() in normalized_allowed]


def get_scoped_profiles_for_user(user, profile_type=None, class_name=None, section_name=None):
    scope, allowed_classes, allowed_sections, _camera_ids, _camera_names = get_user_scope_filters(user)
    normalized_profile_type = profile_type.strip().lower() if profile_type else None
    requested_class = class_name.strip() if class_name else None
    requested_section = section_name.strip() if section_name else None

    if scope.get("restricted"):
        if requested_class and requested_class not in allowed_classes:
            raise PermissionError("Requested class is outside assigned scope.")
        if requested_section and requested_section not in allowed_sections:
            raise PermissionError("Requested section is outside assigned scope.")
        requested_class = requested_class or (allowed_classes[0] if len(allowed_classes) == 1 else None)
        requested_section = requested_section or (allowed_sections[0] if len(allowed_sections) == 1 else None)

    profiles = profile_db.get_all_profiles(
        profile_type=normalized_profile_type,
        class_name=requested_class,
        section_name=requested_section,
    )
    if scope.get("restricted"):
        profiles = [
            profile for profile in profiles
            if profile.get("class_name") in allowed_classes
            and profile.get("section_name") in allowed_sections
        ]
    return profiles


def filter_records_by_profiles(records, profile_ids):
    allowed_ids = set(profile_ids or [])
    return [row for row in (records or []) if row.get("profile_id") in allowed_ids]


def probe_camera_connection(camera):
    """Actively test whether a configured camera can open and return a frame."""
    if not camera or not camera.get("enabled", True):
        return {
            "connection_status": "disabled",
            "error": "Camera is disabled",
            "last_check": app_now().isoformat(),
        }

    url = build_camera_source_url(
        source=camera.get("source"),
        camera_type=camera.get("type"),
        username=camera.get("username"),
        password=camera.get("password"),
    )
    connection_status = "disconnected"
    error_message = None
    cap = None

    try:
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            error_message = "Could not open stream"
        else:
            ret, frame = cap.read()
            if ret and frame is not None:
                connection_status = "connected"
            else:
                error_message = "Could not read frame"
    except Exception as exc:
        error_message = str(exc)
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

    cctv_manager.update_camera_status(camera["id"], connection_status, error_message)
    return {
        "connection_status": connection_status,
        "error": error_message,
        "last_check": app_now().isoformat(),
    }


def _build_attendance_report_payload(resolved_start, resolved_end):
    report_result = attendance_tracker.get_attendance_summary_range(resolved_start, resolved_end) or {}
    summaries = report_result.get("records") or []

    profile_ids = {row.get("profile_id") for row in summaries if row.get("profile_id") is not None}
    profile_map = {}
    if profile_ids:
        profile_map = {
            profile["_id"]: profile
            for profile in mongo_store.collection("profiles").find({"_id": {"$in": list(profile_ids)}})
        }

    daily_rollup = {}
    person_records = []
    for row in summaries:
        date_key = row.get("date")
        if not date_key:
            continue

        status = row.get("status") or "absent"
        daily_rollup.setdefault(date_key, {
            "date": date_key,
            "present": 0,
            "absent": 0,
            "late": 0,
            "total_profiles": 0,
            "attendance_rate": 0.0,
        })
        daily_rollup[date_key]["total_profiles"] += 1
        if status in {"present", "late"}:
            daily_rollup[date_key]["present"] += 1
        else:
            daily_rollup[date_key]["absent"] += 1
        if status == "late":
            daily_rollup[date_key]["late"] += 1

        profile = profile_map.get(row.get("profile_id")) or {}
        person_records.append({
            "profile_id": row.get("profile_id"),
            "name": row.get("name"),
            "date": date_key,
            "profile_type": profile.get("profile_type", "faculty"),
            "class_name": profile.get("class_name"),
            "section_name": profile.get("section_name"),
            "roll_number": profile.get("roll_number"),
            "status": status,
            "check_in_time": row.get("check_in_time"),
            "check_out_time": row.get("check_out_time"),
            "check_in": row.get("check_in_time"),
            "check_out": row.get("check_out_time"),
            "detections": row.get("continuous_detections", 0),
            "continuous_detections": row.get("continuous_detections", 0),
            "last_location": row.get("location"),
            "location": row.get("location"),
            "duration_minutes": row.get("duration_minutes", 0),
            "is_late": bool(row.get("is_late", False)),
        })

    records = []
    for date_key in sorted(daily_rollup.keys()):
        row = daily_rollup[date_key]
        row["attendance_rate"] = _safe_percent(row["present"], row["total_profiles"])
        records.append(row)

    summary = {
        "total_days": len(records),
        "total_present": sum(row["present"] for row in records),
        "total_absent": sum(row["absent"] for row in records),
        "average_attendance_rate": round(
            sum(row["attendance_rate"] for row in records) / len(records),
            2
        ) if records else 0.0,
    }

    return {
        "start_date": report_result.get("start_date", resolved_start),
        "end_date": report_result.get("end_date", resolved_end),
        "record_count": report_result.get("record_count", len(summaries)),
        "present_count": report_result.get("present_count", summary["total_present"]),
        "late_count": report_result.get("late_count", sum(row.get("late", 0) for row in records)),
        "records": records,
        "person_records": person_records,
        "summary": summary,
    }


def iter_activity_docs(location=None, start_time=None, end_time=None, exclude_unknown=True):
    using_mongo_runtime()
    query = {}
    if location is not None:
        query["location"] = location
    if start_time is not None or end_time is not None:
        query["timestamp"] = {}
        if start_time is not None:
            query["timestamp"]["$gte"] = start_time
        if end_time is not None:
            query["timestamp"]["$lt"] = end_time
    if exclude_unknown:
        query["activity"] = {"$ne": "Unknown"}
    return list(mongo_store.collection("activity_log").find(query))


def iter_class_activity_docs(location=None, start_time=None, end_time=None, class_name=None, section_name=None):
    using_mongo_runtime()
    query = {}
    if location is not None:
        query["location"] = location
    if class_name is not None:
        query["class_name"] = class_name
    if section_name is not None:
        query["section_name"] = section_name
    if start_time is not None or end_time is not None:
        query["timestamp"] = {}
        if start_time is not None:
            query["timestamp"]["$gte"] = start_time
        if end_time is not None:
            query["timestamp"]["$lt"] = end_time
    return list(mongo_store.collection("class_activity_log").find(query))


def iter_emotion_docs(collection_name, date=None, location=None, last_24_hours=False):
    if using_mongo_runtime():
        query = {
            "emotion": {"$nin": [None, ""]},
            "location": {"$nin": [None, ""]},
        }
        if location is not None:
            query["location"] = location
        if date:
            start, end = attendance_tracker._day_bounds(date)
            query["timestamp"] = {"$gte": start, "$lt": end}
        elif last_24_hours:
            query["timestamp"] = {"$gte": app_now() - timedelta(days=1)}
        return list(mongo_store.collection(collection_name).find(query, {"location": 1, "emotion": 1, "timestamp": 1}))


REQUIRED_FACE_VIEWS = {
    "straight": "Look straight",
    "left": "Turn slightly left",
    "right": "Turn slightly right",
    "top": "Tilt face up",
    "down": "Tilt face down",
}


def score_registration_bbox(bbox, frame_shape):
    frame_h, frame_w = frame_shape[:2]
    x, y, w, h = bbox
    cx = x + (w / 2.0)
    cy = y + (h / 2.0)
    center_x_penalty = abs(cx - (frame_w / 2.0)) / max(frame_w, 1)
    lower_half_penalty = max(0.0, (cy - (frame_h * 0.48)) / max(frame_h, 1))
    area = w * h
    return (center_x_penalty + lower_half_penalty, -area)


def get_registration_face_candidates(frame):
    faces = engine.detect_faces_with_landmarks(frame)
    if not faces:
        return []
    return sorted(faces, key=lambda face: score_registration_bbox(face["bbox"], frame.shape))


def refined_bbox_candidates(bbox, frame_shape):
    frame_h, frame_w = frame_shape[:2]
    x, y, w, h = bbox
    variants = []

    def clamp(candidate):
        cx, cy, cw, ch = candidate
        cx = max(0, min(int(cx), frame_w - 1))
        cy = max(0, min(int(cy), frame_h - 1))
        cw = max(1, min(int(cw), frame_w - cx))
        ch = max(1, min(int(ch), frame_h - cy))
        return (cx, cy, cw, ch)

    variants.append((x, y, w, h))
    variants.append((x + 0.08 * w, y + 0.05 * h, 0.84 * w, 0.84 * h))
    variants.append((x + 0.12 * w, y + 0.10 * h, 0.76 * w, 0.76 * h))
    variants.append((x + 0.18 * w, y + 0.12 * h, 0.64 * w, 0.64 * h))

    seen = set()
    ordered = []
    for variant in variants:
        candidate = clamp(variant)
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def build_registration_image_variants(img):
    variants = [("original", img, 1.0)]
    ih, iw = img.shape[:2]
    upscale = min(4.0, max(1600 / max(iw, 1), 1600 / max(ih, 1)))

    if upscale > 1.2:
        upscaled_img = cv2.resize(img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
        variants.append(("upscaled", upscaled_img, upscale))

        gray = cv2.cvtColor(upscaled_img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_img = cv2.cvtColor(clahe.apply(gray), cv2.COLOR_GRAY2BGR)
        variants.append(("contrast", contrast_img, upscale))

        sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharpened = cv2.filter2D(upscaled_img, -1, sharpen_kernel)
        variants.append(("sharpened", sharpened, upscale))

    return variants


def extract_registration_embedding_from_variant(img, registration_scale):
    registration_faces = get_registration_face_candidates(img)
    embedding = None
    registration_bbox = None

    if registration_faces:
        for candidate in registration_faces:
            candidate_bbox = candidate["bbox"]
            candidate_face_obj = candidate.get("face_obj")

            try:
                if candidate_face_obj is not None and getattr(candidate_face_obj, "embedding", None) is not None:
                    embedding = candidate_face_obj.embedding.astype(np.float32)
                else:
                    embedding = None
            except Exception:
                embedding = None

            if embedding is None:
                for refined_bbox in refined_bbox_candidates(candidate_bbox, img.shape):
                    embedding = engine.recognizer.get_embedding(img, refined_bbox)
                    if embedding is not None:
                        candidate_bbox = refined_bbox
                        break

            if embedding is not None:
                registration_bbox = candidate_bbox
                break

    if embedding is None:
        detections = engine.detect_faces(img)
        if detections:
            detection_candidates = sorted(detections, key=lambda det: score_registration_bbox(det, img.shape))
            for candidate_bbox in detection_candidates:
                for refined_bbox in refined_bbox_candidates(candidate_bbox, img.shape):
                    embedding = engine.recognizer.get_embedding(img, refined_bbox)
                    if embedding is not None:
                        registration_bbox = refined_bbox
                        break
                if embedding is not None:
                    break

    if embedding is None or registration_bbox is None:
        return None, None

    if registration_scale > 1.0:
        x, y, w, h = registration_bbox
        registration_bbox = (
            int(x / registration_scale),
            int(y / registration_scale),
            int(w / registration_scale),
            int(h / registration_scale),
        )

    return embedding, registration_bbox


def extract_registration_embedding_from_frame(img):
    for _, variant_img, registration_scale in build_registration_image_variants(img):
        embedding, registration_bbox = extract_registration_embedding_from_variant(variant_img, registration_scale)
        if embedding is not None and registration_bbox is not None:
            return embedding, registration_bbox

    return None, None


async def extract_multi_view_embeddings(upload_map):
    view_embeddings = {}
    view_errors = {}

    for view_name, upload in upload_map.items():
        if upload is None:
            view_errors[view_name] = f"{view_name} view is required."
            continue

        contents = await upload.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            view_errors[view_name] = f"{view_name} view is not a valid image."
            continue

        embedding, _ = extract_registration_embedding_from_frame(img)
        if embedding is None:
            view_errors[view_name] = (
                f"Could not extract a usable face embedding for the {view_name} view. "
                f"Please recapture with instruction: {REQUIRED_FACE_VIEWS.get(view_name, view_name)}."
            )
            continue

        view_embeddings[view_name] = {
            "embedding": embedding.astype(np.float32),
            "captured_at": app_now(),
            "image_path": None,
        }

    return view_embeddings, view_errors


async def read_optional_upload_map(upload_map):
    normalized = {}
    for view_name, upload in upload_map.items():
        if upload is None or not getattr(upload, "filename", None):
            continue
        contents = await upload.read()
        if not contents:
            continue
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"{view_name} view is not a valid image.")
        normalized[view_name] = img
    return normalized


def extract_multi_view_embeddings_from_images(image_map):
    view_embeddings = {}
    view_errors = {}
    for view_name, img in image_map.items():
        embedding, _ = extract_registration_embedding_from_frame(img)
        if embedding is None:
            view_errors[view_name] = (
                f"Could not extract a usable face embedding for the {view_name} view. "
                f"Please recapture with instruction: {REQUIRED_FACE_VIEWS.get(view_name, view_name)}."
            )
            continue
        view_embeddings[view_name] = {
            "embedding": embedding.astype(np.float32),
            "captured_at": app_now(),
            "image_path": None,
        }
    return view_embeddings, view_errors


def normalize_profile_status_payload(profile):
    is_complete = bool(profile.get("profile_complete"))
    is_trained = bool(profile.get("recognition_trained"))
    return {
        "profile_complete": is_complete,
        "recognition_trained": is_trained,
        "profile_status": profile.get("profile_status") or ("completed" if is_complete and is_trained else "incomplete"),
    }


def parse_bulk_profiles_dataframe(file_name, raw_bytes):
    lower_name = (file_name or "").lower()
    if lower_name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw_bytes))
    return pd.read_excel(io.BytesIO(raw_bytes))


    rows = []
    if collection_name == "attendance_log":
        if date:
            docs = attendance_tracker.get_daily_report(date) or {"records": []}
            # fallback lower-level data unavailable per-emotion; return empty if not on mongo
            return []
    return rows

def _start_local_webcam_thread():
    """Start background local webcam recognition if not already running."""
    global _webcam_thread

    # Attendance mode should never enable activity analysis.
    cctv_recognition_engine.enable_activity_detection = False
    cctv_recognition_engine.activity_detector = None

    if _webcam_running:
        return {
            "success": True,
            "status": "already_running",
            "message": "Local webcam recognition is already running."
        }

    _webcam_thread = threading.Thread(target=_run_local_webcam_recognition, daemon=True)
    _webcam_thread.start()

    return {
        "success": True,
        "status": "started",
        "message": "Local webcam recognition started."
    }

def _stop_local_webcam_thread():
    """Stop background local webcam recognition if running."""
    global _webcam_running, _webcam_thread

    if not _webcam_running:
        return {
            "success": True,
            "status": "already_stopped",
            "message": "Local webcam recognition is already stopped."
        }

    _webcam_running = False

    if _webcam_thread and _webcam_thread.is_alive():
        _webcam_thread.join(timeout=1.5)

    return {
        "success": True,
        "status": "stopped",
        "message": "Local webcam recognition stopped."
    }

def _build_attendance_marking_status():
    """Build combined attendance-marking status for enabled sources."""
    enabled_cameras = [
        camera
        for camera in cctv_manager.get_all_cameras()
        if camera.get("enabled", True) and camera.get("processing_enabled", True)
    ]
    sources = []
    running_count = 0

    for camera in enabled_cameras:
        camera_type = (camera.get("type") or "").upper()

        if camera_type == "LOCAL_WEBCAM":
          is_running = bool(_webcam_running)
          status = "running" if is_running else "stopped"
        else:
          recognition_status = get_runtime_state(camera["id"])
          is_running = bool(recognition_status.get("is_running"))
          status = recognition_status.get("status", "unknown")

        if is_running:
            running_count += 1

        sources.append({
            "id": camera["id"],
            "name": camera["name"],
            "type": camera.get("type"),
            "running": is_running,
            "status": status
        })

    return {
        "overall_running": running_count > 0,
        "enabled_count": len(enabled_cameras),
        "running_count": running_count,
        "sources": sources
    }


def _request_recognition_state(camera_id, desired_running, mode="attendance", requested_by="api"):
    worker_state = _get_live_recognition_worker_state()
    if worker_state is None:
        logger.warning(
            "No live recognition worker heartbeat found for camera %s; using in-server fallback for mode=%s",
            camera_id,
            mode,
        )
        cctv_recognition_engine.enable_emotion_detection = mode == "emotion"
        cctv_recognition_engine.enable_activity_detection = mode == "activity"
        if desired_running:
            return cctv_recognition_engine.start_recognition(camera_id)
        return cctv_recognition_engine.stop_recognition(camera_id)

    set_desired_state(
        camera_id,
        desired_running=desired_running,
        mode=mode,
        requested_by=requested_by,
    )
    desired_status = "start" if desired_running else "stop"
    return {
        "success": True,
        "status": "queued",
        "message": f"Recognition {desired_status} requested for camera {camera_id}",
    }


def _get_live_recognition_worker_state():
    stale_after_seconds = max(
        5.0,
        float(os.getenv("CHRONOSENSE_RECOGNITION_WORKER_STALE_AFTER_SECONDS", "10")),
    )
    candidate_worker_ids = (
        "primary",
        "recognition-worker",
        "attendance-worker",
        "emotion-worker",
        "activity-worker",
    )
    now = app_now()

    for worker_id in candidate_worker_ids:
        try:
            worker_state = get_worker_state(worker_id)
        except Exception:
            continue
        heartbeat_at = worker_state.get("heartbeat_at")
        if not heartbeat_at:
            continue
        if isinstance(heartbeat_at, str):
            try:
                heartbeat_at = datetime.fromisoformat(heartbeat_at.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
        if not isinstance(heartbeat_at, datetime):
            continue
        if (now - heartbeat_at).total_seconds() <= stale_after_seconds:
            return worker_state

    return None


def _get_all_runtime_recognition_status():
    runtime_map = {doc.get("_id"): doc for doc in list_runtime_states()}
    status_list = []
    for camera in cctv_manager.get_all_cameras():
        if not camera.get("enabled", True):
            continue
        camera_id = camera["id"]
        if (camera.get("type") or "").upper() == "LOCAL_WEBCAM":
            doc = {
                "is_running": bool(_webcam_running),
                "status": "running" if _webcam_running else "stopped",
                "message": "",
            }
        else:
            doc = dict(runtime_map.get(camera_id) or {})
        status_list.append({
            "camera_id": camera_id,
            "camera_name": camera["name"],
            "is_running": bool(doc.get("is_running", False)),
            "status": doc.get("status", "stopped"),
            "frames_processed": doc.get("frames_processed", 0),
            "faces_recognized": doc.get("faces_recognized", 0),
            "message": doc.get("message", ""),
            "fps": doc.get("fps", 0),
            "worker_id": doc.get("worker_id"),
            "updated_at": doc.get("updated_at"),
            "reconnect_attempts": doc.get("reconnect_attempts", 0),
        })
    return status_list

def _run_local_webcam_recognition():
    """Continuously process local webcam frames for attendance in background."""
    global _webcam_running, _webcam_latest_frame, _webcam_latest_annotated, _webcam_last_detections
    import time

    device_index = get_local_webcam_device_index()
    backends = [
        (0, "Default"),
        (cv2.CAP_AVFOUNDATION, "AVFoundation"),
        (cv2.CAP_FFMPEG, "FFMPEG"),
    ]

    cap = None
    for backend_id, backend_name in backends:
        try:
            cap = cv2.VideoCapture(device_index, backend_id)
            if cap.isOpened() and cap.grab():
                logger.info(
                    "✓ Local webcam opened with %s backend on device index %s",
                    backend_name,
                    device_index,
                )
                break
            cap.release()
            cap = None
        except:
            pass

    if cap is None or not cap.isOpened():
        logger.warning("⚠ Local webcam not available on device index %s", device_index)
        _webcam_running = False
        return

    _webcam_running = True
    logger.warning("🎥 Local webcam recognition STARTED (device index %s)", device_index)
    frame_num = 0
    webcam_target_fps = _get_webcam_target_fps()
    webcam_min_interval = 1.0 / webcam_target_fps
    
    webcam_snapshots_dir = os.path.join(os.path.dirname(__file__), 'face_snapshots', 'camera_local_webcam')
    os.makedirs(webcam_snapshots_dir, exist_ok=True)
    
    try:
        while _webcam_running:
            loop_started_at = time.perf_counter()
            success, frame = cap.read()
            if not success:
                time.sleep(0.05)
                continue
            
            frame_num += 1
            work_frame = cv2.resize(frame, (800, 600))
            
            # Process every 3rd frame
            if frame_num % 3 == 0:
                try:
                    detections = cctv_recognition_engine.process_frame(
                        work_frame,
                        camera_id="local_webcam"
                    )
                    result = {'detections': detections, 'frame_count': frame_num}
                    with _webcam_lock:
                        _webcam_last_detections = detections
                    
                    if detections:
                        cctv_recognition_engine.enqueue_recognition_persistence(
                            detections,
                            "Local Webcam",
                            camera_id="local_webcam",
                        )
                except:
                    pass
            
            # Annotate frame with cached detections
            with _webcam_lock:
                dets = _webcam_last_detections if _webcam_last_detections else []
            
            if dets:
                annotated = _annotate_frame(work_frame, {'detections': dets, 'frame_count': frame_num})
            else:
                annotated = work_frame.copy()
            
            # Update shared frames
            with _webcam_lock:
                _webcam_latest_frame = work_frame.copy()
                _webcam_latest_annotated = annotated.copy()
            
            elapsed = time.perf_counter() - loop_started_at
            remaining = webcam_min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
    except Exception as e:
        logger.error(f"Webcam error: {e}")
    finally:
        _webcam_running = False
        if cap:
            cap.release()
        logger.warning("🎥 Local webcam recognition STOPPED")

# Auto-start recognition on enabled cameras
# DISABLED: Camera threads were causing server to hang on startup
# @app.on_event("startup")
# async def auto_start_recognition():
#     """Auto-start face recognition on all enabled cameras after server startup"""
#     def _auto_start():
#         try:
#             import time
#             time.sleep(1)  # Give server time to fully initialize (reduced from 2s)
#             
#             logger.info("\n" + "="*70)
#             logger.info("🎬 AUTO-STARTING RECOGNITION ON ENABLED CAMERAS")
#             logger.info("="*70)
#             
#             cameras = cctv_manager.get_all_cameras()
#             enabled_cameras = [c for c in cameras if c.get('enabled', True)]
#             
#             for camera in enabled_cameras:
#                 try:
#                     # Start camera recognition without waiting for connection  
#                     # (handles offline cameras gracefully)
#                     result = cctv_recognition_engine.start_recognition(camera['id'])
#                     status = "✓" if result['success'] else "✗"
#                     logger.warning(f"{status} Camera {camera['id']} ({camera['name']}): {result['message']}")
#                 except Exception as e:
#                     logger.warning(f"✗ Failed to start recognition on camera {camera['id']}: {e}")
#             
#             logger.info("="*70 + "\n")
#             
#             # Also start local webcam background recognition
#             global _webcam_thread
#             _webcam_thread = threading.Thread(target=_run_local_webcam_recognition, daemon=True)
#             _webcam_thread.start()
#             
#         except Exception as e:
#             logger.error(f"Error in auto-start recognition: {e}")
#     
#     # Run in background thread to not block startup
#     import threading
#     thread = threading.Thread(target=_auto_start, daemon=True)
#     thread.start()

# Get the base directory for file paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(base_dir, "frontend")
react_frontend_dir = os.path.join(frontend_dir, "react")
react_dist_dir = os.path.join(react_frontend_dir, "dist")
react_assets_dir = os.path.join(react_dist_dir, "assets")


def serve_react_app():
    """Serve the React SPA build when present, otherwise show setup guidance."""
    react_index = os.path.join(react_dist_dir, "index.html")
    fallback_page = os.path.join(react_frontend_dir, "build-required.html")

    if os.path.exists(react_index):
        return FileResponse(react_index, media_type="text/html")

    if os.path.exists(fallback_page):
        return FileResponse(fallback_page, media_type="text/html")

    return JSONResponse({"error": "React app not available"}, status_code=404)

@app.get("/")
async def root():
    return serve_react_app()

@app.get("/index.html")
async def index_page():
    return RedirectResponse(url="/", status_code=307)

@app.get("/register.html")
async def register_page():
    return RedirectResponse(url="/register", status_code=307)

@app.get("/login.html")
async def login_page():
    return RedirectResponse(url="/login", status_code=307)

@app.get("/admin-dashboard.html")
async def admin_dashboard_page():
    return RedirectResponse(url="/admin", status_code=307)

@app.get("/director-dashboard.html")
async def director_dashboard_page():
    return RedirectResponse(url="/director", status_code=307)

@app.get("/camera-face-validation.html")
async def camera_face_validation_page():
    return RedirectResponse(url="/validation", status_code=307)


@app.get("/app")
async def react_app_page():
    return RedirectResponse(url="/", status_code=307)


@app.get("/app/")
async def react_app_page_slash():
    return RedirectResponse(url="/", status_code=307)


@app.get("/app/{full_path:path}")
async def react_app_nested(full_path: str):
    normalized_path = full_path.lstrip("/")

    if not normalized_path:
        return RedirectResponse(url="/", status_code=307)

    return RedirectResponse(url=f"/{normalized_path}", status_code=307)

@app.post("/api/auth/login")
async def login(credentials: dict = Body(...)):
    """Authenticate user and return token
    
    Request body:
    {
        "username": "admin",
        "password": "admin123"
    }
    """
    try:
        username = credentials.get('username')
        password = credentials.get('password')
        
        if not username or not password:
            return JSONResponse(
                {"detail": "Username and password are required"},
                status_code=400
            )
        
        result = auth_manager.login(username, password)
        
        if result:
            return JSONResponse(result, status_code=200)
        else:
            return JSONResponse(
                {"detail": "Invalid username or password"},
                status_code=401
            )
    except Exception as e:
        logger.error(f"Login endpoint error: {e}")
        return JSONResponse(
            {"detail": "Login failed"},
            status_code=500
        )

@app.get("/api/auth/verify")
async def verify_token(authorization: str = Header(None)):
    """Verify authentication token"""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing or invalid authorization header"},
                status_code=401
            )
        
        token = authorization[7:]  # Remove "Bearer " prefix
        result = auth_manager.verify_token(token)
        
        if result:
            return JSONResponse(result, status_code=200)
        else:
            return JSONResponse(
                {"detail": "Invalid or expired token"},
                status_code=401
            )
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return JSONResponse(
            {"detail": "Token verification failed"},
            status_code=500
        )

@app.post("/api/auth/logout")
async def logout(authorization: str = Header(None)):
    """Logout and invalidate token"""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing or invalid authorization header"},
                status_code=401
            )
        
        token = authorization[7:]  # Remove "Bearer " prefix
        auth_manager.logout(token)
        
        return JSONResponse(
            {"status": "success", "message": "Logged out successfully"},
            status_code=200
        )
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return JSONResponse(
            {"detail": "Logout failed"},
            status_code=500
        )

@app.get("/api/attendance")
async def get_attendance():
    """Get current attendance from live detections"""
    # Return current tracked faces
    return engine.get_profiles_summary()

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "frames_processed": engine.detect_count}

@app.get("/api/system/camera-status")
async def get_camera_status(authorization: str = Header(None)):
    """Get camera system status and diagnostics"""
    if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        camera_count = len(get_enabled_camera_names())
        recent_activity = get_recent_detection_activity(limit=5)
        
        # Check if local webcam is running
        webcam_ok = _webcam_running if _webcam_running else False
        
        return JSONResponse({
            'status': 'operational',
            'timestamp': app_now().isoformat(),
            'camera_available': True,
            'backend': 'OpenCV',
            'cameras_enabled': camera_count,
            'webcam_status': 'running' if webcam_ok else 'stopped',
            'recent_detections': recent_activity
        })
    except Exception as e:
        logger.error(f"Camera status error: {e}")
        return JSONResponse({
            'status': 'error',
            'message': str(e),
            'camera_available': False
        }, status_code=500)

@app.get("/api/system/unique-individuals")
async def get_unique_individuals(authorization: str = Header(None)):
    """Get count of unique individuals detected in the system"""
    if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        registered_count = get_registered_profile_count()
        unknown_count = get_unknown_individual_count()
        
        total_unique = registered_count + unknown_count
        
        return JSONResponse({
            'registered': registered_count,
            'unknown': unknown_count,
            'total': total_unique
        })
    except Exception as e:
        logger.error(f"Unique individuals count error: {e}")
        return JSONResponse({
            'error': str(e),
            'total': 0
        }, status_code=500)


@app.get("/api/operations/snapshot")
async def get_operations_snapshot(
    date: str = None,
    authorization: str = Header(None)
):
    """Return an aggregated operations snapshot for overview/live pages."""
    user, error = require_capability_user(authorization, CAPABILITY_OVERVIEW_VIEW)
    if error:
        return error

    try:
        selected_date = date or app_now().strftime("%Y-%m-%d")
        scope = user.get("scope") or get_user_scope(user)
        role_scope = "student" if user.get("role") == ROLE_CLASS_TEACHER else "faculty"
        scoped_class = scope.get("class_names", [None])[0] if user.get("role") == ROLE_CLASS_TEACHER else None
        scoped_section = scope.get("section_names", [None])[0] if user.get("role") == ROLE_CLASS_TEACHER else None
        attendance_data = attendance_tracker.get_attendance_dashboard_analytics(
            dashboard_date=selected_date,
            start_date=selected_date,
            end_date=selected_date,
            role_scope=role_scope,
            class_name=scoped_class,
            section_name=scoped_section,
        ) or {}
        attendance_data["marking_status"] = _build_attendance_marking_status()

        cameras = cctv_manager.get_all_cameras()
        enabled_cameras = [
            camera for camera in cameras
            if camera.get("enabled") and camera.get("processing_enabled", True)
        ]
        recognition_statuses = _get_all_runtime_recognition_status()
        recognition_map = {
            str(item.get("camera_id") or item.get("id")): item
            for item in recognition_statuses
        }
        registered_count = get_registered_profile_count()
        completion_counts = get_profile_completion_counts()
        unknown_count = get_unknown_individual_count()
        unknown_counts_by_camera = get_recent_unknown_counts_by_camera()

        classroom_emotions_response = await get_classroom_emotions(date=selected_date, authorization=authorization)
        classroom_emotions = classroom_emotions_response.get("locations", {}) if isinstance(classroom_emotions_response, dict) else {}

        activity_response = await get_activities_by_location(date=selected_date, authorization=authorization)
        if isinstance(activity_response, JSONResponse):
          activity_payload = json.loads(activity_response.body.decode("utf-8"))
        else:
          activity_payload = activity_response
        activity_locations = activity_payload.get("locations", {}) if isinstance(activity_payload, dict) else {}

        recognition_logs = cctv_recognition_engine.get_recognition_logs(limit=12) if has_capability(user.get("role"), CAPABILITY_RECOGNITION_VIEW) else []

        camera_details = []
        for camera in enabled_cameras:
            recognition = recognition_map.get(str(camera["id"]), {})
            camera_details.append({
                **camera,
                "connection": cctv_manager.get_camera_latest_status(camera["id"]),
                "recognition_running": bool(recognition.get("is_running")),
                "recognition": recognition,
                "unknown_face_count": unknown_counts_by_camera.get(camera["id"], 0),
                "emotion": classroom_emotions.get(camera["name"]),
                "activity": activity_locations.get(camera["name"])
            })

        return {
            "status": "success",
            "data": {
                "date": selected_date,
                "attendance": attendance_data,
                "unique_individuals": {
                    "registered": registered_count,
                    "unknown": unknown_count,
                    "total": registered_count + unknown_count
                },
                "profile_completion": completion_counts,
                "cameras": camera_details,
                "classroom_emotions": classroom_emotions,
                "activity_locations": activity_locations,
                "recent_logs": recognition_logs
            }
        }
    except Exception as e:
        logger.error(f"Operations snapshot error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/overview/analytics")
async def get_overview_analytics(
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    role_scope: str = "all",
    class_names: str = None,
    section_names: str = None,
    group_by: str = "day",
    compare_mode: str = "classes",
    authorization: str = Header(None),
):
    user, error = require_capability_user(authorization, CAPABILITY_OVERVIEW_VIEW)
    if error:
        return error

    try:
        scope = user.get("scope") or get_user_scope(user)
        selected_date = date or end_date or start_date or app_now().strftime("%Y-%m-%d")
        resolved_start = start_date or selected_date
        resolved_end = end_date or selected_date
        if scope.get("restricted"):
          allowed_classes = scope.get("class_names") or []
          allowed_sections = scope.get("section_names") or []
          requested_classes = _split_csv_values(class_names)
          requested_sections = _split_csv_values(section_names)
          ensure_requested_scope_allowed(requested_classes, allowed_classes, "class")
          ensure_requested_scope_allowed(requested_sections, allowed_sections, "section")
          class_names = ",".join(requested_classes or allowed_classes)
          section_names = ",".join(requested_sections or allowed_sections)
          role_scope = "student"
        analytics = _build_overview_analytics(
            selected_date=selected_date,
            start_date=resolved_start,
            end_date=resolved_end,
            role_scope=role_scope,
            class_names=class_names,
            section_names=section_names,
            group_by=group_by,
            compare_mode=compare_mode,
        )
        return {
            "status": "success",
            "data": analytics,
        }
    except Exception as exc:
        logger.error(f"Overview analytics error: {exc}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)

@app.post("/api/register")
async def register_face(name: str = Form(...), image_straight: UploadFile = File(None),
                       image_left: UploadFile = File(None), image_right: UploadFile = File(None),
                       image_top: UploadFile = File(None), image_down: UploadFile = File(None),
                       profile_type: str = Form("faculty"), email: str = Form(None),
                       department: str = Form(None), class_name: str = Form(None),
                       section_name: str = Form(None), roll_number: str = Form(None),
                       check_in_time: str = Form(None), check_out_time: str = Form(None),
                       authorization: str = Header(None)):
    """Register a new face profile using InsightFace embeddings
    
    Args:
        name: Person's name (required)
        image: Image file containing face for training (required)
        email: Email address (optional)
        department: Department name (optional)
        check_in_time: Expected check-in time in HH:MM format (IST) - default: 09:00
        check_out_time: Expected check-out time in HH:MM format (IST) - default: 17:00
    
    Returns:
        Profile creation status with 512-D embedding
    """
    try:
        user, error = require_capability_user(authorization, CAPABILITY_PEOPLE_MANAGE)
        if error:
            return error
        profile_type = (profile_type or "faculty").strip().lower()
        if profile_type not in {"faculty", "student"}:
            return JSONResponse({"error": "Invalid profile type"}, status_code=400)

        if profile_type == "student":
            if not (class_name or "").strip():
                return JSONResponse({"error": "Class is required for student profiles"}, status_code=400)
            if not (section_name or "").strip():
                return JSONResponse({"error": "Section is required for student profiles"}, status_code=400)
            if not (roll_number or "").strip():
                return JSONResponse({"error": "Roll number is required for student profiles"}, status_code=400)

        # Validate and set default times
        check_in = check_in_time or "09:00"
        check_out = check_out_time or "17:00"
        
        upload_map = {
            "straight": image_straight,
            "left": image_left,
            "right": image_right,
            "top": image_top,
            "down": image_down,
        }
        optional_images = await read_optional_upload_map(upload_map)
        view_embeddings = {}
        embedding = None
        if optional_images:
            view_embeddings, view_errors = extract_multi_view_embeddings_from_images(optional_images)
            if view_errors:
                return JSONResponse(
                    {
                        "error": "Some uploaded face views could not be processed.",
                        "view_errors": view_errors,
                    },
                    status_code=400,
                )
            if len(view_embeddings) != len(REQUIRED_FACE_VIEWS):
                return JSONResponse(
                    {
                        "error": "All five face views are required to complete face registration.",
                        "view_errors": {
                            view_name: f"{view_name} view is required."
                            for view_name in REQUIRED_FACE_VIEWS
                            if view_name not in view_embeddings
                        },
                    },
                    status_code=400,
                )
            embedding = view_embeddings["straight"]["embedding"]
        
        # Create unique profile ID with metadata
        normalized_name = profile_db.normalize_profile_name(name)

        try:
            profile_id = profile_db.add_profile(normalized_name, embedding, 
                                                profile_type=profile_type,
                                                email=email, 
                                                department=department,
                                                class_name=(class_name or "").strip() or None,
                                                section_name=(section_name or "").strip() or None,
                                                roll_number=(roll_number or "").strip() or None,
                                                check_in_time=check_in,
                                                check_out_time=check_out,
                                                view_embeddings=view_embeddings,
                                                profile_complete=bool(view_embeddings),
                                                recognition_trained=bool(view_embeddings),
                                                profile_status="completed" if view_embeddings else "incomplete")
        except DuplicateProfileError:
            return JSONResponse({
                "error": f"Profile '{normalized_name}' already exists"
            }, status_code=400)
        
        profile_id = int(profile_id)

        if view_embeddings:
            success = engine.register_face_views_from_arrays(profile_id, name, view_embeddings, embedding)
            if not success:
                profile_db.delete_profile(profile_id)
                return JSONResponse({
                    "error": "Failed to register extracted embedding."
                }, status_code=400)
            
            if profile_id in engine.profiles:
                real_embedding = engine.profiles[profile_id]['embedding']
                if real_embedding is not None:
                    try:
                        profile_db.update_profile_view_embeddings(profile_id, real_embedding, engine.profiles[profile_id].get("view_embeddings", {}))
                        logger.info(f"✓ Updated database with real embedding for {name}")
                    except Exception as e:
                        logger.error(f"Failed to update embedding in database: {e}")
        
        logger.info(f"✓ Registered {name} (profile_id={profile_id}, embedding=512-D ArcFace)")
        
        return {
            "status": "success",
            "profile_id": profile_id,
            "name": name,
            "profile_type": profile_type,
            "email": email,
            "department": department,
            "class_name": class_name,
            "section_name": section_name,
            "roll_number": roll_number,
            "check_in_time": check_in,
            "check_out_time": check_out,
            "profile_complete": bool(view_embeddings),
            "recognition_trained": bool(view_embeddings),
            "profile_status": "completed" if view_embeddings else "incomplete",
            "enrollment_views": list(view_embeddings.keys()),
            "message": (
                f"Profile '{name}' registered and completed."
                if view_embeddings
                else f"Profile '{name}' saved as incomplete. Upload all face images later to complete recognition training."
            )
        }
    
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/profiles")
async def list_profiles(profile_type: str = None, class_name: str = None, section_name: str = None, authorization: str = Header(None)):
    """Get all registered profiles with their metadata"""
    try:
        user, error = require_capability_user(authorization, CAPABILITY_PEOPLE_VIEW)
        if error:
            return error
        profiles = get_scoped_profiles_for_user(
            user,
            profile_type=profile_type,
            class_name=class_name,
            section_name=section_name,
        )
        filters = profile_db.get_profile_filters()
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            filters["classes"] = [value for value in filters.get("classes", []) if value in (scope.get("class_names") or [])]
            filters["sections_by_class"] = {
                class_key: [section for section in sections if section in (scope.get("section_names") or [])]
                for class_key, sections in (filters.get("sections_by_class") or {}).items()
                if class_key in (scope.get("class_names") or [])
            }
        return {
            "count": len(profiles),
            "filters": filters,
            "profiles": [
                {
                    "id": p['id'], 
                    "name": p['name'], 
                    "profile_type": p.get('profile_type', 'faculty'),
                    "email": p.get('email'),
                    "department": p.get('department'),
                    "class_name": p.get('class_name'),
                    "section_name": p.get('section_name'),
                    "roll_number": p.get('roll_number'),
                    "check_in_time": p.get('check_in_time', '09:00'),
                    "check_out_time": p.get('check_out_time', '17:00'),
                    "created_at": p['created_at'],
                    **normalize_profile_status_payload(p),
                }
                for p in profiles
            ]
        }
    except Exception as e:
        logger.error(f"List profiles error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: int, authorization: str = Header(None)):
    """Delete a registered profile"""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_PEOPLE_MANAGE)
        if error:
            return error
        success = profile_db.delete_profile(profile_id)
        if success:
            # Reload all profiles into engine as a dictionary (not list!)
            all_profiles = profile_db.get_all_profiles()
            engine.profiles = {}
            for profile in all_profiles:
                if profile.get("embedding") is None:
                    continue
                engine.profiles[profile['id']] = {
                    'name': profile['name'],
                    'embedding': profile['embedding'],
                    'created_at': profile['created_at']
                }
            logger.info(f"Reloaded {len(engine.profiles)} profiles after deletion")
            return {"status": "success", "message": f"Profile {profile_id} deleted"}
        else:
            return JSONResponse({"error": "Profile not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Delete profile error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.put("/api/profiles/{profile_id}")
async def edit_profile(profile_id: int, name: str = Form(None), email: str = Form(None),
                      department: str = Form(None), profile_type: str = Form(None),
                      class_name: str = Form(None), section_name: str = Form(None),
                      roll_number: str = Form(None), check_in_time: str = Form(None),
                      check_out_time: str = Form(None), image_straight: UploadFile = File(None),
                      image_left: UploadFile = File(None), image_right: UploadFile = File(None),
                      image_top: UploadFile = File(None), image_down: UploadFile = File(None),
                      authorization: str = Header(None)):
    """Edit a registered profile (update name, email, department, or schedule times)
    
    Args:
        profile_id: ID of the profile to edit
        name: New name for the profile (optional)
        email: New email for the profile (optional)
        department: New department for the profile (optional)
        check_in_time: New check-in time (HH:MM format, optional)
        check_out_time: New check-out time (HH:MM format, optional)
    """
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_PEOPLE_MANAGE)
        if error:
            return error
        # Check if profile exists
        profile = profile_db.get_profile(profile_id)
        
        if not profile:
            return JSONResponse({"error": "Profile not found"}, status_code=404)
        
        normalized_profile_type = profile_type.strip().lower() if profile_type else None
        if normalized_profile_type and normalized_profile_type not in {"faculty", "student"}:
            return JSONResponse({"error": "Invalid profile type"}, status_code=400)

        if normalized_profile_type == "student":
            if class_name is not None and not class_name.strip():
                return JSONResponse({"error": "Class is required for student profiles"}, status_code=400)
            if section_name is not None and not section_name.strip():
                return JSONResponse({"error": "Section is required for student profiles"}, status_code=400)
            if roll_number is not None and not roll_number.strip():
                return JSONResponse({"error": "Roll number is required for student profiles"}, status_code=400)

        # Update profile using the database method
        success = profile_db.update_profile(
            profile_id,
            name=name,
            email=email,
            department=department,
            profile_type=normalized_profile_type,
            class_name=class_name,
            section_name=section_name,
            roll_number=roll_number,
            check_in_time=check_in_time,
            check_out_time=check_out_time
        )

        upload_map = {
            "straight": image_straight,
            "left": image_left,
            "right": image_right,
            "top": image_top,
            "down": image_down,
        }
        optional_images = await read_optional_upload_map(upload_map)
        completed_now = False
        if optional_images:
            if len(optional_images) != len(REQUIRED_FACE_VIEWS):
                return JSONResponse({"error": "Upload all five face images together to complete the profile."}, status_code=400)
            view_embeddings, view_errors = extract_multi_view_embeddings_from_images(optional_images)
            if view_errors:
                return JSONResponse({"error": "Unable to process uploaded face images.", "view_errors": view_errors}, status_code=400)
            embedding = view_embeddings["straight"]["embedding"]
            success_views = profile_db.update_profile_view_embeddings(profile_id, embedding, view_embeddings)
            if not success_views:
                return JSONResponse({"error": "Failed to save face images for this profile."}, status_code=500)
            engine.register_face_views_from_arrays(profile_id, name or profile["name"], view_embeddings, embedding)
            completed_now = True

        if not success and not completed_now:
            return JSONResponse({"error": "No fields to update"}, status_code=400)
        
        # Update in-memory engine profiles (if name was changed)
        if name and profile_id in engine.profiles:
            engine.profiles[profile_id]['name'] = name
        
        logger.info(
            f"✓ Updated profile {profile_id}: name={name}, email={email}, "
            f"dept={department}, profile_type={normalized_profile_type}"
        )
        
        return {
            "status": "success",
            "profile_id": profile_id,
            "profile_complete": completed_now or bool((profile_db.get_profile(profile_id) or {}).get("profile_complete")),
            "message": "Profile updated successfully"
        }
    
    except Exception as e:
        logger.error(f"Edit profile error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/profiles/bulk-upload")
async def bulk_upload_profiles(
    file: UploadFile = File(...),
    profile_type: str = Form("student"),
    authorization: str = Header(None),
):
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_PEOPLE_MANAGE)
        if error:
            return error

        raw_bytes = await file.read()
        if not raw_bytes:
            return JSONResponse({"error": "Uploaded file is empty"}, status_code=400)

        frame = parse_bulk_profiles_dataframe(file.filename, raw_bytes).fillna("")
        rows = frame.to_dict(orient="records")
        created = 0
        skipped = []

        for index, row in enumerate(rows, start=2):
            name = str(row.get("name") or row.get("full_name") or "").strip()
            if not name:
                skipped.append({"row": index, "reason": "Name is required"})
                continue

            row_profile_type = str(row.get("profile_type") or profile_type or "student").strip().lower()
            if row_profile_type not in {"faculty", "student"}:
                skipped.append({"row": index, "reason": "Invalid profile_type"})
                continue

            class_name = str(row.get("class_name") or row.get("class") or "").strip() or None
            section_name = str(row.get("section_name") or row.get("section") or "").strip() or None
            roll_number = str(row.get("roll_number") or row.get("roll") or "").strip() or None
            if row_profile_type == "student" and (not class_name or not section_name or not roll_number):
                skipped.append({"row": index, "reason": "Student rows require class_name, section_name, and roll_number"})
                continue

            try:
                profile_db.add_profile(
                    profile_db.normalize_profile_name(name),
                    None,
                    profile_type=row_profile_type,
                    email=str(row.get("email") or "").strip() or None,
                    department=str(row.get("department") or "").strip() or None,
                    class_name=class_name,
                    section_name=section_name,
                    roll_number=roll_number,
                    check_in_time=str(row.get("check_in_time") or "09:00").strip() or "09:00",
                    check_out_time=str(row.get("check_out_time") or "17:00").strip() or "17:00",
                    view_embeddings={},
                    profile_complete=False,
                    recognition_trained=False,
                    profile_status="incomplete",
                )
                created += 1
            except DuplicateProfileError:
                skipped.append({"row": index, "reason": f"Profile '{name}' already exists"})

        return {
            "status": "success",
            "created": created,
            "skipped": skipped,
            "message": f"{created} profiles saved as incomplete. Upload face images later from profile settings to complete them."
        }
    except Exception as e:
        logger.error(f"Bulk upload error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

def generate_video_stream():
    """Generate video stream from the shared background webcam thread.
    Reads annotated frames produced by _run_local_webcam_recognition()."""
    import time
    
    if not _webcam_running:
        # Webcam not available — generate placeholder frames
        for frame_num in range(300):
            try:
                test_frame = np.ones((600, 800, 3), dtype=np.uint8) * 100
                cv2.putText(test_frame, f"Test Frame #{frame_num}", (100, 100),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(test_frame, "Camera Not Available", (150, 300),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                cv2.putText(test_frame, "Check camera connection and permissions", (80, 400),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
                
                ret, buffer = cv2.imencode('.jpg', test_frame)
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in test frame generation: {e}")
                break
        return
    
    try:
        while _webcam_running:
            with _webcam_lock:
                # Always prefer annotated frame (updated every frame now with cached detections)
                frame = _webcam_latest_annotated if _webcam_latest_annotated is not None else _webcam_latest_frame
            
            if frame is None:
                time.sleep(0.01)
                continue
            
            try:
                # Encode frame as JPEG with good quality
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except Exception as e:
                logger.error(f"Error encoding frame: {e}")
            
            time.sleep(0.033)  # ~30 FPS
    except GeneratorExit:
        logger.info("Client closed video stream")
    except Exception as e:
        logger.error(f"Unexpected error in video stream: {e}")


def _annotate_frame(frame, result):
    """Draw recognition results on frame
    
    Args:
        frame: Input BGR frame
        result: Dict from engine.process_frame() with detections
    
    Returns:
        Annotated frame with boxes and labels
    """
    annotated = frame.copy()
    
    for det in result.get('detections', []):
        x, y, w, h = det['bbox']
        name = det['name']
        confidence = det['confidence']
        emotion = det.get('emotion', 'unknown')
        
        # Color: green if recognized, orange if unknown
        if name == 'Unknown':
            color = (0, 165, 255)  # Orange
        else:
            color = (0, 255, 0)  # Green
        
        # Draw bounding box
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        
        # Draw name label
        label = f"{name}"
        if confidence > 0:
            label += f" ({confidence:.0%})"
        
        cv2.putText(annotated, label, (x, max(y - 10, 20)),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Draw emotion (if available and not unknown)
        if emotion != 'unknown':
            emotion_text = f"😊 {emotion}"
            cv2.putText(annotated, emotion_text, (x, y + h + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    # Draw frame info
    cv2.putText(annotated, f"Frame: {result.get('frame_count', 0)}", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(annotated, f"Detections: {len(result.get('detections', []))}", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    
    return annotated


def _encode_debug_image(image, jpeg_quality=82):
    try:
        import cv2

        success, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        if not success:
            return None
        return base64.b64encode(buffer.tobytes()).decode("utf-8")
    except Exception as exc:
        logger.debug(f"Failed to encode debug image: {exc}")
        return None

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_video_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

# ============ ATTENDANCE DASHBOARD ENDPOINTS ============

@app.get("/api/attendance/today")
async def get_today_attendance():
    """Get present/absent status for today"""
    result = attendance_tracker.get_today_presence()
    if result:
        return result
    return JSONResponse({"error": "Failed to get attendance data"}, status_code=500)

@app.get("/api/attendance/report/{date_str}")
async def get_daily_attendance(date_str: str):
    """Get detailed attendance report for a specific date (YYYY-MM-DD)"""
    result = attendance_tracker.get_daily_report(date_str)
    if result:
        # Convert timestamps to IST
        for record in result.get('records', []):
            if record.get('first_seen'):
                record['first_seen'] = to_ist(record['first_seen'])
            if record.get('last_seen'):
                record['last_seen'] = to_ist(record['last_seen'])
        return result
    return JSONResponse({"error": "Failed to get attendance report"}, status_code=500)

@app.get("/api/attendance/weekly")
async def get_weekly_attendance():
    """Get weekly attendance summary (last 7 days)"""
    result = attendance_tracker.get_weekly_summary()
    if result:
        return {"weekly_summary": result}
    return JSONResponse({"error": "Failed to get weekly summary"}, status_code=500)

@app.get("/api/attendance/reports/summary")
async def get_attendance_report_summary(start_date: str = None, end_date: str = None):
    """Get attendance summary for an inclusive date range."""
    result = attendance_tracker.get_attendance_summary_range(start_date, end_date)
    if result:
        return result
    return JSONResponse({"error": "Failed to get attendance summary report"}, status_code=500)

@app.get("/api/attendance/reports")
async def get_attendance_reports(
    report_type: str = "daily",
    date: str = None,
    week_start: str = None,
    month: str = None,
    start_date: str = None,
    end_date: str = None,
    authorization: str = Header(None),
):
    """Get attendance reports using daily, weekly, monthly, or custom filters."""
    user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_VIEW)
    if error:
        return error
    try:
        resolved_start, resolved_end = resolve_attendance_report_range(
            report_type=report_type,
            date=date,
            week_start=week_start,
            month=month,
            start_date=start_date,
            end_date=end_date
        )
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)

    result = _build_attendance_report_payload(resolved_start, resolved_end)
    if result:
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            scoped_profiles = get_scoped_profiles_for_user(user, profile_type="student")
            profile_ids = {profile["id"] for profile in scoped_profiles}
            person_records = [row for row in (result.get("person_records") or []) if row.get("profile_id") in profile_ids]
            date_buckets = {}
            for row in person_records:
                entry = date_buckets.setdefault(row["date"], {"date": row["date"], "present": 0, "absent": 0, "late": 0, "total_profiles": 0})
                entry["total_profiles"] += 1
                if row.get("status") in {"present", "late"}:
                    entry["present"] += 1
                else:
                    entry["absent"] += 1
                if row.get("status") == "late":
                    entry["late"] += 1
            result["person_records"] = person_records
            result["records"] = [
                {
                    **entry,
                    "attendance_rate": _safe_percent(entry["present"], entry["total_profiles"]),
                }
                for _, entry in sorted(date_buckets.items())
            ]
            result["summary"] = {
                "total_days": len(result["records"]),
                "total_present": sum(row["present"] for row in result["records"]),
                "total_absent": sum(row["absent"] for row in result["records"]),
                "average_attendance_rate": round(
                    sum(row["attendance_rate"] for row in result["records"]) / len(result["records"]),
                    2,
                ) if result["records"] else 0.0,
            }
        result["report_type"] = report_type
        result["filters"] = {
            "date": date,
            "week_start": week_start,
            "month": month,
            "start_date": start_date,
            "end_date": end_date
        }
        return result

    return JSONResponse({"error": "Failed to get attendance report"}, status_code=500)

# ============ NEW FEATURE ENDPOINTS ============

@app.get("/api/attendance/dashboard")
async def get_attendance_dashboard_analytics(
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    role_scope: str = "faculty",
    class_name: str = None,
    section_name: str = None,
    authorization: str = Header(None)
):
    """Get dashboard-ready attendance analytics for operations and reporting."""
    try:
        user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_VIEW)
        if error:
            return error

        selected_date = date or app_now().strftime("%Y-%m-%d")
        selected_start = start_date or selected_date
        selected_end = end_date or selected_date
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            if class_name and class_name not in (scope.get("class_names") or []):
                return JSONResponse({"error": "Forbidden"}, status_code=403)
            if section_name and section_name not in (scope.get("section_names") or []):
                return JSONResponse({"error": "Forbidden"}, status_code=403)
            role_scope = "student"
            class_name = class_name or (scope.get("class_names") or [None])[0]
            section_name = section_name or (scope.get("section_names") or [None])[0]

        analytics = attendance_tracker.get_attendance_dashboard_analytics(
            dashboard_date=selected_date,
            start_date=selected_start,
            end_date=selected_end,
            role_scope=role_scope,
            class_name=class_name,
            section_name=section_name
        )

        if not analytics:
            return JSONResponse({"error": "Failed to load attendance dashboard analytics"}, status_code=500)

        analytics["marking_status"] = _build_attendance_marking_status()

        cameras = [
            camera for camera in cctv_manager.get_all_cameras()
            if camera.get("enabled", True) and camera.get("processing_enabled", True)
        ]
        source_statuses = []
        for camera in cameras:
            camera_type = (camera.get("type") or "").upper()
            if camera_type == "LOCAL_WEBCAM":
                is_running = bool(_webcam_running)
                camera_status = "running" if is_running else "stopped"
            else:
                recognition_status = get_runtime_state(camera["id"])
                is_running = bool(recognition_status.get("is_running"))
                camera_status = recognition_status.get("status", "unknown")

            source_statuses.append({
                "id": camera["id"],
                "name": camera["name"],
                "type": camera.get("type"),
                "running": is_running,
                "status": camera_status,
                "connection_status": cctv_manager.get_camera_latest_status(camera["id"])
            })

        analytics["source_statuses"] = source_statuses
        return {
            "status": "success",
            "data": analytics
        }
    except Exception as e:
        logger.error(f"Error loading attendance dashboard analytics: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/attendance/check-in-out")
async def get_checkin_checkout(date: str = None, authorization: str = Header(None)):
    """Get check-in and check-out times for all profiles (returns IST times)"""
    user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_VIEW)
    if error:
        return error
    result = attendance_tracker.get_check_in_check_out(date)
    if result:
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            scoped_profiles = get_scoped_profiles_for_user(user, profile_type="student")
            allowed_ids = {profile["id"] for profile in scoped_profiles}
            result["records"] = filter_records_by_profiles(result.get("records"), allowed_ids)
        # Convert summary time-of-day fields to IST for UI display
        for record in result.get('records', []):
            if record.get('check_in_time'):
                record['check_in_time_utc'] = record['check_in_time']
                record['check_in_time'] = to_ist_time_only(record['check_in_time'])
            if record.get('check_out_time'):
                record['check_out_time_utc'] = record['check_out_time']
                record['check_out_time'] = to_ist_time_only(record['check_out_time'])
        return result
    return JSONResponse({"error": "Failed to get check-in/check-out data"}, status_code=500)

@app.get("/api/attendance/continuous-presence")
async def get_continuous_presence(min_detections: int = 5):
    """Get report of people with continuous presence (not single frame)"""
    result = attendance_tracker.get_continuous_presence_report(min_detections)
    if result:
        return result
    return JSONResponse({"error": "Failed to get continuous presence report"}, status_code=500)

@app.get("/api/attendance/marking/status")
async def get_attendance_marking_status(authorization: str = Header(None)):
    """Get overall attendance-marking status across enabled sources."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_VIEW)
        if error:
            return error

        return {
            "status": "success",
            "data": _build_attendance_marking_status()
        }
    except Exception as e:
        logger.error(f"Error getting attendance marking status: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/attendance/marking/start")
async def start_attendance_marking(authorization: str = Header(None)):
    """Start attendance marking across all enabled camera sources."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_MANAGE)
        if error:
            return error

        # Attendance marking must remain attendance-only.
        cctv_recognition_engine.enable_activity_detection = False
        cctv_recognition_engine.activity_detector = None

        enabled_cameras = [
            camera
            for camera in cctv_manager.get_all_cameras()
            if camera.get("enabled", True) and camera.get("processing_enabled", True)
        ]
        if not enabled_cameras:
            return JSONResponse({"error": "No enabled cameras available."}, status_code=400)

        results = []

        for camera in enabled_cameras:
            camera_type = (camera.get("type") or "").upper()

            if camera_type == "LOCAL_WEBCAM":
                result = _start_local_webcam_thread()
            else:
                result = _request_recognition_state(camera["id"], True, mode="attendance", requested_by="attendance_marking")

            results.append({
                "id": camera["id"],
                "name": camera["name"],
                "type": camera.get("type"),
                "success": bool(result.get("success")),
                "message": result.get("message", "")
            })

        return {
            "status": "success",
            "message": "Attendance marking start command sent.",
            "results": results,
            "data": _build_attendance_marking_status()
        }
    except Exception as e:
        logger.error(f"Error starting attendance marking: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/attendance/marking/stop")
async def stop_attendance_marking(authorization: str = Header(None)):
    """Stop attendance marking across all enabled camera sources."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_MANAGE)
        if error:
            return error

        enabled_cameras = [
            camera
            for camera in cctv_manager.get_all_cameras()
            if camera.get("enabled", True) and camera.get("processing_enabled", True)
        ]
        if not enabled_cameras:
            return JSONResponse({"error": "No enabled cameras available."}, status_code=400)

        results = []

        for camera in enabled_cameras:
            camera_type = (camera.get("type") or "").upper()

            if camera_type == "LOCAL_WEBCAM":
                result = _stop_local_webcam_thread()
            else:
                result = _request_recognition_state(camera["id"], False, mode="attendance", requested_by="attendance_marking")

            results.append({
                "id": camera["id"],
                "name": camera["name"],
                "type": camera.get("type"),
                "success": bool(result.get("success")),
                "message": result.get("message", "")
            })

        return {
            "status": "success",
            "message": "Attendance marking stop command sent.",
            "results": results,
            "data": _build_attendance_marking_status()
        }
    except Exception as e:
        logger.error(f"Error stopping attendance marking: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/attendance/late-arrivals")
async def get_late_arrivals(date: str = None):
    """Get list of late arrivals based on class schedule (returns IST times)"""
    result = attendance_tracker.get_late_arrivals(date)
    if result:
        # Convert times to IST
        for arrival in result.get('late_arrivals', []):
            if arrival.get('arrival_time'):
                arrival['arrival_time_utc'] = arrival['arrival_time']
                arrival['arrival_time'] = to_ist(arrival['arrival_time'])
        return result
    return JSONResponse({"error": "Failed to get late arrivals"}, status_code=500)

@app.get("/api/attendance/absent-members")
async def get_absent_members(date: str = None):
    """Get list of absent members for a specific date"""
    result = attendance_tracker.get_absent_members(date)
    if result:
        return result
    return JSONResponse({"error": "Failed to get absent members"}, status_code=500)

@app.get("/api/attendance/filter")
async def filter_attendance(date: str = None, filter_type: str = "all"):
    """
    Filter attendance records by status
    
    Args:
        date: Date in YYYY-MM-DD format (default: today)
        filter_type: 'present', 'absent', 'late', or 'all' (default: all)
    
    Returns:
        Filtered attendance records
    """
    try:
        if date is None:
            from datetime import date as date_cls
            date = date_cls.today().isoformat()
        
        if filter_type == "all":
            result = attendance_tracker.get_today_presence() if date == app_now().strftime('%Y-%m-%d') else attendance_tracker.get_daily_report(date)
        elif filter_type == "present":
            result = attendance_tracker.get_today_presence() if date == app_now().strftime('%Y-%m-%d') else None
            if result:
                result = {"date": date, "records": [{"id": p['id'], "name": p['name'], "status": "present"} for p in result.get('present', [])]}
        elif filter_type == "absent":
            result = attendance_tracker.get_absent_members(date)
        elif filter_type == "late":
            result = attendance_tracker.get_late_arrivals(date)
            # Convert times to IST
            if result:
                for arrival in result.get('late_arrivals', []):
                    if arrival.get('arrival_time'):
                        arrival['arrival_time'] = to_ist(arrival['arrival_time'])
        else:
            return JSONResponse({"error": "Invalid filter_type"}, status_code=400)
        
        return result if result else JSONResponse({"error": "No data found"}, status_code=404)
    except Exception as e:
        logger.error(f"Filter attendance error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/attendance/class-schedule")
async def set_class_schedule(date: str, start_time: str, end_time: str, class_name: str = "Default"):
    """Set class schedule for late arrival detection
    
    Args:
        date: Date in YYYY-MM-DD format
        start_time: Class start time in HH:MM:SS format
        end_time: Class end time in HH:MM:SS format
        class_name: Optional class name
    """
    try:
        success = attendance_tracker.set_class_schedule(date, start_time, end_time, class_name)
        if success:
            return {"status": "success", "message": f"Class schedule set for {date}"}
        else:
            return JSONResponse({"error": "Failed to set class schedule"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/attendance/export/csv")
async def export_csv(date: str = None, start_date: str = None, end_date: str = None):
    """Export attendance data as CSV."""
    if start_date or end_date:
        csv_data = attendance_tracker.export_attendance_summary_csv(start_date, end_date)
        normalized_start = start_date or end_date or app_now().strftime('%Y-%m-%d')
        normalized_end = end_date or start_date or normalized_start
        filename = f"attendance-report-{normalized_start}-to-{normalized_end}.csv"
    else:
        normalized_date = date or app_now().strftime('%Y-%m-%d')
        csv_data = attendance_tracker.export_attendance_csv(normalized_date)
        filename = f"attendance-report-{normalized_date}.csv"

    if csv_data:
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    return JSONResponse({"error": "Failed to export CSV"}, status_code=500)

@app.get("/api/attendance/reports/export/csv")
async def export_report_csv(
    report_type: str = "daily",
    date: str = None,
    week_start: str = None,
    month: str = None,
    start_date: str = None,
    end_date: str = None,
    authorization: str = Header(None),
):
    """Export attendance reports as CSV using report-type-based filters."""
    _user, error = require_capability_user(authorization, CAPABILITY_ATTENDANCE_EXPORT)
    if error:
        return error
    try:
        resolved_start, resolved_end = resolve_attendance_report_range(
            report_type=report_type,
            date=date,
            week_start=week_start,
            month=month,
            start_date=start_date,
            end_date=end_date
        )
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)

    csv_data = attendance_tracker.export_attendance_summary_csv(resolved_start, resolved_end)
    filename = f"attendance-report-{report_type}-{resolved_start}-to-{resolved_end}.csv"

    if csv_data:
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    return JSONResponse({"error": "Failed to export report CSV"}, status_code=500)

@app.get("/api/attendance/export/pdf")
async def export_pdf(date: str = None):
    """Export attendance data as PDF file"""
    pdf_path = attendance_tracker.export_attendance_pdf(date)
    if pdf_path:
        # Return file info for download
        return {
            "status": "success",
            "format": "pdf",
            "file_path": pdf_path
        }
    return JSONResponse({"error": "Failed to export PDF - reportlab may not be installed"}, status_code=500)

@app.put("/api/attendance/update-times")
async def update_check_in_out(data: dict = Body(...)):
    """Update check-in and check-out times for a profile
    
    Request body:
    {
        "profile_id": 4,
        "date": "2026-03-28",
        "check_in_time": "08:30:00",
        "check_out_time": "17:00:00"
    }
    """
    try:
        profile_id = data.get('profile_id')
        date = data.get('date')
        check_in_time = data.get('check_in_time')
        check_out_time = data.get('check_out_time')
        
        if not all([profile_id, date, check_in_time, check_out_time]):
            return JSONResponse({"error": "Missing required fields"}, status_code=400)
        
        success = attendance_tracker.update_check_in_out_times(profile_id, date, check_in_time, check_out_time)
        
        if success:
            return {"status": "success", "message": "Times updated successfully"}
        else:
            return JSONResponse({"error": "Failed to update times"}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ============ EMOTION ANALYTICS ENDPOINTS ============

@app.get("/api/emotions/day-wise")
async def get_day_wise_emotions(date: str, profile_ids: str = None, authorization: str = Header(None)):
    """
    Get day-wise emotion distribution for faculty/employees.
    
    Query parameters:
        date: YYYY-MM-DD format (required)
        profile_ids: Comma-separated profile IDs to filter (optional)
    
    Returns:
    {
        'date': str,
        'total_detections': int,
        'distribution': {
            'profile_id': {
                'name': str,
                'emotions': {emotion: count},
                'dominant_emotion': str,
                'average_confidence': float,
                'total_detections': int
            }
        }
    }
    """
    user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
    if error:
        return error
    
    try:
        profile_list = None
        if profile_ids:
            profile_list = [int(pid.strip()) for pid in profile_ids.split(',')]
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            scoped_profiles = get_scoped_profiles_for_user(user, profile_type="student")
            allowed_ids = {profile["id"] for profile in scoped_profiles}
            if profile_list and not set(profile_list).issubset(allowed_ids):
                return JSONResponse({"error": "Forbidden"}, status_code=403)
            profile_list = sorted(allowed_ids)
        
        from emotion_detector import EmotionAnalytics
        emotion_analytics = EmotionAnalytics(attendance_tracker.db_path)
        result = emotion_analytics.get_day_wise_distribution(date, profile_list)
        
        return result
    except Exception as e:
        logger.error(f"Failed to get day-wise emotions: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/emotions/session-wise")
async def get_session_wise_emotions(session_id: int = None, course_id: int = None, 
                                    authorization: str = Header(None)):
    """
    Get session-wise emotion distribution for students.
    
    Query parameters:
        session_id: Class session ID (optional)
        course_id: Course ID (optional, returns all sessions for course)
    
    Returns:
    {
        'session_id': int,
        'emotion_distribution': {emotion: count},
        'student_emotions': {
            'student_id': {
                'name': str,
                'emotions': {emotion: count},
                'dominant_emotion': str
            }
        },
        'average_mood': str,
        'class_sentiment': str
    }
    """
    _user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
    if error:
        return error
    
    try:
        from emotion_detector import EmotionAnalytics
        emotion_analytics = EmotionAnalytics(attendance_tracker.db_path)
        result = emotion_analytics.get_session_wise_distribution(session_id, course_id)
        
        return result
    except Exception as e:
        logger.error(f"Failed to get session-wise emotions: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/emotions/trends")
async def get_emotion_trends(start_date: str, end_date: str, profile_id: int = None,
                            authorization: str = Header(None)):
    """
    Get emotion trends over a date range.
    
    Query parameters:
        start_date: YYYY-MM-DD (required)
        end_date: YYYY-MM-DD (required)
        profile_id: Specific profile (optional, returns all if not provided)
    
    Returns:
    {
        'date_range': [start, end],
        'daily_trends': {date: emotion_distribution},
        'overall_stats': emotion_stats,
        'most_common_emotion': str
    }
    """
    user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
    if error:
        return error
    
    try:
        from emotion_detector import EmotionAnalytics
        emotion_analytics = EmotionAnalytics(attendance_tracker.db_path)
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted") and profile_id is not None:
            scoped_profiles = get_scoped_profiles_for_user(user, profile_type="student")
            if profile_id not in {profile["id"] for profile in scoped_profiles}:
                return JSONResponse({"error": "Forbidden"}, status_code=403)
        result = emotion_analytics.get_emotion_trends(start_date, end_date, profile_id)
        
        return result
    except Exception as e:
        logger.error(f"Failed to get emotion trends: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/emotions/students/{profile_id}")
async def get_student_emotion_timeline(
    profile_id: int,
    start_date: str = None,
    end_date: str = None,
    location: str = None,
    authorization: str = Header(None),
):
    user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
    if error:
        return error

    try:
        from emotion_detector import EmotionAnalytics
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            scoped_profiles = get_scoped_profiles_for_user(user, profile_type="student")
            if profile_id not in {profile["id"] for profile in scoped_profiles}:
                return JSONResponse({"error": "Forbidden"}, status_code=403)

        today = app_now().strftime("%Y-%m-%d")
        resolved_end = end_date or today
        resolved_start = start_date or resolved_end
        emotion_analytics = EmotionAnalytics(attendance_tracker.db_path)
        result = emotion_analytics.get_student_timeline(
            profile_id=profile_id,
            start_date=resolved_start,
            end_date=resolved_end,
            location=location,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get student emotion timeline: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/emotions/by-location")
async def get_emotions_by_location(date: str = None, authorization: str = Header(None)):
    """
    Get emotion distribution grouped by camera location.
    Shows actual detected emotions for each enabled camera and other recording locations.
    
    Query parameters:
        date: Optional YYYY-MM-DD format to filter by specific date
              If not provided, returns last 24 hours of data
    
    Returns:
    {
        'date': str,
        'locations': {
            'camera_name': {
                'emotions': {emotion: count},
                'total_detections': int,
                'dominant_emotion': str
            }
        }
    }
    """
    _user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
    if error:
        return error
    
    try:
        from emotion_detector import EmotionAnalytics
        analytics = EmotionAnalytics(attendance_tracker.db_path)
        locations = analytics.get_location_distribution(date=date)
        return JSONResponse(
            {
                'date': date or 'last_24_hours',
                'locations': locations,
                'total_locations': len(locations)
            },
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    except Exception as e:
        logger.error(f"Failed to get emotions by location: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/emotions/log")
async def log_emotion_detection(data: dict = Body(...)):
    """
    Log emotion detection (called by face detection pipeline).
    
    Request body:
    {
        'profile_id': int,
        'name': str,
        'date': 'YYYY-MM-DD',
        'emotion': str,
        'emotion_confidence': float,
        'emotion_intensity': str,
        'all_emotions': dict
    }
    """
    try:
        profile_id = data.get('profile_id')
        name = data.get('name')
        date = data.get('date')
        emotion = data.get('emotion', 'Neutral')
        emotion_confidence = data.get('emotion_confidence', 0.0)
        emotion_intensity = data.get('emotion_intensity', 'low')
        all_emotions = data.get('all_emotions', {})
        
        if using_mongo_runtime():
            mongo_store.collection("emotion_analytics").update_one(
                {
                    "profile_id": profile_id,
                    "date": date,
                    "emotion": emotion,
                    "emotion_intensity": emotion_intensity,
                },
                {
                    "$set": {
                        "name": name,
                        "emotion_confidence": emotion_confidence,
                        "updated_at": app_now(),
                    },
                    "$setOnInsert": {
                        "_id": mongo_store.next_id("emotion_analytics"),
                        "timestamp": app_now(),
                    },
                    "$inc": {"detection_count": 1},
                },
                upsert=True
            )
        else:
            return JSONResponse({"error": "MongoDB is required for emotion analytics logging"}, status_code=503)
        
        return {"status": "logged", "emotion": emotion}
    except Exception as e:
        logger.error(f"Failed to log emotion: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/classroom/emotions")
async def get_classroom_emotions(location: str = None, date: str = None, authorization: str = Header(None)):
    """
    Get real-time emotion analytics for classroom cameras - NO AUTHENTICATION REQUIRED.
    Designed for monitoring student emotions in classroom settings like Petals 306 F.
    
    Query parameters:
        location: Filter by camera location (e.g., "Petals 306 F"), optional
        date: Filter by specific date YYYY-MM-DD, optional (defaults to today)
    
    Returns:
    {
        'status': 'success',
        'date': 'YYYY-MM-DD',
        'locations': {
            'Petals 306 F': {
                'total_detections': int,
                'dominant_emotion': 'Happy'|'Sad'|'Angry'|'Neutral'|'Surprised'|'Fearful'|'Disgusted',
                'emotions': {
                    'Happy': 25,
                    'Neutral': 15,
                    'Sad': 5,
                    ...
                },
                'emotion_percentages': {
                    'Happy': 55.6,
                    'Neutral': 33.3,
                    ...
                },
                'last_updated': 'HH:MM:SS'
            }
        }
    }
    """
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
        if error:
            return error
        # Use provided date or today
        if not date:
            date = app_now().strftime('%Y-%m-%d')
        from emotion_detector import EmotionAnalytics
        analytics = EmotionAnalytics(attendance_tracker.db_path)
        locations = analytics.get_location_distribution(date=date, location=location)
        
        return {
            'status': 'success',
            'date': date,
            'locations': locations,
            'total_locations': len(locations),
            'timestamp': app_now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error getting classroom emotions: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'locations': {}
        }


# ============ ACTIVITY ANALYTICS ENDPOINTS ============

@app.get("/api/activities/by-location")
async def get_activities_by_location(date: str = None, authorization: str = Header(None)):
    """
    Get activity distribution grouped by camera location.
    Uses REAL-TIME detections from the current frame — counts actual faces visible now.
    
    Each face in the frame = 1 person. Activity is what that person is doing RIGHT NOW.
    Engagement = (positive_activity_people / total_people) * 100%
    
    Positive engagement: Writing, Reading, Listening, Collaboration, Raised_Hand
    Low engagement: Playing, Fighting, Distracted, Phone_Use, Eating, Sleeping
    """
    user, error = require_capability_user(authorization, CAPABILITY_ACTIVITIES_VIEW)
    if error:
        return error
    
    try:
        POSITIVE_ACTIVITIES = {'Writing', 'Reading', 'Listening', 'Collaboration', 'Raised_Hand'}
        LOW_ENGAGEMENT_ACTIVITIES = {'Playing', 'Fighting', 'Distracted', 'Phone_Use', 'Eating', 'Sleeping'}
        
        locations = {}
        
        camera_map = {
            camera["id"]: camera["name"]
            for camera in cctv_manager.get_all_cameras()
            if camera.get("enabled") and camera.get("processing_enabled", True)
        }
        
        # Use REAL-TIME detections from the recognition engine
        # This gives us the exact faces visible in the most recent frame per camera
        scope = user.get("scope") or get_user_scope(user)
        allowed_camera_ids = set(scope.get("camera_ids") or [])
        allowed_camera_names = set(scope.get("camera_names") or [])
        for camera_id, camera_name in camera_map.items():
            if scope.get("restricted") and allowed_camera_ids and camera_id not in allowed_camera_ids and camera_name not in allowed_camera_names:
                continue
            detections = get_runtime_latest_detections(camera_id)
            
            if not detections or not detections.get('updated_at'):
                continue
            
            known_faces = detections.get('known_faces', [])
            unknown_faces = detections.get('unknown_faces', [])
            all_faces = known_faces + unknown_faces
            
            if not all_faces:
                continue
            
            # Count activity distribution from current frame
            activity_counts = {}
            for face in all_faces:
                activity = face.get('activity', 'Unknown')
                if activity == 'Unknown':
                    continue
                activity_counts[activity] = activity_counts.get(activity, 0) + 1
            
            if not activity_counts:
                continue
            
            total_people = sum(activity_counts.values())
            positive_count = sum(c for a, c in activity_counts.items() if a in POSITIVE_ACTIVITIES)
            low_count = sum(c for a, c in activity_counts.items() if a in LOW_ENGAGEMENT_ACTIVITIES)
            
            engagement_pct = (positive_count / total_people * 100.0) if total_people > 0 else 0.0
            
            if engagement_pct >= 75:
                engagement_cat = 'High'
            elif engagement_pct >= 50:
                engagement_cat = 'Medium'
            else:
                engagement_cat = 'Low'
            
            dominant = max(activity_counts.items(), key=lambda x: x[1])[0] if activity_counts else None
            
            locations[camera_name] = {
                'activities': activity_counts,
                'total_people': total_people,
                'positive_engagement_count': positive_count,
                'low_engagement_count': low_count,
                'engagement_percentage': round(engagement_pct, 1),
                'engagement_category': engagement_cat,
                'dominant_activity': dominant,
                'average_confidence': 0.75
            }
        
        logger.info(f"✓ Activity API (real-time): {len(locations)} locations with current detections")
        for loc, data in locations.items():
            logger.info(f"  {loc}: {data['total_people']} people, activities={data['activities']}")
        
        # Log cameras checked but skipped (for debugging empty classrooms)
        for camera_id, camera_name in camera_map.items():
            if camera_name not in locations:
                detections = get_runtime_latest_detections(camera_id)
                updated_at = detections.get('updated_at') if detections else None
                all_faces = (detections.get('known_faces', []) + detections.get('unknown_faces', [])) if detections else []
                logger.debug(f"  SKIPPED {camera_name}: updated_at={updated_at}, faces={len(all_faces)}")
        
        
        return JSONResponse(
            {
                'date': date or 'real_time',
                'locations': locations,
                'total_locations': len(locations),
                'positive_activities': list(POSITIVE_ACTIVITIES),
                'low_engagement_activities': list(LOW_ENGAGEMENT_ACTIVITIES)
            },
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    except Exception as e:
        logger.error(f"Failed to get activities by location: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/activities/by-person")
async def get_activities_by_person(location: str = None, authorization: str = Header(None)):
    """
    Get detailed person-by-person activities in a classroom.
    Shows EACH PERSON's most recent activity and emotions.
    
    Query parameters:
        location: Optional camera location to filter (e.g., "CP IP Camera - Chronosphere")
                 If not provided, returns all locations
    
    Returns:
    {
        'location': str,
        'people': [
            {
                'name': 'Avika Landge',
                'activity': 'Distracted',
                'activity_confidence': 0.65,
                'emotion': 'Neutral',
                'emotion_confidence': 0.38,
                'last_detected': '2026-04-06 16:45:23',
                'detection_count': 45  ← Total times detected in this activity
            },
            ...
        ],
        'summary': {
            'total_people': 3,
            'activity_breakdown': {'Distracted': 2, 'Listening': 1}
        }
    }
    """
    user, error = require_capability_user(authorization, CAPABILITY_ACTIVITIES_VIEW)
    if error:
        return error
    
    try:
        start_time = app_now() - timedelta(days=1)
        docs = iter_activity_docs(location=location, start_time=start_time, exclude_unknown=True)
        scope = user.get("scope") or get_user_scope(user)
        if scope.get("restricted"):
            allowed_profiles = {profile["id"] for profile in get_scoped_profiles_for_user(user, profile_type="student")}
            docs = [doc for doc in docs if doc.get("profile_id") in allowed_profiles]
        locations_in_data = sorted({doc.get("location") for doc in docs if doc.get("location")}) if not location else []
        
        # Format response - group by location and person
        response_data = {}
        bucket_name = location if location else "All Locations"
        aggregated = {}
        for doc in docs:
            key = (doc.get("name"), doc.get("activity"))
            record = aggregated.setdefault(
                key,
                {
                    "name": doc.get("name"),
                    "activity": doc.get("activity"),
                    "activity_confidence": float(doc.get("activity_confidence") or 0.0),
                    "emotion": doc.get("emotion") or "Unknown",
                    "emotion_confidence": float(doc.get("emotion_confidence") or 0.0),
                    "last_detected": doc.get("timestamp"),
                    "detection_count": 0,
                }
            )
            record["detection_count"] += 1
            ts = doc.get("timestamp")
            if isinstance(ts, datetime) and (record["last_detected"] is None or ts > record["last_detected"]):
                record["last_detected"] = ts

        people = []
        activity_summary = {}
        for record in aggregated.values():
            activity_summary[record["activity"]] = activity_summary.get(record["activity"], 0) + 1
            record["last_detected"] = record["last_detected"].isoformat() if isinstance(record["last_detected"], datetime) else record["last_detected"]
            people.append(record)

        response_data[bucket_name] = {
            "people": sorted(people, key=lambda item: item["last_detected"] or "", reverse=True),
            "summary": {
                "total_people": len({item["name"] for item in people}),
                "activity_breakdown": activity_summary,
            }
        }
        
        # If all locations, restructure response
        if not location:
            # For multi-location, return all
            final_response = {
                'locations': response_data,
                'all_locations': locations_in_data
            }
        else:
            final_response = {
                'location': location,
                'people': response_data.get(location, {}).get('people', []),
                'summary': response_data.get(location, {}).get('summary', {})
            }
        
        return JSONResponse(
            final_response,
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    except Exception as e:
        logger.error(f"Failed to get activities by person: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/debug/activity-log")
async def debug_activity_log(authorization: str = Header(None)):
    """Debug endpoint to check what's in the activity_log table"""
    if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        docs = iter_activity_docs(exclude_unknown=False)
        total = len(docs)
        docs_sorted = sorted(
            docs,
            key=lambda item: item.get("timestamp") if isinstance(item.get("timestamp"), datetime) else str(item.get("timestamp") or ""),
            reverse=True
        )
        records = docs_sorted[:20]
        breakdown_map = {}
        for doc in docs:
            activity = doc.get("activity")
            breakdown_map[activity] = breakdown_map.get(activity, 0) + 1
        breakdown = sorted(breakdown_map.items(), key=lambda item: item[1], reverse=True)
        
        return JSONResponse({
            'total_records': total,
            'activity_breakdown': [{'activity': act, 'count': cnt} for act, cnt in breakdown],
            'sample_records': [
                {
                    'id': r.get("_id"),
                    'profile_id': r.get("profile_id"),
                    'name': r.get("name"),
                    'activity': r.get("activity"),
                    'confidence': r.get("activity_confidence"),
                    'location': r.get("location"),
                    'timestamp': r.get("timestamp").isoformat() if isinstance(r.get("timestamp"), datetime) else r.get("timestamp")
                } for r in records
            ]
        })
    except Exception as e:
        logger.error(f"Debug query failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/activities/timeline/{location}")
async def get_activity_timeline(location: str, hours: int = 24, authorization: str = Header(None)):
    """
    Get activity timeline for a specific location over last N hours.
    Shows activity distribution across time periods.
    
    Path parameters:
        location: Camera location name (required)
    
    Query parameters:
        hours: Number of hours to look back (default: 24)
    
    Returns:
    {
        'location': str,
        'hours': int,
        'timeline': {
            'HH:00': {
                'activities': {activity: count},
                'total_detections': int,
                'dominant_activity': str
            }
        }
    }
    """
    _user, error = require_capability_user(authorization, CAPABILITY_ACTIVITIES_VIEW)
    if error:
        return error
    
    try:
        start_time = app_now() - timedelta(hours=hours)
        docs = iter_activity_docs(location=location, start_time=start_time, exclude_unknown=True)
        timeline = {}

        for doc in docs:
            ts = doc.get("timestamp")
            if isinstance(ts, datetime):
                hour = ts.strftime('%H:00')
            else:
                hour = str(ts)[11:13] + ":00"
            activity = doc.get("activity")
            if hour not in timeline:
                timeline[hour] = {
                    'activities': {},
                    'total_detections': 0,
                    'dominant_activity': None
                }
            timeline[hour]['activities'][activity] = timeline[hour]['activities'].get(activity, 0) + 1
            timeline[hour]['total_detections'] += 1
        
        # Find dominant activity for each hour
        for hour in timeline:
            activities = timeline[hour]['activities']
            if activities:
                dominant = max(activities.items(), key=lambda x: x[1])
                timeline[hour]['dominant_activity'] = dominant[0]
        
        logger.info(f"✓ Activity timeline API: {location}, {hours}h, {len(timeline)} periods")
        
        return JSONResponse(
            {
                'location': location,
                'hours': hours,
                'timeline': timeline,
                'periods_with_data': len(timeline)
            },
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    except Exception as e:
        logger.error(f"Failed to get activity timeline: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/activities/engagement/{location}")
async def get_engagement_score(location: str, date: str = None, authorization: str = Header(None)):
    """
    Get engagement score for a classroom location.
    Engagement is derived from activities (high engagement: Listening, Writing, Raised_Hand, Collaboration).
    
    Path parameters:
        location: Camera location name (required)
    
    Query parameters:
        date: Optional YYYY-MM-DD (defaults to today)
    
    Returns:
    {
        'location': str,
        'date': str,
        'engagement_score': 0.0-1.0,
        'engagement_level': 'Low'|'Medium'|'High',
        'activity_breakdown': {
            'high_engagement': {activity: count},
            'medium_engagement': {activity: count},
            'low_engagement': {activity: count}
        },
        'total_detections': int
    }
    """
    _user, error = require_capability_user(authorization, CAPABILITY_ACTIVITIES_VIEW)
    if error:
        return error
    
    try:
        if not date:
            date = app_now().strftime('%Y-%m-%d')
        
        # Define engagement levels
        high_engagement = ['Listening', 'Writing', 'Raised_Hand', 'Collaboration']
        medium_engagement = ['Reading', 'Distracted']
        low_engagement = ['Sleeping', 'Playing', 'Phone_Use', 'Eating']
        
        activity_breakdown = {
            'high_engagement': {},
            'medium_engagement': {},
            'low_engagement': {}
        }
        
        engagement_counts = {'high': 0, 'medium': 0, 'low': 0, 'total': 0}
        
        start, end = attendance_tracker._day_bounds(date)
        docs = iter_activity_docs(location=location, start_time=start, end_time=end, exclude_unknown=True)
        counts_by_activity = {}
        for doc in docs:
            activity = doc.get("activity")
            counts_by_activity[activity] = counts_by_activity.get(activity, 0) + 1

        for activity, count in counts_by_activity.items():
            engagement_counts['total'] += count
            if activity in high_engagement:
                activity_breakdown['high_engagement'][activity] = count
                engagement_counts['high'] += count
            elif activity in medium_engagement:
                activity_breakdown['medium_engagement'][activity] = count
                engagement_counts['medium'] += count
            elif activity in low_engagement:
                activity_breakdown['low_engagement'][activity] = count
                engagement_counts['low'] += count
        
        # Calculate engagement score (0.0 - 1.0)
        if engagement_counts['total'] > 0:
            engagement_score = (
                (engagement_counts['high'] * 1.0 +
                 engagement_counts['medium'] * 0.5 +
                 engagement_counts['low'] * 0.0) / engagement_counts['total']
            )
        else:
            engagement_score = 0.5
        
        # Determine engagement level
        if engagement_score >= 0.7:
            engagement_level = 'High'
        elif engagement_score >= 0.4:
            engagement_level = 'Medium'
        else:
            engagement_level = 'Low'
        
        logger.info(f"✓ Engagement score for {location} on {date}: {engagement_score:.2f}")
        
        return JSONResponse(
            {
                'location': location,
                'date': date,
                'engagement_score': round(engagement_score, 3),
                'engagement_level': engagement_level,
                'activity_breakdown': activity_breakdown,
                'total_detections': engagement_counts['total']
            },
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    except Exception as e:
        logger.error(f"Failed to get engagement score: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/classroom/activities")
async def get_classroom_activities(location: str = None, date: str = None):
    """
    Get real-time activity analytics for classroom cameras - NO AUTHENTICATION REQUIRED.
    Designed for monitoring student activities in classroom settings like Petals 306 F.
    
    Query parameters:
        location: Filter by camera location (e.g., "Petals 306 F"), optional
        date: Filter by specific date YYYY-MM-DD, optional (defaults to today)
    
    Returns:
    {
        'status': 'success',
        'date': 'YYYY-MM-DD',
        'locations': {
            'Petals 306 F': {
                'total_detections': int,
                'dominant_activity': 'Listening'|'Writing'|'Sleeping'|...,
                'activities': {
                    'Listening': 30,
                    'Writing': 25,
                    'Distracted': 5,
                    ...
                },
                'activity_percentages': {
                    'Listening': 50.0,
                    'Writing': 41.7,
                    ...
                },
                'engagement_score': 0.0-1.0,
                'last_updated': 'HH:MM:SS'
            }
        }
    }
    """
    try:
        if not date:
            date = app_now().strftime('%Y-%m-%d')
        locations = {}
        current_time = app_now().strftime('%H:%M:%S')

        if location:
            location_list = [location]
        else:
            location_list = sorted(
                {
                    camera.get("name")
                    for camera in cctv_manager.get_all_cameras()
                    if (
                        camera.get("enabled", True)
                        and camera.get("processing_enabled", True)
                        and (camera.get("camera_context") or "").strip().lower() == "classroom"
                    )
                }
            )

        for loc in location_list:
            start, end = attendance_tracker._day_bounds(date)
            docs = iter_class_activity_docs(location=loc, start_time=start, end_time=end)
            camera_record = next((camera for camera in cctv_manager.get_all_cameras() if camera.get("name") == loc), None)
            if not docs:
                locations[loc] = {
                    'total_windows': 0,
                    'total_detections': 0,
                    'dominant_activity': None,
                    'dominant_student_activity': None,
                    'dominant_faculty_activity': None,
                    'dominant_context': None,
                    'student_activities': {},
                    'faculty_activities': {},
                    'context_activities': {},
                    'student_activity_percentages': {},
                    'faculty_activity_percentages': {},
                    'context_percentages': {},
                    'engagement_score': 0.0,
                    'last_updated': current_time,
                    'recognized_student_count': 0,
                    'recognized_faculty_count': 0,
                    'unknown_count': 0,
                    'class_name': camera_record.get("class_name") if camera_record else None,
                    'section_name': camera_record.get("section_name") if camera_record else None,
                    'camera_context': (camera_record.get("camera_context") if camera_record else "classroom") or "classroom",
                }
                continue
            student_breakdown = {}
            faculty_breakdown = {}
            context_breakdown = {}
            student_high = 0.0
            total_windows = 0
            latest_doc = docs[-1]
            for doc in docs:
                student_label = doc.get("student_activity_label") or "students_uncertain"
                faculty_label = doc.get("faculty_activity_label") or "faculty_uncertain"
                context_label = doc.get("context_label") or "uncertain_context"
                student_breakdown[student_label] = student_breakdown.get(student_label, 0) + 1
                faculty_breakdown[faculty_label] = faculty_breakdown.get(faculty_label, 0) + 1
                context_breakdown[context_label] = context_breakdown.get(context_label, 0) + 1
                total_windows += 1
                if student_label in {"students_attentive", "students_writing", "students_reading"}:
                    student_high += 1.0
                elif student_label in {"students_peer_discussion", "students_mixed"}:
                    student_high += 0.5

            student_percentages = {
                key: round((value / total_windows) * 100, 1) for key, value in student_breakdown.items()
            }
            faculty_percentages = {
                key: round((value / total_windows) * 100, 1) for key, value in faculty_breakdown.items()
            }
            context_percentages = {
                key: round((value / total_windows) * 100, 1) for key, value in context_breakdown.items()
            }
            dominant_student = max(student_breakdown.items(), key=lambda item: item[1])[0] if student_breakdown else "students_uncertain"
            dominant_faculty = max(faculty_breakdown.items(), key=lambda item: item[1])[0] if faculty_breakdown else "faculty_uncertain"
            dominant_context = max(context_breakdown.items(), key=lambda item: item[1])[0] if context_breakdown else "uncertain_context"
            engagement_score = round(student_high / total_windows, 3) if total_windows > 0 else 0.0

            locations[loc] = {
                'total_windows': total_windows,
                'total_detections': total_windows,
                'dominant_activity': dominant_student,
                'dominant_student_activity': dominant_student,
                'dominant_faculty_activity': dominant_faculty,
                'dominant_context': dominant_context,
                'student_activities': student_breakdown,
                'faculty_activities': faculty_breakdown,
                'context_activities': context_breakdown,
                'student_activity_percentages': student_percentages,
                'faculty_activity_percentages': faculty_percentages,
                'context_percentages': context_percentages,
                'engagement_score': engagement_score,
                'last_updated': current_time,
                'recognized_student_count': latest_doc.get("recognized_student_count", 0),
                'recognized_faculty_count': latest_doc.get("recognized_faculty_count", 0),
                'unknown_count': latest_doc.get("unknown_count", 0),
                'class_name': latest_doc.get("class_name") or (camera_record.get("class_name") if camera_record else None),
                'section_name': latest_doc.get("section_name") or (camera_record.get("section_name") if camera_record else None),
                'camera_context': latest_doc.get("camera_context") or ((camera_record.get("camera_context") if camera_record else "classroom") or "classroom"),
            }

        logger.info(f"✓ Classroom activities API: {date}, {len(locations)} locations")

        return {
            'status': 'success',
            'date': date,
            'locations': locations,
            'total_locations': len(locations)
        }
    
    except Exception as e:
        logger.error(f"Error getting classroom activities: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'locations': {}
        }


@app.get("/api/classroom/activities/timeline/{location}")
async def get_classroom_activity_timeline(location: str, hours: int = 24, authorization: str = Header(None)):
    _user, error = require_capability_user(authorization, CAPABILITY_ACTIVITIES_VIEW)
    if error:
        return error
    try:
        start_time = app_now() - timedelta(hours=hours)
        docs = iter_class_activity_docs(location=location, start_time=start_time)
        timeline = {}
        for doc in docs:
            ts = doc.get("timestamp")
            hour = ts.strftime('%H:00') if isinstance(ts, datetime) else str(ts)[11:13] + ":00"
            if hour not in timeline:
                timeline[hour] = {
                    "student_activities": {},
                    "faculty_activities": {},
                    "context_activities": {},
                    "total_windows": 0,
                }
            bucket = timeline[hour]
            student_label = doc.get("student_activity_label") or "students_uncertain"
            faculty_label = doc.get("faculty_activity_label") or "faculty_uncertain"
            context_label = doc.get("context_label") or "uncertain_context"
            bucket["student_activities"][student_label] = bucket["student_activities"].get(student_label, 0) + 1
            bucket["faculty_activities"][faculty_label] = bucket["faculty_activities"].get(faculty_label, 0) + 1
            bucket["context_activities"][context_label] = bucket["context_activities"].get(context_label, 0) + 1
            bucket["total_windows"] += 1
        for bucket in timeline.values():
            if bucket["student_activities"]:
                bucket["dominant_student_activity"] = max(bucket["student_activities"].items(), key=lambda item: item[1])[0]
            if bucket["faculty_activities"]:
                bucket["dominant_faculty_activity"] = max(bucket["faculty_activities"].items(), key=lambda item: item[1])[0]
            if bucket["context_activities"]:
                bucket["dominant_context"] = max(bucket["context_activities"].items(), key=lambda item: item[1])[0]
        return JSONResponse({"location": location, "hours": hours, "timeline": timeline})
    except Exception as exc:
        logger.error(f"Failed to get classroom activity timeline: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/classroom/activities/summary")
async def get_classroom_activity_summary(
    date: str = None,
    class_name: str = None,
    section_name: str = None,
    authorization: str = Header(None),
):
    _user, error = require_capability_user(authorization, CAPABILITY_ACTIVITIES_VIEW)
    if error:
        return error
    try:
        if not date:
            date = app_now().strftime("%Y-%m-%d")
        start, end = attendance_tracker._day_bounds(date)
        docs = iter_class_activity_docs(start_time=start, end_time=end, class_name=class_name, section_name=section_name)
        student_breakdown = {}
        faculty_breakdown = {}
        context_breakdown = {}
        for doc in docs:
            student_breakdown[doc.get("student_activity_label") or "students_uncertain"] = student_breakdown.get(doc.get("student_activity_label") or "students_uncertain", 0) + 1
            faculty_breakdown[doc.get("faculty_activity_label") or "faculty_uncertain"] = faculty_breakdown.get(doc.get("faculty_activity_label") or "faculty_uncertain", 0) + 1
            context_breakdown[doc.get("context_label") or "uncertain_context"] = context_breakdown.get(doc.get("context_label") or "uncertain_context", 0) + 1
        return JSONResponse(
            {
                "date": date,
                "class_name": class_name,
                "section_name": section_name,
                "total_windows": len(docs),
                "student_activity_breakdown": student_breakdown,
                "faculty_activity_breakdown": faculty_breakdown,
                "context_breakdown": context_breakdown,
            }
        )
    except Exception as exc:
        logger.error(f"Failed to get classroom activity summary: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


# ============ CCTV CAMERA MANAGEMENT ENDPOINTS ============

@app.post("/api/cameras/add")
async def add_cctv_camera(camera_data: dict = Body(...), authorization: str = Header(None)):
    """Add a new CCTV camera to the system
    
    Request body:
    {
        "name": "Classroom A - Door",
        "type": "rtsp",  # rtsp, mjpeg, hls, usb
        "source": "rtsp://192.168.1.100:554/stream1",
        "username": "admin",
        "password": "password",
        "fps": 30,
        "resolution": "1280x720",
        "inference_width": 960,
        "target_fps": 8,
        "recognition_threshold_override": null,
        "enable_emotion": false,
        "enable_activity": false
    }
    """
    try:
        # Verify authentication
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_MANAGE)
        if error:
            return error
        
        name = camera_data.get('name', '').strip()
        requested_camera_type = camera_data.get('type', 'rtsp').lower()
        camera_type = 'LOCAL_WEBCAM' if requested_camera_type == 'local_webcam' else requested_camera_type
        source = camera_data.get('source', '').strip()
        username = camera_data.get('username', '').strip() if camera_data.get('username') else None
        password = camera_data.get('password', '').strip() if camera_data.get('password') else None
        wing = camera_data.get('wing', '').strip() if camera_data.get('wing') else None
        room_number = camera_data.get('room_number', '').strip() if camera_data.get('room_number') else None
        camera_context = camera_data.get('camera_context', '').strip().lower() if camera_data.get('camera_context') else None
        class_name = camera_data.get('class_name', '').strip() if camera_data.get('class_name') else None
        section_name = camera_data.get('section_name', '').strip() if camera_data.get('section_name') else None
        front_zone = camera_data.get('front_zone')
        board_zone = camera_data.get('board_zone')
        student_seating_zone = camera_data.get('student_seating_zone')
        faculty_workstation_zone = camera_data.get('faculty_workstation_zone')
        fps = int(camera_data.get('fps', 30))
        resolution_str = camera_data.get('resolution', '1280x720')
        inference_width = int(camera_data.get('inference_width', 960) or 960)
        target_fps = float(camera_data.get('target_fps', 8) or 8)
        recognition_threshold_override = camera_data.get('recognition_threshold_override')
        min_face_size_identity = camera_data.get('min_face_size_identity')
        min_face_size_emotion = camera_data.get('min_face_size_emotion')
        weak_match_threshold = camera_data.get('weak_match_threshold')
        consensus_frames_required = camera_data.get('consensus_frames_required')
        enable_emotion = camera_data.get('enable_emotion')
        enable_activity = camera_data.get('enable_activity')
        
        if camera_type == "LOCAL_WEBCAM":
            name, source, wing, room_number = apply_local_webcam_defaults(name, source, wing, room_number)

        if not name or (camera_type != "LOCAL_WEBCAM" and not source):
            return JSONResponse({"error": "Camera name and source are required"}, status_code=400)
        
        if camera_type not in ['rtsp', 'mjpeg', 'hls', 'usb', 'LOCAL_WEBCAM']:
            return JSONResponse({"error": "Invalid camera type"}, status_code=400)
        
        # Parse resolution
        try:
            res_parts = resolution_str.split('x')
            resolution = (int(res_parts[0]), int(res_parts[1]))
        except:
            resolution = (1280, 720)
        
        # Add camera via manager
        camera_id = cctv_manager.add_camera(
            name=name,
            source=source,
            camera_type=camera_type,
            username=username,
            password=password,
            fps=fps,
            resolution=resolution,
            inference_width=inference_width,
            target_fps=target_fps,
            recognition_threshold_override=recognition_threshold_override,
            min_face_size_identity=min_face_size_identity,
            min_face_size_emotion=min_face_size_emotion,
            weak_match_threshold=weak_match_threshold,
            consensus_frames_required=consensus_frames_required,
            enable_emotion=enable_emotion,
            enable_activity=enable_activity,
            wing=wing,
            room_number=room_number,
            camera_context=camera_context,
            class_name=class_name,
            section_name=section_name,
            front_zone=front_zone,
            board_zone=board_zone,
            student_seating_zone=student_seating_zone,
            faculty_workstation_zone=faculty_workstation_zone,
        )
        
        if camera_id > 0:
            # Immediately test the camera connection
            logger.info(f"Testing newly added camera {camera_id}: {name}")
            
            def test_new_camera():
                try:
                    url = build_camera_source_url(
                        source=source,
                        camera_type=camera_type,
                        username=username,
                        password=password,
                    )
                    
                    local_device_index = None
                    if camera_type == "LOCAL_WEBCAM":
                        local_device_index = parse_local_webcam_device_index(source)
                    cap = cv2.VideoCapture(local_device_index if camera_type == "LOCAL_WEBCAM" else url)
                    if not cap.isOpened():
                        cctv_manager.update_camera_status(camera_id, "error", "Failed to open stream")
                        logger.warning(f"Camera {camera_id} connection failed: VideoCapture.isOpened()=False")
                        return
                    
                    # Try to read a frame
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret and frame is not None:
                        cctv_manager.update_camera_status(camera_id, "connected")
                        logger.info(f"✓ Camera {camera_id} verified connected")
                    else:
                        cctv_manager.update_camera_status(camera_id, "error", "Could not read frames")
                        logger.warning(f"Camera {camera_id} could not read frames")
                        
                except Exception as e:
                    error_msg = str(e)
                    cctv_manager.update_camera_status(camera_id, "error", error_msg)
                    logger.error(f"Camera {camera_id} test error: {error_msg}")
            
            # Run test in background with timeout
            test_thread = threading.Thread(target=test_new_camera, daemon=True)
            test_thread.start()
            test_thread.join(timeout=15)
            
            return {
                "status": "success",
                "camera_id": camera_id,
                "message": f"Camera '{name}' added successfully. Connection status is being verified..."
            }
        else:
            return JSONResponse({"error": "Failed to add camera. Camera may already exist."}, status_code=500)
            
    except Exception as e:
        logger.error(f"Error adding camera: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/cameras")
async def get_all_cameras(authorization: str = Header(None)):
    """Get list of all configured cameras"""
    try:
        user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_VIEW)
        if error:
            return error
        cameras = cctv_manager.get_all_cameras()
        
        # Format cameras for JSON response - include disabled cameras so they can
        # be reactivated from the admin UI.
        formatted_cameras = []
        for cam in cameras:
            # Get latest status for this camera
            if not cam['enabled']:
                status = 'disabled'
            elif not cam.get('processing_enabled', True):
                status = 'processing-disabled'
            else:
                status = cctv_manager.get_camera_latest_status(cam['id'])
            
            width, height = cam['resolution'] if isinstance(cam['resolution'], tuple) else (1280, 720)
            formatted_cameras.append({
                'id': cam['id'],
                'name': cam['name'],
                'source': cam['source'],
                'type': cam['type'],
                'fps': cam['fps'],
                'resolution': f"{width}x{height}",
                'inference_width': cam.get('inference_width', 960),
                'target_fps': cam.get('target_fps', 8.0),
                'recognition_threshold_override': cam.get('recognition_threshold_override'),
                'min_face_size_identity': cam.get('min_face_size_identity'),
                'min_face_size_emotion': cam.get('min_face_size_emotion'),
                'weak_match_threshold': cam.get('weak_match_threshold'),
                'consensus_frames_required': cam.get('consensus_frames_required'),
                'enable_emotion': cam.get('enable_emotion'),
                'enable_activity': cam.get('enable_activity'),
                'wing': cam.get('wing'),
                'room_number': cam.get('room_number'),
                'camera_context': cam.get('camera_context'),
                'class_name': cam.get('class_name'),
                'section_name': cam.get('section_name'),
                'front_zone': cam.get('front_zone'),
                'board_zone': cam.get('board_zone'),
                'student_seating_zone': cam.get('student_seating_zone'),
                'faculty_workstation_zone': cam.get('faculty_workstation_zone'),
                'username': cam.get('username') if has_capability(user.get("role"), CAPABILITY_CAMERAS_MANAGE) else None,
                'password': cam.get('password') if has_capability(user.get("role"), CAPABILITY_CAMERAS_MANAGE) else None,
                'enabled': cam['enabled'],
                'processing_enabled': cam.get('processing_enabled', True),
                'status': status
            })
        
        return {
            "status": "success",
            "count": len(formatted_cameras),
            "cameras": formatted_cameras,
            "wings": cctv_manager.get_wing_options()
        }
    except Exception as e:
        logger.error(f"Error fetching cameras: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/cameras/{camera_id}")
async def get_camera_details(camera_id: int, authorization: str = Header(None)):
    """Get details of a specific camera"""
    try:
        # Verify authentication
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_VIEW)
        if error:
            return error
        
        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id), None)
        
        if camera:
            return {
                "status": "success",
                "camera": camera
            }
        else:
            return JSONResponse({"error": "Camera not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error fetching camera: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/cameras/{camera_id}")
async def delete_camera(camera_id: int, authorization: str = Header(None)):
    """Permanently delete a camera from the system."""
    try:
        # Verify authentication
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_MANAGE)
        if error:
            return error
        
        # Verify camera exists before deletion
        cameras = cctv_manager.get_all_cameras()
        camera_exists = any(c['id'] == camera_id for c in cameras)
        
        if not camera_exists:
            return JSONResponse({"error": "Camera not found"}, status_code=404)

        # Stop any active recognition before disabling the camera so the UI and
        # worker state stay in sync after deletion.
        try:
            _request_recognition_state(camera_id, False, mode="attendance", requested_by="camera_delete")
        except Exception as stop_error:
            logger.warning(f"Failed to queue stop for camera {camera_id} before delete: {stop_error}")
        
        success = cctv_manager.remove_camera(camera_id)
        if success:
            clear_camera_runtime(camera_id)
            logger.info(f"Camera {camera_id} deleted successfully")
            return {
                "status": "success",
                "message": "Camera deleted successfully"
            }
        else:
            return JSONResponse({"error": "Failed to delete camera"}, status_code=500)
    except Exception as e:
        logger.error(f"Error deleting camera: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/cameras/{camera_id}/enabled")
async def set_camera_enabled(camera_id: int, payload: dict = Body(...), authorization: str = Header(None)):
    """Activate or deactivate a camera without removing it from the system."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_MANAGE)
        if error:
            return error

        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id), None)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)

        enabled = bool(payload.get("enabled"))

        if not enabled:
            try:
                _request_recognition_state(camera_id, False, mode="attendance", requested_by="camera_disable")
            except Exception as stop_error:
                logger.warning(f"Failed to queue stop for camera {camera_id} while disabling: {stop_error}")

        success = cctv_manager.set_camera_enabled(camera_id, enabled)
        if not success:
            return JSONResponse({"error": "Failed to update camera activation state"}, status_code=500)

        return {
            "status": "success",
            "camera_id": camera_id,
            "enabled": enabled,
            "message": f"Camera {'activated' if enabled else 'deactivated'} successfully"
        }
    except Exception as e:
        logger.error(f"Error updating camera activation state: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/cameras/{camera_id}/processing-enabled")
async def set_camera_processing_enabled(camera_id: int, payload: dict = Body(...), authorization: str = Header(None)):
    """Enable or disable a camera for attendance/emotion/activity processing only."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_MANAGE)
        if error:
            return error

        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id), None)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)

        processing_enabled = bool(payload.get("processing_enabled"))

        if not processing_enabled:
            try:
                _request_recognition_state(camera_id, False, mode="attendance", requested_by="camera_processing_disable")
            except Exception as stop_error:
                logger.warning(
                    f"Failed to queue stop for camera {camera_id} while disabling processing: {stop_error}"
                )

        success = cctv_manager.set_camera_processing_enabled(camera_id, processing_enabled)
        if not success:
            return JSONResponse({"error": "Failed to update camera processing state"}, status_code=500)

        return {
            "status": "success",
            "camera_id": camera_id,
            "processing_enabled": processing_enabled,
            "message": (
                "Camera processing enabled successfully"
                if processing_enabled
                else "Camera processing disabled successfully"
            ),
        }
    except Exception as e:
        logger.error(f"Error updating camera processing state: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.put("/api/cameras/{camera_id}")
async def update_camera(camera_id: int, camera_data: dict = Body(...), authorization: str = Header(None)):
    """Update camera details."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_MANAGE)
        if error:
            return error

        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id and c['enabled']), None)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)

        name = camera_data.get('name', '').strip()
        requested_camera_type = camera_data.get('type', 'rtsp').lower()
        camera_type = 'LOCAL_WEBCAM' if requested_camera_type == 'local_webcam' else requested_camera_type
        source = camera_data.get('source', '').strip()
        username = camera_data.get('username', '').strip() if camera_data.get('username') else None
        password = camera_data.get('password', '').strip() if camera_data.get('password') else None
        wing = camera_data.get('wing', '').strip() if camera_data.get('wing') else None
        room_number = camera_data.get('room_number', '').strip() if camera_data.get('room_number') else None
        camera_context = camera_data.get('camera_context', '').strip().lower() if camera_data.get('camera_context') else None
        class_name = camera_data.get('class_name', '').strip() if camera_data.get('class_name') else None
        section_name = camera_data.get('section_name', '').strip() if camera_data.get('section_name') else None
        front_zone = camera_data.get('front_zone')
        board_zone = camera_data.get('board_zone')
        student_seating_zone = camera_data.get('student_seating_zone')
        faculty_workstation_zone = camera_data.get('faculty_workstation_zone')
        fps = int(camera_data.get('fps', 30))
        resolution_str = camera_data.get('resolution', '1280x720')
        inference_width = int(camera_data.get('inference_width', 960) or 960)
        target_fps = float(camera_data.get('target_fps', 8) or 8)
        recognition_threshold_override = camera_data.get('recognition_threshold_override')
        min_face_size_identity = camera_data.get('min_face_size_identity')
        min_face_size_emotion = camera_data.get('min_face_size_emotion')
        weak_match_threshold = camera_data.get('weak_match_threshold')
        consensus_frames_required = camera_data.get('consensus_frames_required')
        enable_emotion = camera_data.get('enable_emotion')
        enable_activity = camera_data.get('enable_activity')

        if camera_type == "LOCAL_WEBCAM":
            name, source, wing, room_number = apply_local_webcam_defaults(name, source, wing, room_number)

        if not name or (camera_type != "LOCAL_WEBCAM" and not source):
            return JSONResponse({"error": "Camera name and source are required"}, status_code=400)

        try:
            res_parts = resolution_str.split('x')
            resolution = (int(res_parts[0]), int(res_parts[1]))
        except Exception:
            resolution = (1280, 720)

        success = cctv_manager.update_camera(
            camera_id=camera_id,
            name=name,
            source=source,
            camera_type=camera_type,
            username=username,
            password=password,
            fps=fps,
            resolution=resolution,
            inference_width=inference_width,
            target_fps=target_fps,
            recognition_threshold_override=recognition_threshold_override,
            min_face_size_identity=min_face_size_identity,
            min_face_size_emotion=min_face_size_emotion,
            weak_match_threshold=weak_match_threshold,
            consensus_frames_required=consensus_frames_required,
            enable_emotion=enable_emotion,
            enable_activity=enable_activity,
            wing=wing,
            room_number=room_number,
            camera_context=camera_context,
            class_name=class_name,
            section_name=section_name,
            front_zone=front_zone,
            board_zone=board_zone,
            student_seating_zone=student_seating_zone,
            faculty_workstation_zone=faculty_workstation_zone,
        )

        if not success:
            return JSONResponse({"error": "Failed to update camera"}, status_code=500)

        return {
            "status": "success",
            "message": f"Camera '{name}' updated successfully."
        }
    except Exception as e:
        logger.error(f"Error updating camera: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/cameras/test")
async def test_camera_connection(test_data: dict = Body(...), authorization: str = Header(None)):
    """Test connection to a camera before adding it
    
    Request body:
    {
        "type": "rtsp|mjpeg|http",
        "source": "rtsp://192.168.1.100:554/stream1 or http://192.168.4.136:25001",
        "username": "admin",
        "password": "password"
    }
    """
    try:
        # Verify authentication
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_MANAGE)
        if error:
            return error
        
        requested_camera_type = test_data.get('type', 'rtsp').lower()
        camera_type = 'LOCAL_WEBCAM' if requested_camera_type == 'local_webcam' else requested_camera_type
        source = test_data.get('source', '').strip()
        username = test_data.get('username', '').strip() if test_data.get('username') else None
        password = test_data.get('password', '').strip() if test_data.get('password') else None
        
        if camera_type == "LOCAL_WEBCAM":
            _name, source, _wing, _room = apply_local_webcam_defaults(None, source, None, None)
            try:
                parse_local_webcam_device_index(source)
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

        if camera_type != "LOCAL_WEBCAM" and not source:
            return JSONResponse({"error": "Camera source is required"}, status_code=400)
        
        logger.info(f"Testing camera connection: type={camera_type}, source={source}, user={username}")
        
        # Build URL with proper credential injection for different camera types
        url = build_camera_source_url(
            source=source,
            camera_type=camera_type,
            username=username,
            password=password,
        )
        if url != source and "://" in url:
            proto, rest = url.split("://", 1)
            logger.info(f"Added credentials to URL: {proto}://***:***@{rest[:40]}...")
        
        # Test with timeout using threading
        frames_read = 0
        test_result = {"connected": False, "frames": 0, "error": None}
        
        def test_camera():
            try:
                logger.info(
                    "Opening camera with cv2.VideoCapture: "
                    f"{f'device_index={parse_local_webcam_device_index(source)}' if camera_type == 'LOCAL_WEBCAM' else url[:60]}"
                )
                local_device_index = None
                if camera_type == "LOCAL_WEBCAM":
                    local_device_index = parse_local_webcam_device_index(source)
                cap = cv2.VideoCapture(local_device_index if camera_type == "LOCAL_WEBCAM" else url)
                
                # Set timeout properties for some types
                if camera_type in ['http', 'mjpeg']:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Check if opened
                if not cap.isOpened():
                    if camera_type == "LOCAL_WEBCAM":
                        test_result["error"] = (
                            "Failed to open the local camera. "
                            f"Check device index {local_device_index}, system camera permission, and whether another app is using the camera."
                        )
                        logger.warning(
                            "VideoCapture.isOpened() returned False for local webcam device index %s",
                            local_device_index,
                        )
                    else:
                        test_result["error"] = f"Failed to open camera. Check URL format and credentials. URL: {url[:80]}"
                        logger.warning(f"VideoCapture.isOpened() returned False for {url[:60]}")
                    return
                
                logger.info("VideoCapture opened successfully, trying to read frames...")
                
                # Try to read a few frames
                for i in range(5):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        test_result["frames"] += 1
                        logger.info(f"Frame {i+1}: OK (shape: {frame.shape})")
                    else:
                        logger.warning(f"Frame {i+1}: Failed to read (ret={ret})")
                        if i == 0:
                            break  # First frame failed, likely auth issue
                
                cap.release()
                
                if test_result["frames"] > 0:
                    test_result["connected"] = True
                    test_result["error"] = None
                    logger.info(f"✓ Camera test successful, read {test_result['frames']} frames")
                else:
                    if camera_type == "LOCAL_WEBCAM":
                        test_result["error"] = (
                            "Local camera opened but no frames were read. "
                            f"Check device index {local_device_index} and whether another app is already using the webcam."
                        )
                        logger.warning(
                            "Could not read any frames from local webcam device index %s",
                            local_device_index,
                        )
                    else:
                        test_result["error"] = "Camera opened but could not read frames. Check credentials, URL path, and camera is streaming."
                        logger.warning(f"Could not read any frames from {url[:60]}")
                    
            except Exception as e:
                test_result["error"] = f"Exception during test: {str(e)}"
                logger.error(f"Test camera error: {str(e)}", exc_info=True)
        
        # Run test with 30 second timeout
        test_thread = threading.Thread(target=test_camera, daemon=True)
        test_thread.start()
        test_thread.join(timeout=30)
        
        if test_thread.is_alive():
            return JSONResponse({
                "error": f"Camera connection timeout (>30s). Camera may be offline or unresponsive. URL: {url[:80]}"
            }, status_code=408)
        
        if test_result["connected"]:
            return {
                "status": "success",
                "connected": True,
                "frames_read": test_result["frames"],
                "message": f"Camera connection successful! Read {test_result['frames']} frames."
            }
        else:
            error_msg = test_result["error"] or "Unknown error"
            logger.error(f"Camera test failed: {error_msg}")
            return JSONResponse({
                "error": error_msg
            }, status_code=400)
            
    except Exception as e:
        logger.error(f"Unexpected error in test_camera_connection: {str(e)}", exc_info=True)
        return JSONResponse({
            "error": f"Unexpected error: {str(e)}"
        }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error testing camera: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/cameras/{camera_id}/status")
async def get_camera_status(camera_id: int, authorization: str = Header(None)):
    """Get and test connection status of a specific camera (real-time test)"""
    try:
        # Verify authentication
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_VIEW)
        if error:
            return error
        
        # Get camera from database
        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id and c['enabled']), None)
        
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)
        
        logger.info(f"Testing camera {camera_id} ({camera['name']})")
        live_status = probe_camera_connection(camera)

        return {
            "status": "success",
            "camera_id": camera_id,
            "camera_name": camera['name'],
            "connection_status": live_status.get("connection_status", "disconnected"),
            "error": live_status.get("error"),
            "last_check": live_status.get("last_check"),
        }
            
    except Exception as e:
        logger.error(f"Error checking camera status: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/dashboard.html")
async def dashboard_page():
    """Serve the attendance dashboard"""
    return FileResponse(os.path.join(frontend_dir, "dashboard.html"))

# ============ CCTV REAL-TIME FACE RECOGNITION ENDPOINTS ============

@app.post("/api/cameras/{camera_id}/recognition/start")
async def start_camera_recognition(camera_id: int, authorization: str = Header(None)):
    """Start real-time face recognition on a specific CCTV camera"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        # Verify camera exists
        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id and c['enabled']), None)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)

        if (camera.get("type") or "").upper() == "LOCAL_WEBCAM":
            result = _start_local_webcam_thread()
        else:
            result = _request_recognition_state(camera_id, True, mode="attendance", requested_by="api")
        
        if result['success']:
            return {"status": "success", "message": result['message']}
        else:
            return JSONResponse({"error": result['message']}, status_code=400)
    
    except Exception as e:
        logger.error(f"Error starting recognition: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/cameras/{camera_id}/recognition/stop")
async def stop_camera_recognition(camera_id: int, authorization: str = Header(None)):
    """Stop real-time face recognition on a specific CCTV camera"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        camera = get_camera_record(camera_id)
        if camera and (camera.get("type") or "").upper() == "LOCAL_WEBCAM":
            result = _stop_local_webcam_thread()
        else:
            result = _request_recognition_state(camera_id, False, mode="attendance", requested_by="api")
        
        if result['success']:
            return {
                "status": "success",
                "message": result['message'],
                "stats": result.get('stats', {})
            }
        else:
            return JSONResponse({"error": result['message']}, status_code=400)
    
    except Exception as e:
        logger.error(f"Error stopping recognition: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/cameras/{camera_id}/recognition/status")
async def get_camera_recognition_status(camera_id: int, authorization: str = Header(None)):
    """Get recognition status for a specific camera"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        camera = get_camera_record(camera_id)
        if camera and (camera.get("type") or "").upper() == "LOCAL_WEBCAM":
            status = {
                "camera_id": camera_id,
                "is_running": bool(_webcam_running),
                "status": "running" if _webcam_running else "stopped",
                "frames_processed": 0,
                "faces_recognized": 0,
                "message": "",
            }
        else:
            status = get_runtime_state(camera_id)
        return {"status": "success", "data": status}
    
    except Exception as e:
        logger.error(f"Error getting recognition status: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/cameras/recognition/status/all")
async def get_all_recognition_status(authorization: str = Header(None)):
    """Get recognition status for all cameras"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        status_list = _get_all_runtime_recognition_status()
        return {
            "status": "success",
            "count": len(status_list),
            "cameras": status_list
        }
    
    except Exception as e:
        logger.error(f"Error getting all recognition status: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cameras/emotion/room-status")
async def get_emotion_room_status(authorization: str = Header(None)):
    """Get live per-room emotion runtime status for all enabled cameras."""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        runtime_map = {item.get("camera_id"): item for item in _get_all_runtime_recognition_status()}
        cameras = [
            camera for camera in cctv_manager.get_all_cameras()
            if camera.get("enabled", True) and camera.get("processing_enabled", True)
        ]
        rooms = []

        for camera in cameras:
            camera_id = camera["id"]
            runtime = runtime_map.get(camera_id, {})
            detections = (
                dict(_webcam_last_detections or {})
                if (camera.get("type") or "").upper() == "LOCAL_WEBCAM"
                else get_runtime_latest_detections(camera_id)
            ) or {}
            known_faces = detections.get("known_faces", []) or []
            unknown_faces = detections.get("unknown_faces", []) or []
            all_faces = list(known_faces) + list(unknown_faces)

            emotion_counts = {}
            for face in all_faces:
                label = (
                    face.get("smoothed_emotion")
                    if face.get("smoothed_emotion") and face.get("smoothed_emotion") != "LowSignal"
                    else face.get("emotion") or face.get("raw_emotion")
                )
                if not label:
                    continue
                emotion_counts[label] = emotion_counts.get(label, 0) + 1

            dominant_emotion = None
            if emotion_counts:
                dominant_emotion = max(emotion_counts.items(), key=lambda item: item[1])[0]

            rooms.append({
                "camera_id": camera_id,
                "camera_name": camera.get("name"),
                "camera_type": camera.get("type"),
                "is_running": bool(runtime.get("is_running", False)),
                "status": runtime.get("status", "stopped"),
                "message": runtime.get("message", ""),
                "frames_processed": runtime.get("frames_processed", 0),
                "faces_recognized": runtime.get("faces_recognized", 0),
                "fps": runtime.get("fps", 0),
                "updated_at": detections.get("updated_at") or runtime.get("updated_at"),
                "total_faces": len(all_faces),
                "known_faces_count": len(known_faces),
                "unknown_faces_count": len(unknown_faces),
                "dominant_emotion": dominant_emotion,
                "emotion_counts": emotion_counts,
                "last_emotion_detection_at": runtime.get("last_emotion_detection_at"),
                "emotion_backend": runtime.get("emotion_backend"),
                "emotion_model_loaded": runtime.get("emotion_model_loaded"),
                "emotion_detection_error": runtime.get("emotion_detection_error"),
            })

        return {
            "status": "success",
            "date": app_now().strftime("%Y-%m-%d"),
            "rooms": rooms,
        }
    except Exception as e:
        logger.error(f"Error getting emotion room status: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/cameras/recognition/logs")
async def get_recognition_logs(camera_id: int = None, limit: int = 100, authorization: str = Header(None)):
    """Get recognition logs (attendance detections from cameras)"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        logs = cctv_recognition_engine.get_recognition_logs(camera_id, limit)
        return {
            "status": "success",
            "count": len(logs),
            "logs": logs
        }
    
    except Exception as e:
        logger.error(f"Error getting recognition logs: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/recognition/review")
async def get_recognition_review_records(
    camera_id: int = None,
    review_status: str = None,
    predicted_profile_id: int = None,
    limit: int = 200,
    sort: str = "top_score_desc",
    authorization: str = Header(None),
):
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_RECOGNITION_VIEW)
        if error:
            return error

        records = cctv_recognition_engine.list_recognition_review_records(
            camera_id=camera_id,
            review_status=review_status,
            predicted_profile_id=predicted_profile_id,
            limit=limit,
            sort=sort,
        )
        return {"status": "success", "count": len(records), "records": records}
    except Exception as e:
        logger.error(f"Error getting recognition review records: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/recognition/review/{record_id}/verdict")
async def update_recognition_review_verdict(
    record_id: int,
    payload: dict = Body(...),
    authorization: str = Header(None),
):
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_RECOGNITION_MANAGE)
        if error:
            return error

        review_status = str(payload.get("review_status") or "").strip().lower()
        review_note = str(payload.get("note") or payload.get("review_note") or "").strip()
        record = cctv_recognition_engine.update_recognition_review_verdict(
            record_id,
            review_status=review_status,
            note=review_note,
        )
        if not record:
            return JSONResponse({"error": "Recognition review record not found or invalid verdict."}, status_code=404)
        return {"status": "success", "record": record}
    except Exception as e:
        logger.error(f"Error updating recognition review verdict: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/recognition/review/export.csv")
async def export_recognition_review_csv(
    camera_id: int = None,
    review_status: str = None,
    predicted_profile_id: int = None,
    limit: int = 5000,
    sort: str = "top_score_desc",
    authorization: str = Header(None),
):
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_RECOGNITION_VIEW)
        if error:
            return error

        csv_payload = cctv_recognition_engine.export_recognition_review_csv(
            camera_id=camera_id,
            review_status=review_status,
            predicted_profile_id=predicted_profile_id,
            limit=limit,
            sort=sort,
        )
        filename = f"recognition-review-{app_now().strftime('%Y%m%d-%H%M%S')}.csv"
        return StreamingResponse(
            iter([csv_payload]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Error exporting recognition review csv: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/recognition/review/reset")
async def reset_recognition_review_records(payload: dict = Body(default={}), authorization: str = Header(None)):
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_RECOGNITION_MANAGE)
        if error:
            return error

        camera_id = payload.get("camera_id")
        deleted_count = cctv_recognition_engine.reset_recognition_review_records(camera_id=camera_id)
        return {"status": "success", "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"Error resetting recognition review records: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cameras/{camera_id}/detections")
async def get_current_detections(camera_id: int, authorization: str = Header(None)):
    """Get current face detections (known + unknown) for a camera"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        camera = get_camera_record(camera_id)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)
        
        if (camera.get("type") or "").upper() == "LOCAL_WEBCAM":
            detections = dict(_webcam_last_detections or {
                "updated_at": None,
                "known_faces": [],
                "unknown_faces": [],
                "total_faces": 0,
            })
        else:
            detections = get_runtime_latest_detections(camera_id)

        known_faces = detections.get('known_faces', [])
        unknown_faces = detections.get('unknown_faces', [])
        all_faces = list(known_faces) + list(unknown_faces)
        
        return {
            "status": "success",
            "camera_id": camera_id,
            "camera_name": camera['name'],
            "data": {
                "updated_at": detections.get('updated_at'),
                "total_faces": detections.get('total_faces', 0),
                "known_faces": known_faces,
                "unknown_faces": unknown_faces,
                "all_faces": all_faces,
                "unknown_faces_count": len(unknown_faces),
                "known_faces_count": len(known_faces),
                "class_activity": detections.get('class_activity'),
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting detections: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cameras/{camera_id}/face-debug")
async def get_camera_face_debug(camera_id: int, authorization: str = Header(None)):
    """Capture a single frame and return raw face boxes plus cropped face images."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_CAMERAS_VIEW)
        if error:
            return error

        camera = get_camera_record(camera_id)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)

        if (camera.get("type") or "").upper() == "LOCAL_WEBCAM":
            with _webcam_lock:
                frame = _webcam_latest_frame.copy() if _webcam_latest_frame is not None else None
            camera_name = camera.get("name") or "Local Webcam"
        else:
            cap, resolved_camera_name = cctv_recognition_engine._get_camera_stream(camera_id, max_retries=3)
            try:
                if cap is None or not cap.isOpened():
                    return JSONResponse({"error": "Unable to open camera stream for face debug."}, status_code=503)
                success, frame = cap.read()
                if not success or frame is None:
                    return JSONResponse({"error": "Unable to read a frame from the camera."}, status_code=503)
            finally:
                if cap is not None:
                    cap.release()
            camera_name = resolved_camera_name or camera.get("name") or f"Camera {camera_id}"

        if frame is None:
            return JSONResponse({"error": "No frame available for face debug."}, status_code=503)

        import cv2

        preview_width = 960
        preview_height = 540
        preview_frame = cv2.resize(frame, (preview_width, preview_height))
        prepared_frame = cctv_recognition_engine._prepare_frame_for_inference(preview_frame)
        face_candidates = cctv_recognition_engine.ai_engine.detect_faces_with_landmarks(prepared_frame) or []

        face_debug = []
        for index, face_data in enumerate(face_candidates):
            bbox = list(face_data.get("bbox") or [])
            if len(bbox) < 4:
                continue

            face_crop = cctv_recognition_engine._crop_face(prepared_frame, bbox)
            encoded_crop = _encode_debug_image(face_crop) if face_crop is not None else None
            x, y, w, h = [int(value) for value in bbox[:4]]
            face_debug.append(
                {
                    "id": f"{camera_id}-{index + 1}",
                    "bbox": [x, y, w, h],
                    "label": f"Face {index + 1}",
                    "size": {"width": w, "height": h},
                    "crop_base64": encoded_crop,
                }
            )

        return {
            "status": "success",
            "camera_id": camera_id,
            "camera_name": camera_name,
            "frame_size": {"width": preview_width, "height": preview_height},
            "face_count": len(face_debug),
            "faces": face_debug,
        }
    except Exception as e:
        logger.error(f"Error getting camera face debug: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/cameras/{camera_id}/emotion/start")
async def start_emotion_detection(camera_id: int):
    """Start emotion detection on a camera - NO AUTHENTICATION REQUIRED for convenience"""
    try:
        # Verify camera exists and is enabled
        cameras = cctv_manager.get_all_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id and c['enabled']), None)
        if not camera:
            return JSONResponse({"error": "Camera not found or disabled"}, status_code=404)
        
        # Start recognition (which includes emotion detection)
        result = _request_recognition_state(camera_id, True, mode="emotion", requested_by="emotion_api")
        
        if result['success']:
            logger.info(f"✓ Emotion detection started for camera {camera_id} ({camera['name']})")
            return {
                "status": "success",
                "message": f"Emotion detection active for {camera['name']}",
                "camera_id": camera_id,
                "camera_name": camera['name']
            }
        else:
            return JSONResponse({
                "error": result['message'],
                "camera_id": camera_id
            }, status_code=400)
    
    except Exception as e:
        logger.error(f"Error starting emotion detection: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/cameras/emotion/start-all")
async def start_all_emotion_detection():
    """Start emotion detection on all enabled non-local cameras."""
    try:
        cameras = [
            camera for camera in cctv_manager.get_all_cameras()
            if (
                camera.get("enabled")
                and camera.get("processing_enabled", True)
                and (camera.get("type") or "").upper() != "LOCAL_WEBCAM"
            )
        ]
        if not cameras:
            return JSONResponse({"error": "No enabled CCTV cameras found"}, status_code=404)

        started = []
        failed = []
        for camera in cameras:
            result = _request_recognition_state(camera["id"], True, mode="emotion", requested_by="emotion_api_all")
            if result.get("success"):
                started.append({
                    "camera_id": camera["id"],
                    "camera_name": camera["name"],
                    "message": result.get("message"),
                })
            else:
                failed.append({
                    "camera_id": camera["id"],
                    "camera_name": camera["name"],
                    "error": result.get("message") or "Failed to start emotion detection",
                })

        return {
            "status": "success" if started else "partial",
            "started_count": len(started),
            "failed_count": len(failed),
            "started": started,
            "failed": failed,
        }
    except Exception as e:
        logger.error(f"Error starting emotion detection for all cameras: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/cameras/emotion/stop-all")
async def stop_all_emotion_detection():
    """Stop emotion detection on all enabled non-local cameras."""
    try:
        cameras = [
            camera for camera in cctv_manager.get_all_cameras()
            if (camera.get("type") or "").upper() != "LOCAL_WEBCAM"
        ]
        stopped = []
        failed = []
        for camera in cameras:
            result = _request_recognition_state(camera["id"], False, mode="emotion", requested_by="emotion_api_all")
            if result.get("success"):
                stopped.append({
                    "camera_id": camera["id"],
                    "camera_name": camera["name"],
                    "message": result.get("message"),
                })
            else:
                failed.append({
                    "camera_id": camera["id"],
                    "camera_name": camera["name"],
                    "error": result.get("message") or "Failed to stop emotion detection",
                })

        return {
            "status": "success" if stopped else "partial",
            "stopped_count": len(stopped),
            "failed_count": len(failed),
            "stopped": stopped,
            "failed": failed,
        }
    except Exception as e:
        logger.error(f"Error stopping emotion detection for all cameras: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/browser-camera/analyze")
async def analyze_browser_camera_frame(
    frame: UploadFile = File(...),
    device_label: str = Form(None),
    camera_id: str = Form(None),
    camera_name: str = Form(None),
    session_id: str = Form(None),
    authorization: str = Header(None),
):
    """Analyze a frame captured in the browser on a remote client machine."""
    try:
        _user, error = require_capability_user(authorization, CAPABILITY_EMOTIONS_VIEW)
        if error:
            return error

        payload = await frame.read()
        if not payload:
            return JSONResponse({"error": "Captured frame is empty"}, status_code=400)

        np_buffer = np.frombuffer(payload, dtype=np.uint8)
        image = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
        if image is None:
            return JSONResponse({"error": "Unable to decode captured frame"}, status_code=400)

        _ensure_browser_emotion_pipeline()
        prepared_image = _prepare_browser_analysis_frame(image)

        session_token = (session_id or "default").strip() or "default"
        scoped_camera_id = (camera_id or "").strip()
        scoped_camera_name = (camera_name or "").strip()
        browser_camera_id = (
            f"browser_camera:{scoped_camera_id}:{session_token}"
            if scoped_camera_id
            else f"browser_camera:{session_token}"
        )
        raw_faces, raw_face_source = _normalize_browser_face_candidates(prepared_image)
        center_fallback_used = False
        if not raw_faces:
            raw_faces = [_center_browser_face_candidate(prepared_image)]
            raw_face_source = "center_person_fallback"
            center_fallback_used = True

        detections = cctv_recognition_engine._process_frame(
            prepared_image,
            browser_camera_id,
            runtime_config={
                "camera_name": scoped_camera_name or device_label or browser_camera_id,
                "enable_emotion": True,
                # Keep unknown visible faces in the browser analysis flow even when
                # attendance-style unknown tracking is disabled globally.
                "enable_activity": True,
            },
        ) or []

        if not detections:
            fallback_unknown_faces = []

            for index, face_data in enumerate(raw_faces):
                face_crop = cctv_recognition_engine._crop_face(prepared_image, face_data.get("bbox"))
                if face_crop is None:
                    continue
                try:
                    fallback_unknown_faces.append(
                        _build_browser_unknown_detection(
                            face_data=face_data,
                            face_crop=face_crop,
                            browser_camera_id=browser_camera_id,
                            index=index,
                        )
                    )
                except Exception as exc:
                    logger.debug(f"Browser fallback emotion detection failed for face {index}: {exc}")

            detections = fallback_unknown_faces

        known_faces = [item for item in detections if item.get("profile_id") is not None]
        unknown_faces = [item for item in detections if item.get("profile_id") is None]
        summary = _build_browser_frame_emotion_summary(detections)
        emotion_backend = getattr(getattr(cctv_recognition_engine, "emotion_pipeline", None), "backend", None)
        emotion_processed_count = sum(
            1 for item in detections
            if item.get("emotion_available")
            or float(item.get("raw_confidence") or 0.0) > 0.0
            or float(item.get("emotion_confidence") or 0.0) > 0.0
        )
        fallback_emotion_count = sum(1 for item in detections if item.get("fallback_backend_used"))
        low_signal_count = sum(1 for item in detections if item.get("low_signal_state"))
        unavailable_reasons = sorted(
            {
                str(item.get("emotion_unavailable_reason")).strip()
                for item in detections
                if item.get("emotion_unavailable_reason")
            }
        )

        logger.info(
            "Browser camera frame analyzed: session=%s device=%s total=%s known=%s unknown=%s",
            session_token,
            scoped_camera_name or device_label or "Browser camera",
            len(detections),
            len(known_faces),
            len(unknown_faces),
        )

        return {
            "status": "success",
            "session_id": session_token,
            "device_label": device_label or "Browser camera",
            "camera_id": scoped_camera_id or None,
            "camera_name": scoped_camera_name or None,
            "data": {
                "updated_at": app_now().isoformat(),
                "total_faces": len(detections),
                "all_faces": [
                    _serialize_browser_detection(item)
                    for item in detections
                ],
                "known_faces": [_serialize_browser_detection(item) for item in known_faces],
                "known_faces_count": len(known_faces),
                "unknown_faces": [_serialize_browser_detection(item) for item in unknown_faces],
                "unknown_faces_count": len(unknown_faces),
                "room_emotion": summary,
                "debug": {
                    "frame_width": int(image.shape[1]),
                    "frame_height": int(image.shape[0]),
                    "prepared_frame_width": int(prepared_image.shape[1]),
                    "prepared_frame_height": int(prepared_image.shape[0]),
                    "payload_bytes": len(payload),
                    "raw_face_source": raw_face_source,
                    "center_person_fallback_used": center_fallback_used,
                    "server_emotion_backend": getattr(emotion_backend, "name", None),
                    "server_emotion_model": getattr(emotion_backend, "model_name", None),
                    "server_emotion_version": getattr(emotion_backend, "model_version", None),
                    "server_emotion_model_loaded": bool(getattr(emotion_backend, "model_loaded", False)),
                    "server_emotion_last_error": getattr(emotion_backend, "last_error", None),
                    "raw_face_count": len(raw_faces),
                    "pipeline_detection_count": len(detections),
                    "known_face_count": len(known_faces),
                    "unknown_face_count": len(unknown_faces),
                    "emotion_processed_count": emotion_processed_count,
                    "fallback_emotion_count": fallback_emotion_count,
                    "low_signal_count": low_signal_count,
                    "emotion_unavailable_reasons": unavailable_reasons,
                    "using_fallback_unknown_face_path": not bool(known_faces or unknown_faces) and bool(raw_faces),
                    "server_last_emotion_error": cctv_recognition_engine.emotion_detection_error.get(browser_camera_id),
                    "server_last_emotion_detection_at": cctv_recognition_engine.last_emotion_detection_at.get(browser_camera_id),
                },
            }
        }
    except Exception as e:
        logger.error(f"Error analyzing browser camera frame: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cameras/{camera_id}/snapshots")
async def get_unknown_face_snapshots(camera_id: int, limit: int = 50, authorization: str = Header(None)):
    """Get list of unknown face snapshots for a camera"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        camera = get_camera_record(camera_id)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)
        
        snapshots = cctv_recognition_engine.get_unknown_face_snapshots(camera_id, limit)
        
        return {
            "status": "success",
            "camera_id": camera_id,
            "camera_name": camera['name'],
            "count": len(snapshots),
            "snapshots": snapshots
        }
    
    except Exception as e:
        logger.error(f"Error getting snapshots: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cameras/{camera_id}/snapshots/{filename}")
async def get_snapshot_image(camera_id: int, filename: str, authorization: str = Header(None)):
    """Get a specific unknown face snapshot image (base64 encoded)"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        camera = get_camera_record(camera_id)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)
        
        image_data = cctv_recognition_engine.get_snapshot_image(camera_id, filename)
        
        if not image_data:
            return JSONResponse({"error": "Snapshot not found"}, status_code=404)
        
        return {
            "status": "success",
            "filename": filename,
            "image_base64": image_data
        }
    
    except Exception as e:
        logger.error(f"Error getting snapshot image: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/profiles/{profile_id}/re-register")
async def re_register_profile(
    profile_id: int,
    image_straight: UploadFile = File(...),
    image_left: UploadFile = File(...),
    image_right: UploadFile = File(...),
    image_top: UploadFile = File(...),
    image_down: UploadFile = File(...),
    authorization: str = Header(None),
):
    """
    Re-register a profile with a new face image.
    This updates the profile's embedding to match the new face.
    Useful when someone's appearance has changed (lighting, angle, etc.)
    """
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        # Check if profile exists
        profile = profile_db.get_profile(profile_id)
        if not profile:
            return JSONResponse({"error": "Profile not found"}, status_code=404)
        
        upload_map = {
            "straight": image_straight,
            "left": image_left,
            "right": image_right,
            "top": image_top,
            "down": image_down,
        }
        view_embeddings, view_errors = await extract_multi_view_embeddings(upload_map)
        if view_errors:
            return JSONResponse(
                {
                    "error": "All five face views are required and must contain a usable face.",
                    "view_errors": view_errors,
                },
                status_code=400,
            )

        embedding = view_embeddings["straight"]["embedding"]

        success = profile_db.update_profile_view_embeddings(profile_id, embedding, view_embeddings)
        
        if not success:
            return JSONResponse({"error": "Failed to update profile"}, status_code=500)
        
        engine.register_face_views_from_arrays(profile_id, profile["name"], view_embeddings, embedding)
        
        logger.warning(f"✓✓✓ Profile re-registered: {profile['name']} (ID: {profile_id})")
        
        return {
            "status": "success",
            "profile_id": profile_id,
            "name": profile['name'],
            "enrollment_views": list(REQUIRED_FACE_VIEWS.keys()),
            "message": f"Profile {profile['name']} re-registered successfully with new multi-view face set"
        }
    
    except Exception as e:
        logger.error(f"Re-registration error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cameras/{camera_id}/unknown-faces-persistent")
async def get_persistent_unknown_faces(camera_id: int, authorization: str = Header(None)):
    """Get persistent unknown faces detected on a camera (tracked across frames)"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        camera = get_camera_record(camera_id)
        if not camera:
            return JSONResponse({"error": "Camera not found"}, status_code=404)
        
        # Get unknown faces from DB
        unknown_faces = profile_db.get_unknown_faces(camera_id, hours=24)
        
        return {
            "status": "success",
            "camera_id": camera_id,
            "camera_name": camera['name'],
            "total_unknown": len(unknown_faces),
            "unknown_faces": unknown_faces
        }
    
    except Exception as e:
        logger.error(f"Error getting persistent unknown faces: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/unknown-faces/{unknown_face_id}")
async def delete_unknown_face(unknown_face_id: int, authorization: str = Header(None)):
    """Remove an unknown face entry from persistent tracking"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        success = profile_db.delete_unknown_face(unknown_face_id)
        
        if not success:
            return JSONResponse({"error": "Failed to delete unknown face"}, status_code=500)
        
        return {
            "status": "success",
            "message": "Unknown face entry deleted"
        }
    
    except Exception as e:
        logger.error(f"Error deleting unknown face: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/unknown-faces/{unknown_face_id}/assign")
async def assign_unknown_face_to_profile(unknown_face_id: int, profile_id: int = Form(...), authorization: str = Header(None)):
    """Assign an unknown face to a profile (mark as recognized)"""
    try:
        if not authorization or not auth_manager.verify_token(authorization.split(" ")[-1]):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
        # Verify profile exists
        profile = profile_db.get_profile(profile_id)
        if not profile:
            return JSONResponse({"error": "Profile not found"}, status_code=404)
        
        # Update unknown face with profile_id
        success = profile_db.update_unknown_face_detection(unknown_face_id, profile_id=profile_id)
        
        if not success:
            return JSONResponse({"error": "Failed to assign unknown face"}, status_code=500)
        
        logger.info(f"✓ Unknown face {unknown_face_id} assigned to {profile['name']}")
        
        return {
            "status": "success",
            "unknown_face_id": unknown_face_id,
            "profile_id": profile_id,
            "profile_name": profile['name'],
            "message": f"Unknown face assigned to {profile['name']}"
        }
    
    except Exception as e:
        logger.error(f"Error assigning unknown face: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============ SNAPSHOT SERVING ENDPOINT ============

@app.get("/api/snapshots/{camera_id}/{filename}")
async def get_snapshot(camera_id: int, filename: str):
    """
    Serve a captured face snapshot for validation.
    
    Args:
        camera_id: Camera ID
        filename: Snapshot filename (e.g., 'recognized_John_Doe_20260402_100733.jpg')
    
    Returns:
        JPEG image file
    """
    try:
        logger.info(f"[SNAPSHOT] Requested: camera_id={camera_id}, filename='{filename}'")
        # Validate filename to prevent path traversal attacks
        if ".." in filename or "/" in filename or "\\" in filename:
            return JSONResponse({"error": "Invalid filename"}, status_code=400)
        
        # Construct path to snapshot
        snapshot_dir = os.path.join(os.path.dirname(__file__), 'face_snapshots', f'camera_{camera_id}')
        snapshot_path = os.path.join(snapshot_dir, filename)
        
        # Verify the path is within the snapshot directory (security check)
        if not os.path.abspath(snapshot_path).startswith(os.path.abspath(snapshot_dir)):
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        
        # Check if file exists
        if not os.path.exists(snapshot_path):
            return JSONResponse({"error": "Snapshot not found"}, status_code=404)
        
        # Verify it's a valid image file
        if not snapshot_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            return JSONResponse({"error": "Invalid file type"}, status_code=400)

        try:
            with open(snapshot_path, 'rb') as snapshot_file:
                if not snapshot_file.read(16):
                    return JSONResponse({"error": "Snapshot is empty"}, status_code=404)
        except Exception:
            return JSONResponse({"error": "Snapshot is unreadable"}, status_code=404)
        
        # Serve the file with appropriate MIME type
        media_type = "image/jpeg" if snapshot_path.lower().endswith(('jpg', 'jpeg')) else "image/png"
        return FileResponse(snapshot_path, media_type=media_type)
        
    except Exception as e:
        logger.error(f"Error serving snapshot: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============ CCTV VIDEO STREAMING ENDPOINTS ============

def generate_cctv_stream(camera_id, roi_mode=None):
    """Generate a lightweight MJPEG preview stream for connectivity checks."""
    try:
        import cv2

        preview_resolution = (960, 540)
        jpeg_quality = 72

        def yield_status_frame(title, detail="", frames=30):
            for _ in range(frames):
                frame = np.ones((480, 640, 3), dtype=np.uint8) * 50
                cv2.putText(frame, title, (20, 220),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
                if detail:
                    cv2.putText(frame, detail[:70], (20, 280),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 255), 1)
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        row = get_camera_stream_row(camera_id, enabled_only=True)
        
        if not row:
            logger.error(f"Camera {camera_id} not found or disabled")
            for frame_data in yield_status_frame(f"Camera {camera_id} Not Available"):
                yield frame_data
            return
        
        camera_id, camera_name, source, camera_type, username, password = row
        
        # Handle local webcam specially - use the /video_feed stream
        if camera_type == 'LOCAL_WEBCAM':
            logger.info(f"Streaming local webcam (camera {camera_id})")
            # Forward to the local webcam stream generator
            for frame_data in generate_video_stream():
                yield frame_data
            return
        
        logger.info(f"Opening CCTV stream for camera {camera_name} (ID: {camera_id}) from {source}")

        cap, resolved_camera_name = cctv_recognition_engine._get_camera_stream(camera_id, max_retries=3)
        if resolved_camera_name:
            camera_name = resolved_camera_name

        if cap is None or not cap.isOpened():
            cctv_manager.update_camera_status(camera_id, "error", "Failed to open stream")
            logger.error(f"Failed to open camera {camera_name} after timeout-safe retries. Attempting periodic reconnection...")
            retry_count = 0
            max_reconnection_attempts = 300  # Try for 5 minutes (300 * 1s)
            
            while retry_count < max_reconnection_attempts:
                for frame_data in yield_status_frame(
                    f"Failed to Connect: {camera_name}",
                    f"Attempting reconnect... ({retry_count + 1}/300)",
                    frames=1
                ):
                    yield frame_data
                
                # Try to reconnect every 5 frames (every ~1 second)
                if retry_count % 5 == 0:
                    try:
                        cap, resolved_camera_name = cctv_recognition_engine._get_camera_stream(camera_id, max_retries=1)
                        if cap is not None and cap.isOpened():
                            if resolved_camera_name:
                                camera_name = resolved_camera_name
                            cctv_manager.update_camera_status(camera_id, "connected")
                            logger.info(f"✓ CCTV stream reconnected for {camera_name}")
                            break
                    except Exception:
                        cap = None
                
                retry_count += 1
            
            if cap is None or not cap.isOpened():
                logger.error(f"Failed to reconnect to {camera_name} after 5 minutes. Stream unavailable.")
                return

        cctv_manager.update_camera_status(camera_id, "connected")
        
        frame_count = 0
        error_count = 0
        max_errors = 15
        try:
            while True:
                success, frame = cap.read()
                frame_count += 1
                
                if not success or frame is None:
                    error_count += 1
                    if error_count > max_errors:
                        logger.warning(f"Too many frame read errors for {camera_name}, reconnecting...")
                        cap.release()
                        
                        # Try to reconnect
                        cap, resolved_camera_name = cctv_recognition_engine._get_camera_stream(camera_id, max_retries=1)
                        if cap is not None and cap.isOpened():
                            if resolved_camera_name:
                                camera_name = resolved_camera_name
                            error_count = 0
                            frame_count += 1
                            cctv_manager.update_camera_status(camera_id, "connected")
                            logger.info(f"Reconnected to {camera_name}")
                        else:
                            cctv_manager.update_camera_status(camera_id, "error", "Reconnection failed")
                            logger.error(f"Reconnection failed for {camera_name}")
                            break
                    continue
                
                error_count = 0
                
                if roi_mode == "emotion":
                    try:
                        if isinstance(camera_id, int):
                            runtime_config = cctv_recognition_engine._get_camera_runtime_config(camera_id)
                        else:
                            runtime_config = {}
                        cropped_frame, _ = cctv_recognition_engine._select_inference_region(frame, runtime_config)
                        if cropped_frame is not None and getattr(cropped_frame, "size", 0):
                            frame = cropped_frame
                    except Exception as exc:
                        logger.debug(f"Preview ROI selection failed for camera {camera_id}: {exc}")

                # Resize once for preview to keep MJPEG throughput high.
                frame_display = cv2.resize(frame, preview_resolution)
                annotated_frame = frame_display
                
                # Add camera name and timestamp
                cv2.putText(annotated_frame, camera_name, (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(annotated_frame, f"Frame: {frame_count}", (10, 470),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
                
                # Encode frame
                ret, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
        except Exception as e:
            logger.error(f"Error streaming CCTV {camera_name}: {e}")
        
        finally:
            if cap:
                cap.release()
            cctv_manager.update_camera_status(camera_id, "disconnected")
            logger.info(f"CCTV stream closed for {camera_name}")
    
    except Exception as e:
        logger.error(f"Error in CCTV streaming: {e}")


@app.get("/api/cameras/{camera_id}/stream")
async def stream_cctv_camera(camera_id: int, roi: str = None):
    """Stream MJPEG video from CCTV camera"""
    roi_mode = (roi or "").strip().lower() or None
    return StreamingResponse(
        generate_cctv_stream(camera_id, roi_mode=roi_mode),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/camera-stream.html")
async def camera_stream_page():
    """Redirect legacy camera stream page to the React workspace."""
    return RedirectResponse(url="/camera-stream", status_code=307)


@app.get("/camera-test.html")
async def camera_test_page():
    """Redirect legacy camera test page to camera settings."""
    return RedirectResponse(url="/cameras", status_code=307)


@app.get("/tools.html")
async def tools_page():
    """Redirect legacy tools page to the admin workspace."""
    return RedirectResponse(url="/admin", status_code=307)


@app.get("/emotion-analytics.html")
async def emotion_analytics_page():
    """Redirect legacy emotion analytics page to the reports workspace."""
    return RedirectResponse(url="/admin#reports", status_code=307)


@app.get("/face-validation-dashboard.html")
async def face_validation_dashboard_page():
    """Redirect legacy face validation dashboard to the React workspace."""
    return RedirectResponse(url="/validation", status_code=307)


@app.get("/classroom-emotions.html")
async def classroom_emotions_page():
    """Redirect legacy classroom emotions page to the reports workspace."""
    return RedirectResponse(url="/admin#reports", status_code=307)


if os.path.exists(react_assets_dir):
    app.mount("/assets", StaticFiles(directory=react_assets_dir), name="react-assets")
    logger.info(f"✓ React assets mounted from {react_assets_dir}")
else:
    logger.warning(f"⚠️ React assets directory not found at {react_assets_dir}")


@app.get("/{full_path:path}")
async def react_frontend_fallback(full_path: str):
    """Serve the React SPA for any unmatched non-API route."""
    normalized_path = full_path.lstrip("/")

    if not normalized_path:
        return serve_react_app()

    if normalized_path.startswith("api/"):
        return JSONResponse({"error": "Not found"}, status_code=404)

    candidate_path = os.path.join(react_dist_dir, normalized_path)
    if "." in normalized_path and os.path.exists(candidate_path):
        return FileResponse(candidate_path)

    return serve_react_app()

if __name__ == "__main__":
    logger.info("[INFO] Starting ChronoSense Web Server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
