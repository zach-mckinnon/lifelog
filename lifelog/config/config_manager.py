# lifelog/config/config_manager.py
import os
from pathlib import Path
from tomlkit import parse, document, dumps, loads

CONFIG_PATH = Path.home() / ".config" / "lifelog" / "config.toml"

def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r") as f:
            return parse(f.read())
    else:
        return document()

def save_config(doc):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        f.write(dumps(doc))
        
def expand_path(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str))

def get_config_paths():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            parsed = loads(f.read())
            return parsed.get("paths", {})
    return {}

def get_log_file():
    return expand_path(get_config_paths().get("log_file", "~/.lifelog.json"))

def get_time_file():
    return expand_path(get_config_paths().get("time_file", "~/.lifelog_time_tracking.json"))

def get_habit_file():
    return expand_path(get_config_paths().get("habit_file", "~/.lifelog_habits.json"))

def get_task_file():
    return Path(get_config_paths().get("paths", {}).get("task_log", Path.home() / ".lifelog_tasks.json"))


def get_alias_map():
    config_path = Path.home() / ".config" / "lifelog" / "config.toml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        parsed = loads(f.read())
    return parsed.get("aliases", {})


def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r") as f:
            return parse(f.read())
    else:
        # Return an empty doc if it doesn't exist
        return document()


def save_config(doc):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        f.write(dumps(doc))


def get_metric_definitions():
    config = load_config()
    return config.get("metric", {})


def get_metric_definition(metric_name):
    metric = get_metric_definitions()
    return metric.get(metric_name)