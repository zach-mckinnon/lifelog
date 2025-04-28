

import os
from typing import Any, Dict
from lifelog.config.config_manager import load_config
import typer
import rich
from rich.console import Console

app = typer.Typer(help="Debugging and development tools.")
console = Console()

def _load_paths() -> Dict[str, Any]:
    """
    Load only the [paths] section of the config.
    """
    config = load_config()
    # console.print(f"[info]Loaded config: {config}[/info]")
    paths = config.get("paths", {}) or {}
    console.print(f"[info]Loaded paths: {paths}[/info]")
    return paths

@app.command("remove-log-files", help="Remove all log files.")
def remove_TRACK_FILEs():
    paths = _load_paths()
    for p in paths.values():
        if p.endswith(".json") and not p.endswith(".toml"):
            full_path = os.path.expanduser(p)
            try:
                os.remove(full_path)
                print(f"[info]Removed log file: {full_path}[/info]")
            except Exception as e:
                print(f"[error]Failed to remove log file: {full_path} - {e}[/error]")
