# lifelog/utils/log_utils.py

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from typing import Union


def setup_logging(level: Union[int, str] = logging.INFO):
    """
    Configure root logger with:
     - RotatingFileHandler writing to ~/.lifelog/logs/lifelog.log
     - StreamHandler to console
    Idempotent: calling multiple times won’t add duplicate handlers.
    Optional `level` param can be numeric or string (e.g., logging.DEBUG or "DEBUG").
    """
    # Determine log directory
    try:
        log_dir = Path.home() / ".lifelog" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # If directory creation fails, log to console only
        print(f"WARNING: Could not create log directory {log_dir}: {e}")
        _configure_console_logging(level)
        return

    root_logger = logging.getLogger()
    # Convert string level to numeric if needed
    try:
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        root_logger.setLevel(level)
    except Exception:
        root_logger.setLevel(logging.INFO)

    existing_handlers = list(root_logger.handlers)

    # 1) RotatingFileHandler: only add if not already present for our log file
    file_log_path = log_dir / "lifelog.log"
    add_file = True
    for h in existing_handlers:
        if isinstance(h, RotatingFileHandler):
            base = getattr(h, 'baseFilename', None)
            if base and os.path.abspath(base) == str(file_log_path):
                add_file = False
                break
    if add_file:
        try:
            file_handler = RotatingFileHandler(
                file_log_path,
                maxBytes=5 * 1024 * 1024,
                backupCount=3
            )
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"WARNING: Could not set up file logging: {e}")

    # 2) Console handler: only add if not already present
    add_console = True
    for h in existing_handlers:
        if isinstance(h, logging.StreamHandler):
            add_console = False
            break
    if add_console:
        try:
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(level)
            root_logger.addHandler(console_handler)
        except Exception as e:
            print(f"WARNING: Could not set up console logging: {e}")


def _configure_console_logging(level: Union[int, str] = logging.INFO):
    """
    Fallback: configure only console logging if file handler cannot be created.
    """
    root_logger = logging.getLogger()
    try:
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        root_logger.setLevel(level)
    except Exception:
        root_logger.setLevel(logging.INFO)

    for h in root_logger.handlers:
        if isinstance(h, logging.StreamHandler):
            return

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)
