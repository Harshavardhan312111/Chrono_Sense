from __future__ import annotations

import logging
import os
from pathlib import Path


_CONFIGURED_SERVICE_NAMES: set[str] = set()


def configure_logging(service_name: str | None = None) -> logging.Logger:
    resolved_service = (service_name or os.getenv("CHRONOSENSE_SERVICE_NAME") or "backend").strip() or "backend"
    root_logger = logging.getLogger()

    if resolved_service in _CONFIGURED_SERVICE_NAMES:
        return root_logger

    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{resolved_service}.log"

    formatter = logging.Formatter(
        fmt=f"%(asctime)s | %(levelname)s | {resolved_service} | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger.setLevel(logging.INFO)

    if not any(getattr(handler, "_chronosense_console", False) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler._chronosense_console = True  # type: ignore[attr-defined]
        root_logger.addHandler(console_handler)

    file_handler_exists = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path:
            handler.setFormatter(formatter)
            file_handler_exists = True
            break

    if not file_handler_exists:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _CONFIGURED_SERVICE_NAMES.add(resolved_service)
    return root_logger
