"""Local rotating logs for startup errors and background jobs."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_directory() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    return base / "Shrimpit" / "logs"


def configure_logging() -> Path | None:
    logger = logging.getLogger("shrimpit")
    if logger.handlers:
        return log_directory()
    try:
        folder = log_directory()
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            folder / "shrimpit.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        logger.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return folder
