from __future__ import annotations

import os

os.environ["CHRONOSENSE_SERVICE_NAME"] = "attendance-worker"
os.environ["CHRONOSENSE_EMOTION_ENABLED_DEFAULT"] = "false"
os.environ["CHRONOSENSE_ACTIVITY_ENABLED_DEFAULT"] = "false"
os.environ["CHRONOSENSE_RECOGNITION_WORKER_ID"] = "attendance-worker"

from recognition_worker import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
