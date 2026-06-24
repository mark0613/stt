from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import src.config as cfg

LOGGER_NAME = 'stt'


def setup_logging(audio_path: Path) -> Path:
    """Route detailed logs to a file under <repo>/logs/. Returns the log file path."""
    logs_dir = cfg.BASE_DIR / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log_path = logs_dir / f'{stamp}-{audio_path.stem}.log'

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(message)s'))
    logger.handlers.clear()
    logger.addHandler(handler)

    return log_path


def get_logger(suffix: str | None = None) -> logging.Logger:
    name = f'{LOGGER_NAME}.{suffix}' if suffix else LOGGER_NAME
    return logging.getLogger(name)
