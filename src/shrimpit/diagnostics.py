"""Local rotating logs for startup errors and background jobs."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from shrimpit.resources import data_directory


class SharedRotatingFileHandler(RotatingFileHandler):
    """Keep logging when Windows refuses to rename a log another Shrimp'It instance holds open."""

    def doRollover(self):
        try:
            super().doRollover()
        except OSError:
            # The record would otherwise be lost: write on and retry the rotation with the next one.
            if self.stream is None:
                self.stream = self._open()


def log_directory() -> Path:
    return data_directory() / "logs"


def configure_logging() -> Path | None:
    logger = logging.getLogger("shrimpit")
    if logger.handlers:
        return log_directory()
    try:
        folder = log_directory()
        folder.mkdir(parents=True, exist_ok=True)
        handler = SharedRotatingFileHandler(
            folder / "shrimpit.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        logger.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return folder
