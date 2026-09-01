from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from data_health_monitor.config import Settings, get_settings


LOGGER_NAME = "data_health_monitor"
_SAFE_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "error_type",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log_event"),
        }
        for field_name in _SAFE_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        if record.exc_info:
            payload["traceback"] = [
                {
                    "file": Path(frame.filename).name,
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _log_level(level_name: str) -> int:
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported log level: {level_name}")
    return level


def _log_file_path(settings: Settings) -> Path:
    configured_path = Path(settings.app_log_file).expanduser()
    if configured_path.is_absolute():
        return configured_path
    return Path(__file__).resolve().parents[2] / configured_path


def configure_logging(settings: Settings | None = None) -> logging.Logger:
    settings = settings or get_settings()
    logger = get_logger()
    logger.setLevel(_log_level(settings.app_log_level))
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    formatter = JsonFormatter()
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    log_file_path = _log_file_path(settings)
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=settings.app_log_max_bytes,
        backupCount=settings.app_log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(file_handler)
    return logger


def log_event(level: int, event: str, **fields: str | int | None) -> None:
    get_logger().log(level, event, extra={"event": event, **fields})