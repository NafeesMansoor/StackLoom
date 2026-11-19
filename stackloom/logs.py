"""Logging to ~/.stackloom/logs/stackloom.log, bounded and redacted."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from stackloom import paths
from stackloom.security import redact


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup(level: int = logging.INFO) -> None:
    logger = logging.getLogger("stackloom")
    if logger.handlers:
        return
    paths.ensure()
    handler = RotatingFileHandler(paths.log_dir() / "stackloom.log", maxBytes=2_000_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(_Redact())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
