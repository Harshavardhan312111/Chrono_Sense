from __future__ import annotations

import os

os.environ["CHRONOSENSE_SERVICE_NAME"] = "emotion"
os.environ["CHRONOSENSE_EMOTION_ENABLED_DEFAULT"] = "true"
os.environ["CHRONOSENSE_ACTIVITY_ENABLED_DEFAULT"] = "false"

from server import app  # noqa: E402,F401
