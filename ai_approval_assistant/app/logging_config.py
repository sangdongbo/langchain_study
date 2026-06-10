from __future__ import annotations
import logging

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    """配置进程级应用日志。"""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
