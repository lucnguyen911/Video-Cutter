"""
app_logging.py — Centralized logging for Video Cutter.
======================================================
Sets up rotating file handlers for security, updater, and app logs.
Logs are written to %APPDATA%\\VideoCutter\\logs\\
"""

import logging
import os
from logging.handlers import RotatingFileHandler


def _get_log_dir() -> str:
    """Get the log directory, creating if needed."""
    from version import APPDATA_FOLDER
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(app_data, APPDATA_FOLDER, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_logging() -> None:
    """
    Configure logging for the application.
    
    Creates three log files:
        - security.log  (HWID, license, DPAPI)
        - updater.log   (update checks, downloads, installs)
        - app.log       (general application events)
    
    Each file is limited to 2MB with 3 backups.
    """
    log_dir = _get_log_dir()
    
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # ── Security logger ──
    security_logger = logging.getLogger("security")
    security_logger.setLevel(logging.DEBUG)
    if not security_logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(log_dir, "security.log"),
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        security_logger.addHandler(handler)
    
    # ── Updater logger ──
    updater_logger = logging.getLogger("updater")
    updater_logger.setLevel(logging.DEBUG)
    if not updater_logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(log_dir, "updater.log"),
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        updater_logger.addHandler(handler)
    
    # ── App logger ──
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG)
    if not app_logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        app_logger.addHandler(handler)


def mask_hwid(hwid: str) -> str:
    """Mask HWID for logging: show first 8 + last 5 chars."""
    if len(hwid) <= 13:
        return hwid[:4] + "..."
    return hwid[:8] + "..." + hwid[-5:]


def mask_key(key: str) -> str:
    """Mask license key for logging: show first 10 chars only."""
    if len(key) <= 10:
        return "***"
    return key[:10] + "..."
