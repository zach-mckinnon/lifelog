# lifelog/config/config_manager.py
'''
config_manager.py - Configuration management for lifelog
'''
from importlib.resources import files
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Tuple
import toml
from rich.console import Console

from lifelog.utils.encrypt import decrypt_data


console = Console()
# Standardized base directory

MODES = ("local", "server", "client")

if "BASE_DIR" not in globals():
    # honor XDG_CONFIG_HOME first; else ~/.lifelog
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
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return toml.loads(USER_CONFIG.read_text(encoding="utf-8"))


def save_config(doc: dict):
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.write_text(toml.dumps(doc), encoding="utf-8")


def get_deployment_mode() -> str:
    cfg = load_config().get("deployment", {})
    mode = cfg.get("mode", "local")
    if mode not in MODES:
        console.print(
            f"[yellow]Warning:[/] unknown deployment.mode '{mode}', defaulting to 'local'")
        return "local"
    return mode


def get_server_url() -> str:
    return load_config().get("deployment", {}).get("server_url", "")


def is_local_mode() -> bool:
    return get_deployment_mode() == "local"


def is_server_mode() -> bool:
    return get_deployment_mode() == "server"


def is_client_mode() -> bool:
    return get_deployment_mode() == "client"


def get_deployment_mode_and_url() -> Tuple[str, str]:
    """
    Backwards‐compat shim for code & tests that still call get_deployment_mode_and_url().
    """
    return get_deployment_mode(), get_server_url()


def is_direct_db_mode() -> bool:
    return is_local_mode() or is_server_mode()


def is_host_server() -> bool:
    return bool(load_config().get("deployment", {}).get("host_server", False))


def get_config_value(section: str, key: str, default=None) -> Any:
    config = load_config()
    return config.get(section, {}).get(key, default)


def set_deployment_mode(mode):
    set_config_value("deployment", "mode", mode)


def find_docker_compose_cmd():
    import shutil
    # Try 'docker compose' (newer) and 'docker-compose' (legacy)
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    if shutil.which("docker") and subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0:
        return ["docker", "compose"]
    return None


def is_docker_running():
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def get_category_importance(category: str) -> float:
    """
    Get the importance multiplier for a category from config.
    Returns 1.0 if not set.
    """
    config = load_config()
    cat_impt = config.get("category_importance", {}) or {}
    try:
        return float(cat_impt.get(category, 1.0))
    except Exception:
        return 1.0


def set_config_value(section: str, key: str, value: Any):
    """
    Sets a value in the given config section and saves.
    Example: set_config_value("settings", "default_importance", 2)
    """
    config = load_config()
    sec = config.get(section, {})
    sec[key] = value
    config[section] = sec
    save_config(config)


def delete_config_value(section: str, key: str):
    """
    Deletes `key` from the specified `section` in the config, if it exists.
    """
    config = load_config()
    # grab the section dict (or empty if missing)
    sec = config.get(section, {})
    # remove the key if present
    if key in sec:
        del sec[key]
        # write back and persist
        config[section] = sec
        save_config(config)
    else:
        # no-op if the key wasn’t there; you could log or raise if you prefer
        console.print(f"[yellow]Warning:[/] '{key}' not found in [{section}]")


def get_all_category_importance() -> Dict[str, float]:
    config = load_config()
    cat_impt = config.get("category_importance", {}) or {}
    return {k: float(v) for k, v in cat_impt.items()}


def set_category_importance(category: str, value: float):
    config = load_config()
    cat_impt = config.get("category_importance", {}) or {}
    cat_impt[category] = value
    config["category_importance"] = cat_impt
    save_config(config)


def set_category_description(category: str, description: str):
    config = load_config()
    cats = config.get("categories", {})
    cats[category] = description
    config["categories"] = cats
    save_config(config)


def delete_category(category: str):
    config = load_config()
    cats = config.get("categories", {})
    if category in cats:
        del cats[category]
        config["categories"] = cats
        save_config(config)


def list_config_section(section: str) -> Dict[str, Any]:
    config = load_config()
    return config.get(section, {})


def get_ai_credentials():
    """Retrieve and decrypt AI credentials"""
    config = load_config()
    ai_config = config.get("ai", {})

    if not ai_config.get("enabled", False):
        return None

    provider = ai_config["provider"]
    encrypted_key = ai_config["api_key"]

    try:
        api_key = decrypt_data(config, encrypted_key)
        return {
            "provider": provider,
            "api_key": api_key
        }
    except Exception as e:
        Console.print(f"[red]Error decrypting AI credentials: {e}[/red]")
        return None


def get_config_section(section: str) -> Dict[str, Any]:
    """
    Load a specific section from the config file.
    """
    config = load_config()
    return config.get(section, {}) or {}


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
