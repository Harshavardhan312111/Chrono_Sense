from typing import Dict, List

try:
    from mongo_store import mongo_store
except ImportError:
    from backend.mongo_store import mongo_store


ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_PRINCIPAL = "principal"
ROLE_DIRECTOR = "director"
ROLE_CLASS_TEACHER = "class_teacher"

ALL_ROLES = [
    ROLE_CLASS_TEACHER,
    ROLE_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_ADMIN,
    ROLE_DIRECTOR,
]

ROLE_LABELS = {
    ROLE_ADMIN: "Administrator",
    ROLE_MANAGER: "Manager",
    ROLE_PRINCIPAL: "Principal",
    ROLE_DIRECTOR: "Director",
    ROLE_CLASS_TEACHER: "Class Teacher",
}

CAPABILITY_OVERVIEW_VIEW = "overview:view"
CAPABILITY_ATTENDANCE_VIEW = "attendance:view"
CAPABILITY_ATTENDANCE_MANAGE = "attendance:manage"
CAPABILITY_ATTENDANCE_EXPORT = "attendance:export"
CAPABILITY_PEOPLE_VIEW = "people:view"
CAPABILITY_PEOPLE_MANAGE = "people:manage"
CAPABILITY_CAMERAS_VIEW = "cameras:view"
CAPABILITY_CAMERAS_MANAGE = "cameras:manage"
CAPABILITY_RECOGNITION_VIEW = "recognition:view"
CAPABILITY_RECOGNITION_MANAGE = "recognition:manage"
CAPABILITY_ACTIVITIES_VIEW = "activities:view"
CAPABILITY_EMOTIONS_VIEW = "emotions:view"
CAPABILITY_ANALYTICS_VIEW = "analytics:view"
CAPABILITY_SYSTEM_ADMIN = "system:admin"

ROLE_CAPABILITIES = {
    ROLE_ADMIN: {
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_ATTENDANCE_MANAGE,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_PEOPLE_VIEW,
        CAPABILITY_PEOPLE_MANAGE,
        CAPABILITY_CAMERAS_VIEW,
        CAPABILITY_CAMERAS_MANAGE,
        CAPABILITY_RECOGNITION_VIEW,
        CAPABILITY_RECOGNITION_MANAGE,
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
        CAPABILITY_SYSTEM_ADMIN,
    },
    ROLE_MANAGER: {
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_PEOPLE_VIEW,
        CAPABILITY_PEOPLE_MANAGE,
        CAPABILITY_CAMERAS_VIEW,
        CAPABILITY_CAMERAS_MANAGE,
        CAPABILITY_RECOGNITION_VIEW,
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
    },
    ROLE_PRINCIPAL: {
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_PEOPLE_VIEW,
        CAPABILITY_CAMERAS_VIEW,
        CAPABILITY_RECOGNITION_VIEW,
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
    },
    ROLE_DIRECTOR: {
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
    },
    ROLE_CLASS_TEACHER: {
        CAPABILITY_OVERVIEW_VIEW,
        CAPABILITY_ATTENDANCE_VIEW,
        CAPABILITY_ATTENDANCE_EXPORT,
        CAPABILITY_PEOPLE_VIEW,
        CAPABILITY_ACTIVITIES_VIEW,
        CAPABILITY_EMOTIONS_VIEW,
        CAPABILITY_ANALYTICS_VIEW,
    },
}


def get_role_label(role: str) -> str:
    return ROLE_LABELS.get(role, "Workspace User")


def get_role_capabilities(role: str) -> List[str]:
    return sorted(ROLE_CAPABILITIES.get(role or "", set()))


def has_capability(role: str, capability: str) -> bool:
    return capability in ROLE_CAPABILITIES.get(role or "", set())


def get_user_scope(user: Dict) -> Dict:
    role = (user or {}).get("role")
    if role != ROLE_CLASS_TEACHER:
        return {
            "restricted": False,
            "class_names": [],
            "section_names": [],
            "camera_ids": [],
            "camera_names": [],
        }

    assignments = list(
        mongo_store.collection("class_assignments").find({"user_id": user.get("user_id")})
    )
    class_names = sorted({doc.get("class_name") for doc in assignments if doc.get("class_name")})
    section_names = sorted({doc.get("section_name") for doc in assignments if doc.get("section_name")})
    camera_ids = sorted({int(value) for doc in assignments for value in (doc.get("camera_ids") or []) if value is not None})
    camera_names = sorted({value for doc in assignments for value in (doc.get("camera_names") or []) if value})
    return {
        "restricted": True,
        "class_names": class_names,
        "section_names": section_names,
        "camera_ids": camera_ids,
        "camera_names": camera_names,
    }
