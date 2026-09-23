"""
Centralized logging for VideoForge.
Supports per-project logs, central app log, and in-memory log buffer for GUI display.
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading


_LOG_BUFFER: list[dict] = []
_BUFFER_LOCK = threading.Lock()
_MAX_BUFFER = 2000
_CALLBACKS: list = []


class _CallbackHandler(logging.Handler):
    """Logging handler that dispatches to registered callbacks (for GUI)."""
    def emit(self, record: logging.LogRecord):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "logger": record.name,
            "message": self.format(record),
            "project_id": getattr(record, "project_id", None),
        }
        with _BUFFER_LOCK:
            _LOG_BUFFER.append(entry)
            if len(_LOG_BUFFER) > _MAX_BUFFER:
                _LOG_BUFFER.pop(0)
        for cb in _CALLBACKS:
            try:
                cb(entry)
            except Exception:
                pass


_root_handler: Optional[_CallbackHandler] = None
_file_handler: Optional[logging.FileHandler] = None


def setup_logging(log_dir: Optional[Path] = None, debug: bool = False):
    """Initialize application logging. Call once at startup."""
    global _root_handler, _file_handler

    root = logging.getLogger("videoforge")
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", "%H:%M:%S")
    console.setFormatter(fmt)
    root.addHandler(console)

    # Callback handler for GUI
    _root_handler = _CallbackHandler()
    _root_handler.setFormatter(fmt)
    root.addHandler(_root_handler)

    # File handler
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"videoforge_{datetime.now().strftime('%Y%m%d')}.log"
        _file_handler = logging.FileHandler(log_file, encoding="utf-8")
        _file_handler.setLevel(logging.DEBUG)
        _file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
        ))
        root.addHandler(_file_handler)
        root.info(f"Log file: {log_file}")


def register_log_callback(callback):
    """Register a callable that receives log entry dicts for GUI display."""
    _CALLBACKS.append(callback)


def unregister_log_callback(callback):
    if callback in _CALLBACKS:
        _CALLBACKS.remove(callback)


def get_log_buffer() -> list[dict]:
    with _BUFFER_LOCK:
        return list(_LOG_BUFFER)


def clear_log_buffer():
    with _BUFFER_LOCK:
        _LOG_BUFFER.clear()


def export_logs(path: Path, project_id: Optional[str] = None) -> bool:
    """Export log buffer to a text file. Filter by project_id if given."""
    try:
        with _BUFFER_LOCK:
            entries = list(_LOG_BUFFER)
        if project_id:
            entries = [e for e in entries if e.get("project_id") == project_id]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(f"[{e['timestamp']}] [{e['level']:<8}] {e['message']}\n")
        return True
    except Exception:
        return False


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the videoforge namespace."""
    return logging.getLogger(f"videoforge.{name}")


class ProjectAdapter(logging.LoggerAdapter):
    """Logger adapter that tags log records with a project_id."""
    def __init__(self, logger: logging.Logger, project_id: str):
        super().__init__(logger, {"project_id": project_id})

    def process(self, msg, kwargs):
        kwargs.setdefault("extra", {})["project_id"] = self.extra["project_id"]
        return msg, kwargs


def get_project_logger(project_id: str) -> ProjectAdapter:
    base = get_logger("project")
    return ProjectAdapter(base, project_id)
