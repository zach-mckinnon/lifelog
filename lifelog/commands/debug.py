

import os
from typing import Any, Dict
from lifelog.config.config_manager import load_config
import typer
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
                print(
                    f"[error]Failed to remove log file: {full_path} - {e}[/error]")


@app.command("show-file", help="Show the contents of a file defined in [paths].")
def show_file(
    key: str = typer.Argument(
        ..., help="The config key of the file (e.g., TRACK_FILE, TIME_FILE, etc.)")
):
    """
    Load and display the contents of the specified file from the [paths] section.
    """
    paths = _load_paths()

    if key not in paths:
        console.print(
            f"[bold red]❌ No path found for key '{key}' in config.[/bold red]")
        raise typer.Exit(code=1)

    file_path = os.path.expanduser(paths[key])

    if not os.path.exists(file_path):
        console.print(f"[bold red]❌ File not found:[/bold red] {file_path}")
        raise typer.Exit(code=1)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            console.rule(f"[bold blue]Contents of {key}[/bold blue]")
            console.print(content)
            console.rule()
    except Exception as e:
        console.print(
            f"[bold red]❌ Failed to read {file_path}[/bold red]: {e}")
        raise typer.Exit(code=1)
