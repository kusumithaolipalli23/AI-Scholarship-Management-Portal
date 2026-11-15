"""
Centralized logging setup. Logs to console and to a rotating file under
LOG_DIR (default: backend/logs/app.log). Import `setup_logging(app)` once
from app.py after the Flask app is created.
"""
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from config import config


def setup_logging(app):
    os.makedirs(config.LOG_DIR, exist_ok=True)
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if setup_logging is called more than once (e.g. reloader)
    root.handlers = []

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(config.LOG_DIR, "app.log"), maxBytes=2_000_000, backupCount=5
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    error_file_handler = RotatingFileHandler(
        os.path.join(config.LOG_DIR, "error.log"), maxBytes=2_000_000, backupCount=5
    )
    error_file_handler.setFormatter(fmt)
    error_file_handler.setLevel(logging.ERROR)
    root.addHandler(error_file_handler)

    # Quiet down noisy libraries a little
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    logger = logging.getLogger("scholarai")

    @app.before_request
    def _log_request_start():
        from flask import request, g
        g._start_time = time.time()

    @app.after_request
    def _log_request_end(response):
        from flask import request, g
        try:
            duration_ms = round((time.time() - getattr(g, "_start_time", time.time())) * 1000, 1)
            logger.info(f"{request.method} {request.path} -> {response.status_code} ({duration_ms}ms)")
        except Exception:
            pass
        return response

    return logger


logger = logging.getLogger("scholarai")
