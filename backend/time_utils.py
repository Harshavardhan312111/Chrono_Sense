from datetime import datetime
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


def app_now():
    return datetime.now(APP_TIMEZONE)


def utc_now():
    return datetime.now(UTC)


def ensure_app_timezone(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).astimezone(APP_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def to_app_iso(value):
    localized = ensure_app_timezone(value)
    return localized.isoformat() if localized else None
