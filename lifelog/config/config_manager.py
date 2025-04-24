# lifelog/config/config_manager.py
from pathlib import Path
from tomlkit import parse, document, dumps

CONFIG_PATH = Path.home() / ".config" / "lifelog" / "config.toml"


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
    return config.get("metrics", {})


def get_metric_definition(metric_name):
    metrics = get_metric_definitions()
    return metrics.get(metric_name)