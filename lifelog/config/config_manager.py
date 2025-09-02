# lifelog/config/config_manager.py
'''
config_manager.py - Configuration management for lifelog
'''
from importlib.resources import files
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Tuple
import toml
from rich.console import Console

from lifelog.utils.encrypt import decrypt_data


console = Console()

logger = logging.getLogger(__name__)

MODES = ("local", "server", "client")

if "BASE_DIR" not in globals():
    _xdg = os.getenv("XDG_CONFIG_HOME")
    BASE_DIR = Path(_xdg) if _xdg else Path.home() / ".lifelog"

if "USER_CONFIG" not in globals():
    USER_CONFIG = BASE_DIR / "config.toml"

if "DEFAULT_CONFIG" not in globals():
    # the shipped defaults, read from your package resources
    DEFAULT_CONFIG = files("lifelog.config") \
        .joinpath("config.toml") \
        .read_text(encoding="utf-8")


def load_config() -> dict:
    """
    Load the user configuration from USER_CONFIG file.
    - If the config directory or file does not exist, create them with defaults.
    - Returns a dict parsed from TOML; on error, logs and returns empty dict.
    """
    try:
        # Ensure config directory exists
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        # If no user config file, write default contents
        if not USER_CONFIG.exists():
            try:
                USER_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")
            except Exception as e:
                logger.error(
                    f"Failed to write default config to {USER_CONFIG}: {e}", exc_info=True)
                # Continue; attempt to read file may still fail below
        # Read file contents
        try:
            text = USER_CONFIG.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(
                f"Failed to read config file {USER_CONFIG}: {e}", exc_info=True)
            return {}
        # Parse TOML
        try:
            return toml.loads(text)
        except Exception as e:
            logger.error(
                f"Failed to parse TOML from {USER_CONFIG}: {e}", exc_info=True)
            return {}
    except Exception as e:
        # Catch any unexpected errors
        logger.error(f"Unexpected error in load_config: {e}", exc_info=True)
        return {}


def save_config(doc: dict):
    """
    Save the given config dict to USER_CONFIG in TOML format.
    - On error, logs and returns False; otherwise returns True.
    """
    try:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(
            f"Failed to ensure config directory {BASE_DIR}: {e}", exc_info=True)
        # Still attempt to write file; likely to fail but let that be logged next
    try:
        toml_str = toml.dumps(doc)
    except Exception as e:
        logger.error(f"Failed to serialize config to TOML: {e}", exc_info=True)
        return False
    try:
        USER_CONFIG.write_text(toml_str, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(
            f"Failed to write config to {USER_CONFIG}: {e}", exc_info=True)
        return False


def get_deployment_mode() -> str:
    """
    Return deployment.mode from config (one of MODES).
    - Defaults to 'local'.
    - If unknown mode found, logs a warning and returns 'local'.
    """
    try:
        cfg = load_config().get("deployment", {})
        mode = cfg.get("mode", "local")
        if mode not in MODES:
            logger.warning(
                f"Unknown deployment.mode '{mode}', defaulting to 'local'")
            return "local"
        return mode
    except Exception as e:
        logger.error(f"Error retrieving deployment mode: {e}", exc_info=True)
        return "local"


def get_server_url() -> str:
    """
    Return deployment.server_url from config, or empty string if missing.
    """
    try:
        return load_config().get("deployment", {}).get("server_url", "") or ""
    except Exception as e:
        logger.error(f"Error retrieving server URL: {e}", exc_info=True)
        return ""


def is_local_mode() -> bool:
    """
    Return True if deployment mode is 'local'.
    """
    try:
        return get_deployment_mode() == "local"
    except Exception as e:
        logger.error(f"Error checking local mode: {e}", exc_info=True)
        return False


def is_server_mode() -> bool:
    """
    Return True if deployment mode is 'server'.
    """
    try:
        return get_deployment_mode() == "server"
    except Exception as e:
        logger.error(f"Error checking server mode: {e}", exc_info=True)
        return False


def is_client_mode() -> bool:
    """
    Return True if deployment mode is 'client'.
    """
    try:
        return get_deployment_mode() == "client"
    except Exception as e:
        logger.error(f"Error checking client mode: {e}", exc_info=True)
        return False


def get_deployment_mode_and_url() -> Tuple[str, str]:
    """
    Backwards‐compat shim: return (deployment_mode, server_url).
    """
    try:
        return get_deployment_mode(), get_server_url()
    except Exception as e:
        logger.error(
            f"Error retrieving deployment mode and URL: {e}", exc_info=True)
        return ("local", "")


def is_direct_db_mode() -> bool:
    """
    Return True if running in 'local' or 'server' mode (i.e., direct DB access).
    """
    try:
        # Note: get_deployment_mode is safe-wrapped
        return is_local_mode() or is_server_mode()
    except Exception as e:
        logger.error(f"Error checking direct DB mode: {e}", exc_info=True)
        return False


def is_host_server() -> bool:
    """
    Return True if 'host_server' flag in config is truthy.
    """
    try:
        return bool(load_config().get("deployment", {}).get("host_server", False))
    except Exception as e:
        logger.error(f"Error checking host_server flag: {e}", exc_info=True)
        return False


def get_config_value(section: str, key: str, default=None) -> Any:
    """
    Return value for [section][key] in config, or default if missing.
    """
    try:
        config = load_config()
        return config.get(section, {}).get(key, default)
    except Exception as e:
        logger.error(
            f"Error getting config value for [{section}][{key}]: {e}", exc_info=True)
        return default


def set_deployment_mode(mode: str) -> bool:
    """
    Set deployment.mode to given mode (must be one of MODES) and save config.
    Returns True if saved successfully, False otherwise.
    """
    if mode not in MODES:
        logger.warning(
            f"Attempted to set invalid deployment mode '{mode}'. Must be one of {MODES}.")
        return False
    try:
        return set_config_value("deployment", "mode", mode)
    except Exception as e:
        logger.error(f"Error setting deployment mode: {e}", exc_info=True)
        return False


def find_docker_compose_cmd() -> Optional[list]:
    """
    Return a list command for docker-compose or ['docker', 'compose'] if available, else None.
    """
    import shutil
    try:
        if shutil.which("docker-compose"):
            return ["docker-compose"]
        # Check newer 'docker compose'
        if shutil.which("docker"):
            result = subprocess.run(
                ["docker", "compose", "version"], capture_output=True, timeout=15)
            if result.returncode == 0:
                return ["docker", "compose"]
        return None
    except Exception as e:
        logger.error(
            f"Error finding docker-compose command: {e}", exc_info=True)
        return None


def is_docker_running() -> bool:
    """
    Return True if 'docker info' returns exit code 0, else False.
    """
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(
            f"Error checking if Docker is running: {e}", exc_info=True)
        return False


def get_category_importance(category_name: str) -> float:
    """
    Return importance multiplier for a category from [category_importance].
    Defaults to 1.0 if missing or on error.
    """
    try:
        config = load_config()
        cat_importances = config.get("category_importance", {}) or {}
        val = cat_importances.get(category_name, 1.0)
        try:
            return float(val)
        except Exception:
            logger.warning(
                f"Category importance for '{category_name}' is not a float: {val}. Using 1.0.")
            return 1.0
    except Exception as e:
        logger.error(
            f"Error getting category importance for '{category_name}': {e}", exc_info=True)
        return 1.0


def set_config_value(section: str, key: str, value: Any) -> bool:
    """
    Set config[section][key] = value and persist.
    Returns True if saved successfully, False otherwise.
    """
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Error loading config to set value: {e}", exc_info=True)
        config = {}
    try:
        sec = config.get(section, {}) or {}
        sec[key] = value
        config[section] = sec
        success = save_config(config)
        if not success:
            logger.error(
                f"Failed to save config after setting [{section}][{key}]")
        return success
    except Exception as e:
        logger.error(
            f"Error setting config value for [{section}][{key}]: {e}", exc_info=True)
        return False


def delete_config_value(section: str, key: str) -> bool:
    """
    Delete key from config[section] if present, persist changes.
    Returns True if deleted (or section/key missing and treated as no-op), False on write error.
    """
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Error loading config for deletion: {e}", exc_info=True)
        return False
    try:
        sec = config.get(section, {}) or {}
        if key in sec:
            del sec[key]
            config[section] = sec
            success = save_config(config)
            if not success:
                logger.error(
                    f"Failed to save config after deleting [{section}][{key}]")
            return success
        else:
            logger.warning(
                f"delete_config_value: '{key}' not found in section [{section}]. No action taken.")
            return True
    except Exception as e:
        logger.error(
            f"Error deleting config value [{section}][{key}]: {e}", exc_info=True)
        return False


def get_all_category_importance() -> Dict[str, float]:
    """
    Return a dict of all category importances from config.
    On error, returns empty dict.
    """
    try:
        config = load_config()
        cat_impt = config.get("category_importance", {}) or {}
        result: Dict[str, float] = {}
        for k, v in cat_impt.items():
            try:
                result[k] = float(v)
            except Exception:
                logger.warning(
                    f"Category importance value for '{k}' is not float: {v}. Skipping.")
        return result
    except Exception as e:
        logger.error(
            f"Error retrieving all category importance: {e}", exc_info=True)
        return {}


def set_category_importance(category: str, value: float) -> bool:
    """
    Set category importance in config and save.
    Returns True on success, False otherwise.
    """
    try:
        config = load_config()
    except Exception as e:
        logger.error(
            f"Error loading config to set category importance: {e}", exc_info=True)
        config = {}
    try:
        cat_impt = config.get("category_importance", {}) or {}
        cat_impt[category] = value
        config["category_importance"] = cat_impt
        success = save_config(config)
        if not success:
            logger.error(
                f"Failed to save config after setting category importance for '{category}'")
        return success
    except Exception as e:
        logger.error(
            f"Error setting category importance for '{category}': {e}", exc_info=True)
        return False


def set_category_description(category: str, description: str) -> bool:
    """
    Set categories[category] = description in config and save.
    Returns True on success, False otherwise.
    """
    try:
        config = load_config()
    except Exception as e:
        logger.error(
            f"Error loading config to set category description: {e}", exc_info=True)
        config = {}
    try:
        cats = config.get("categories", {}) or {}
        cats[category] = description
        config["categories"] = cats
        success = save_config(config)
        if not success:
            logger.error(
                f"Failed to save config after setting description for category '{category}'")
        return success
    except Exception as e:
        logger.error(
            f"Error setting category description for '{category}': {e}", exc_info=True)
        return False


def delete_category(category: str) -> bool:
    """
    Remove category from config['categories'] if exists, and save.
    Returns True on success or if category not present; False if write error.
    """
    try:
        config = load_config()
    except Exception as e:
        logger.error(
            f"Error loading config to delete category: {e}", exc_info=True)
        return False
    try:
        cats = config.get("categories", {}) or {}
        if category in cats:
            del cats[category]
            config["categories"] = cats
            success = save_config(config)
            if not success:
                logger.error(
                    f"Failed to save config after deleting category '{category}'")
            return success
        else:
            logger.warning(
                f"delete_category: '{category}' not found in [categories]. No action taken.")
            return True
    except Exception as e:
        logger.error(
            f"Error deleting category '{category}': {e}", exc_info=True)
        return False


def list_config_section(section: str) -> Dict[str, Any]:
    """
    Return the entire dict for given section name from config.
    On missing section or error, returns empty dict.
    """
    try:
        config = load_config()
        sec = config.get(section, {})
        if isinstance(sec, dict):
            return sec
        else:
            logger.warning(
                f"list_config_section: section [{section}] is not a dict in config.")
            return {}
    except Exception as e:
        logger.error(
            f"Error listing config section [{section}]: {e}", exc_info=True)
        return {}




def get_config_section(section: str) -> Dict[str, Any]:
    """
    Return the dict for [section] from config.
    On error or missing, returns empty dict.
    """
    try:
        config = load_config()
        sec = config.get(section, {})
        if isinstance(sec, dict):
            return sec
        else:
            logger.warning(
                f"get_config_section: section [{section}] is not a dict.")
            return {}
    except Exception as e:
        logger.error(
            f"Error retrieving config section [{section}]: {e}", exc_info=True)
        return {}


def get_alias_map() -> Dict[str, str]:
    """
    Load the [aliases] section from config.
    Returns a dict or empty if missing/error.
    """
    try:
        config = load_config()
        aliases = config.get("aliases", {})
        if isinstance(aliases, dict):
            return aliases
        else:
            logger.warning("get_alias_map: 'aliases' section is not a dict.")
            return {}
    except Exception as e:
        logger.error(f"Error retrieving alias map: {e}", exc_info=True)
        return {}


def get_tracker_definition(name: str) -> Optional[Dict[str, Any]]:
    """
    Return the definition for a tracker (under [tracker]) by name, or None if missing/error.
    """
    try:
        config = load_config()
        tracker_section = config.get("tracker", {})
        if not isinstance(tracker_section, dict):
            logger.warning(
                "get_tracker_definition: 'tracker' section is not a dict.")
            return None
        return tracker_section.get(name)
    except Exception as e:
        logger.error(
            f"Error retrieving tracker definition for '{name}': {e}", exc_info=True)
        return None
