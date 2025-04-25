# lifelog/config/config_manager.py
import os
from pathlib import Path
from typing import Any, Dict, Optional
from tomlkit import parse, dumps

CONFIG_PATH = Path.home() / ".config" / "lifelog" / "config.toml"


def load_cron_config() -> Dict[str, Any]:
    """
    Load the full configuration as a plain dict. Returns an empty dict if no config exists.
    """
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r") as f:
            # parse returns a TOMLDocument, but it supports .get for dict-like access
            return parse(f.read())
    return {}



def save_config(config: Dict[str, Any]) -> None:
    """
    Save the configuration dict back to the config file, creating directories as needed.
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        f.write(dumps(config))


def expand_path(path_str: str) -> Path:
    """
    Expand ~ and environment variables in a path string.
    """
    return Path(os.path.expanduser(path_str))


def _load_paths() -> Dict[str, Any]:
    """
    Load only the [paths] section of the config.
    """
    config = load_cron_config()
    return config.get("paths", {}) or {}



def get_log_file():
    paths = _load_paths()
    if "LOG_FILE" not in paths:
        raise FileNotFoundError("log_file not defined in config.toml [paths].")
    return expand_path(paths["LOG_FILE"])


def get_time_file() -> Path:
    """
    Path to the time tracking log file.
    """
    paths = _load_paths()
    if "TIME_FILE" not in paths:
        raise FileNotFoundError("time_file not defined in config.toml [paths].")
    return expand_path(paths["TIME_FILE"])


def get_task_file() -> Path:
    """
    Path to the tasks log file.
    """
    paths = _load_paths()
    if "TASK_FILE" not in paths:
        raise FileNotFoundError("task_file not defined in config.toml [paths].")
    return expand_path(paths["TASK_FILE"])


def get_fc_file() -> Path:
    """
    Path to the tasks log file.
    """
    paths = _load_paths()
    if "FIRST_COMMAND_FLAG_FILE" not in paths:
        raise FileNotFoundError("FIRST_COMMAND_FLAG_FILE not defined in config.toml [paths].")
    return expand_path(paths["FIRST_COMMAND_FLAG_FILE"])


def get_feedback_file() -> Path:
    """
    Path to the tasks log file.
    """
    paths = _load_paths()
    if "FEEDBACK_FILE" not in paths:
        raise FileNotFoundError("FEEDBACK_FILE not defined in config.toml [paths].")
    return expand_path(paths["FEEDBACK_FILE"])


def get_init_marker() -> Path:
    """
    Path to the tasks log file.
    """
    paths = _load_paths()
    if "INIT_MARKER" not in paths:
        raise FileNotFoundError("INIT_MARKER not defined in config.toml [paths].")
    return expand_path(paths["INIT_MARKER"])

def get_daily_quote_file() -> Path:
    """
    Path to the daily quote file.
    """
    paths = _load_paths()
    if "DAILY_QUOTE_FILE" not in paths:
        raise FileNotFoundError("DAILY_QUOTE_FILE not defined in config.toml [paths].")
    return expand_path(paths["DAILY_QUOTE_FILE"])

def get_feedback_sayings_file() -> Path:
    """
    Path to the feedback sayings file.
    """
    paths = _load_paths()
    if "FEEDBACK_SAYINGS_FILE" not in paths:
        raise FileNotFoundError("FEEDBACK_SAYINGS_FILE not defined in config.toml [paths].")
    return expand_path(paths["FEEDBACK_SAYINGS_FILE"])

def get_alias_map() -> Dict[str, str]:
    """
    Load the [aliases] section from the config.
    """
    config = load_cron_config()
    return config.get("aliases", {}) or {}


def get_tracker_definition(name: str) -> Optional[Dict[str, Any]]:
    """
    Return the definition for a tracker (metric/habit) by name, or None if missing.
    """
    config = load_cron_config()
    return config.get("tracker", {}).get(name)
