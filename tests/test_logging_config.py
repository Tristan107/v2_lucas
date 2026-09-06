from __future__ import annotations

import logging
from pathlib import Path

from lucas_v2.logging_config import setup_logging


def test_setup_logging_creates_handlers(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger = setup_logging(log_dir)
    assert logger.name == "lucas_v2"
    assert logger.level == logging.DEBUG
    handler_types = {type(h) for h in logger.handlers}
    assert logging.StreamHandler in handler_types
    assert any("TimedRotatingFileHandler" in t.__name__ for t in handler_types)


def test_setup_logging_creates_log_dir(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "new_logs")
    setup_logging(log_dir)
    assert Path(log_dir).is_dir()


def test_setup_logging_idempotent(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "logs")
    logger1 = setup_logging(log_dir)
    n_handlers = len(logger1.handlers)
    logger2 = setup_logging(log_dir)
    assert len(logger2.handlers) == n_handlers
    assert logger1 is logger2
