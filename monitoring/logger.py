import logging
import os
from datetime import datetime
from config.settings import LOG_DIR, LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler
    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.utcnow().strftime("%Y%m%d")
    fh = logging.FileHandler(f"{LOG_DIR}/bot_{today}.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
