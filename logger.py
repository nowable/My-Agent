import logging
import os
from logging.handlers import RotatingFileHandler


LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(_formatter)

_file = RotatingFileHandler(
    os.path.join(LOG_DIR, "bot.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file.setLevel(logging.DEBUG)
_file.setFormatter(_formatter)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        logger.addHandler(_console)
        logger.addHandler(_file)
    return logger
