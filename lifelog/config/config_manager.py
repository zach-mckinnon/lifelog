# lifelog/config/config_manager.py
'''
config_manager.py - Configuration management for lifelog
'''
from importlib.resources import files
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional
import toml
from rich.console import Console

from lifelog.utils.encrypt import decrypt_data


console = Console()
# Standardized base directory
BASE_DIR = Path.home() / ".lifelog"
USER_CONFIG = BASE_DIR / "config.toml"

# Load default config from package resources
DEFAULT_CONFIG = files("lifelog.config").joinpath(
    "config.toml").read_text(encoding="utf-8")


def load_config() -> dict:
    # Ensure base directory exists
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Create default config if missing
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")

    # Load and return config
    return toml.loads(USER_CONFIG.read_text(encoding="utf-8"))


def save_config(doc: dict):
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with USER_CONFIG.open("w", encoding="utf-8") as f:
        f.write(toml.dumps(doc))


def get_deployment_mode_and_url():
    config = load_config()
    deployment = config.get("deployment", {})
    mode = deployment.get("mode", "standalone")
    server_url = deployment.get("server_url", "http://localhost:5000")
    return mode, server_url


def is_client_mode() -> bool:
    """
    Return True if the deployment mode is set to 'client' (or whatever you’ve chosen).
    """
    config = load_config()
    mode = config.get("deployment", {}).get("mode", "standalone")
    return mode == "client"


def get_config_value(section: str, key: str, default=None) -> Any:
    config = load_config()
    return config.get(section, {}).get(key, default)


def get_deployment_mode() -> str:
    config = load_config()
    return config.get("deployment", {}).get("mode", "local")


def get_server_url() -> str:
    config = load_config()
    return config.get("deployment", {}).get("server_url", "")


def is_host_server() -> bool:
    config = load_config()
    return config.get("deployment", {}).get("host_server", False)


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
