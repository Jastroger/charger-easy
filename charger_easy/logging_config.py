from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


def configure_logger(config: dict[str, Any]) -> logging.Logger:
    logging_config = config["logging"]
    log_level = getattr(logging, logging_config.get("level", "INFO").upper(), logging.INFO)

    logger = logging.getLogger("mqtt_client_logger")
    logger.setLevel(log_level)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    log_path = Path(logging_config["file_path"])
    if log_path.parent:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

