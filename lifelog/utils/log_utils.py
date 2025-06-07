import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def setup_logging():
    log_dir = Path.home() / ".lifelog" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Rotating file handler (5MB per file, keep 3 backups)
    file_handler = RotatingFileHandler(
        log_dir / "lifelog.log",
        maxBytes=5*1024*1024,
        backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)

    # Also log to console for CLI commands
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(console_handler)
