from __future__ import annotations

import os

os.environ["CHRONOSENSE_SERVICE_NAME"] = "activity-worker"
os.environ["CHRONOSENSE_EMOTION_ENABLED_DEFAULT"] = "false"
os.environ["CHRONOSENSE_ACTIVITY_ENABLED_DEFAULT"] = "true"
os.environ["CHRONOSENSE_UNKNOWN_FACE_TRACKING"] = "true"
os.environ["CHRONOSENSE_RECOGNITION_WORKER_ID"] = "activity-worker"

from recognition_worker import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
