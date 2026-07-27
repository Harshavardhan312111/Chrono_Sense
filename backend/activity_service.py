from __future__ import annotations

import os

os.environ["CHRONOSENSE_SERVICE_NAME"] = "activity"
os.environ["CHRONOSENSE_EMOTION_ENABLED_DEFAULT"] = "false"
os.environ["CHRONOSENSE_ACTIVITY_ENABLED_DEFAULT"] = "true"

from server import app  # noqa: E402,F401
