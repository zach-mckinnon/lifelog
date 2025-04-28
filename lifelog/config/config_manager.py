# lifelog/config/config_manager.py
'''
config_manager.py - Configuration management for lifelog
'''
from importlib.resources import files
import os
from pathlib import Path
from typing import Any, Dict, Optional
import toml
from tomlkit import parse, dumps

USER_CONFIG = Path.home() / ".config" / "lifelog" / "config.toml"
DEFAULT_CONFIG = files("lifelog.config").joinpath("config.toml").read_text()


def load_config() -> dict:
    # Ensure user config exists
    if not USER_CONFIG.exists():
        USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        USER_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return toml.loads(USER_CONFIG.read_text(encoding="utf-8"))

def save_config(doc: dict):
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with USER_CONFIG.open("w", encoding="utf-8") as f:
        f.write(toml.dumps(doc))


def expand_path(path_str: str) -> Path:
    """
    Expand ~ and environment variables in a path string.
    """
    return Path(os.path.expanduser(path_str))


def _load_paths() -> Dict[str, Any]:
    """
    Load only the [paths] section of the config.
    """
    config = load_config()
    paths = config.get("paths", {}) or {}
    return paths

# TODO: remove individual path functions and use a single function to get any path with passed key.

def get_config_section(section: str) -> Dict[str, Any]:
    """
    Load a specific section from the config file.
    """
    config = load_config()
    return config.get(section, {}) or {}


def get_track_file():
    paths = _load_paths()
    if "TRACK_FILE" not in paths:
        raise FileNotFoundError("TRACK_FILE not defined in config.toml [paths].")
    return expand_path(paths["TRACK_FILE"])


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
    if "FC_FILE" not in paths:
        raise FileNotFoundError("FC_FILE not defined in config.toml [paths].")
    return expand_path(paths["FC_FILE"])


def get_feedback_file() -> Path:
    """
    Path to the tasks log file.
    """
    paths = _load_paths()
    if "FEEDBACK_FILE" not in paths:
        raise FileNotFoundError("FEEDBACK_FILE not defined in config.toml [paths].")
    return expand_path(paths["FEEDBACK_FILE"])


def get_env_data_file() -> Path:
    """
    Path to the tasks log file.
    """
    paths = _load_paths()
    if "ENV_DATA_FILE" not in paths:
        raise FileNotFoundError("ENV_DATA_FILE not defined in config.toml [paths].")
    return expand_path(paths["ENV_DATA_FILE"])


def get_motivational_quote_file() -> Path:
    """
    Path to the daily quote file.
    """
    paths = _load_paths()
    if "DAILY_QUOTE_FILE" not in paths:
        raise FileNotFoundError("DAILY_QUOTE_FILE not defined in config.toml [paths].")
    return expand_path(paths["DAILY_QUOTE_FILE"])

def get_alias_map() -> Dict[str, str]:
    """
    Load the [aliases] section from the config.
    """
    config = load_config()
    return config.get("aliases", {}) or {}


def get_tracker_definition(name: str) -> Optional[Dict[str, Any]]:
    """
    Return the definition for a tracker (metric/habit) by name, or None if missing.
    """
    config = load_config()
    return config.get("tracker", {}).get(name)

#TODO: create a funcgion to get all user defined categories, projects, etc., from the config file by passing key