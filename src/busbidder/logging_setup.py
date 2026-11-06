"""Logging configuration.

All modules log through ``logging.getLogger(__name__)``; their loggers are
children of the ``busbidder`` logger configured here. Everything at INFO and
above goes to the log file; only errors are echoed to the console, so normal
CLI output stays readable. Expected problems such as rejected data records are
warnings: they are in the log file and summarised by the CLI instead.
"""

import logging
from pathlib import Path

from busbidder.paths import LOG_FILE

LOGGER_NAME = "busbidder"
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(
    log_file: Path = LOG_FILE,
    level: int | str = logging.INFO,
    console_level: int | str = logging.ERROR,
) -> logging.Logger:
    """Configure and return the application logger (safe to call more than once)."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_FORMAT))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
