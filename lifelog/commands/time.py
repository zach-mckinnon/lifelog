# lifelog/commands/time.py
from typing import List, Optional
import typer
from pathlib import Path
from datetime import datetime
import json
from lifelog.config.config_manager import get_time_file
from lifelog.commands.utils.shared_options import tags_option, notes_option

app = typer.Typer(help="Track time spent in different life categories.")

TIME_TRACK_FILE = get_time_file()


def load_tracking():
    if TIME_TRACK_FILE.exists():
        with open(TIME_TRACK_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tracking(data):
    with open(TIME_TRACK_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.command()
def start(
    category: str, 
    tags: List[str] = tags_option,
    notes: Optional[str] = notes_option
    ):
    """
    Start tracking time for a category (e.g. working, resting).
    """
    data = load_tracking()

    if "active" in data:
        typer.echo(f"⏳ Already tracking: {data['active']['category']} (since {data['active']['start']})")
        raise typer.Exit()

    data["active"] = {
        "category": category,
        "start": datetime.now().isoformat(),
        "tags" : tags if tags else "",
        "notes": notes if notes else "",
    }
    save_tracking(data)
    typer.echo(f"▶️  Started tracking '{category}'")


@app.command()
def stop( 
    tags: List[str] = tags_option,
    notes: Optional[str] = notes_option
    ):
    """
    Stop the current timer and record the time block.
    """
    data = load_tracking()
    if "active" not in data:
        typer.echo("⚠️  No active tracking session.")
        raise typer.Exit()

    start_time = datetime.fromisoformat(data["active"]["start"])
    end_time = datetime.now()
    category = data["active"]["category"]
    duration = (end_time - start_time).total_seconds() / 60  # minutes

    record = {
        "category": category,
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration_minutes": round(duration, 2),
        "tags" : tags if tags else "",
        "notes": notes if notes else "",
    }

    history = data.get("history", [])
    history.append(record)
    data["history"] = history
    data.pop("active")

    save_tracking(data)
    typer.echo(f"⏹️  Stopped tracking '{category}' — duration: {round(duration, 2)} minutes")


@app.command()
def status():
    """
    Show the current active tracking session.
    """
    data = load_tracking()
    if "active" in data:
        typer.echo(f"Currently tracking '{data['active']['category']}' since {data['active']['start']}")
    else:
        typer.echo("No active session.")
