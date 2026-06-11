from __future__ import annotations
import logging
from logging import FileHandler

from app.services.debug_log_service import debug_log_path

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    """配置进程级应用日志。"""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    path = debug_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    debug_logger = logging.getLogger("ai_approval_assistant.debug")
    debug_logger.setLevel(logging.INFO)
    if not any(
        isinstance(handler, FileHandler)
        and getattr(handler, "baseFilename", "") == str(path)
        for handler in debug_logger.handlers
    ):
        file_handler = FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        debug_logger.addHandler(file_handler)
    debug_logger.propagate = False
