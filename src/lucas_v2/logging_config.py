from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TextIO


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """Configure le logger racine lucas_v2 avec console + fichier rotatif quotidien."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger: logging.Logger = logging.getLogger("lucas_v2")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    console: logging.StreamHandler[TextIO] = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    file_handler: TimedRotatingFileHandler = TimedRotatingFileHandler(
        f"{log_dir}/ingestion.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"),
    )

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger
