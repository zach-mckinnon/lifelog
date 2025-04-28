# lifelog/commands/time.py
''' 
Lifelog CLI - Time Tracking Module
This module provides functionality to track time spent on different activities or categories.
It allows users to start and stop timers, view current tracking status, and manage time records.
'''

from typing import List, Optional
import typer
from datetime import datetime, timedelta
import json

from rich.console import Console

from lifelog.config.config_manager import get_time_file
from lifelog.commands.utils.shared_options import category_option, project_option

from lifelog.commands.utils.shared_utils import parse_date_string, parse_args


app = typer.Typer(help="Track time spent in different life categories.")

console = Console()


@app.command()
def start(
    args: List[str] = typer.Argument(..., help="Title, +tags, or notes. To add extra options after -c or -pr, add a -- after them before your other notes or tags."),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    ):
    """
    Start tracking time for an activity. (e.g. working, resting).
    """
    try:
        title, tags, notes, past = parse_args(args)
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)
    
    data = load_tracking()

    if "active" in data:
        console.print(f"[yellow]⏳ You're already making progress on '{data['active']['title']}' since {datetime.fromisoformat(data['active']['start'])}.[/yellow]")
        console.print("[dim]🌱 You can stop it first if you want to switch tasks![/dim]")
        raise typer.Exit(code=1)
    
    if past:
        start = datetime.now() - parse_date_string(past)
    
    else:
        start = datetime.now()
    
    data["active"] = {
        "title": title,
        "category": category if category else "",
        "project": project if project else "",
        "start": start.isoformat(),
        "end": None,
        "duration_minutes": 0,
        "tags" : tags if tags else "",
        "notes": notes if notes else "",
    }

    save_tracking(data)
    console.print(f"[success]▶️ Great choice! You're now tracking: [bold]{title}[/bold][/success]")
    if any([category, project, tags, notes]):
        console.print(f"[info]🌟 Details: {category or ''} {project or ''} {tags or ''} {notes or ''}[/info]")




@app.command()
def stop( 
    args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes."),
    ):
    """
    Stop the current timer and record the time block.
    """
    title, tags, notes, past = parse_args(args or [])
    data = load_tracking()
    
    if "active" not in data:
        console.print("[yellow]⏸️ Looks like you're not actively tracking right now. Hope you got some time to rest![/yellow]")
        console.print("[dim]🌟 Ready to start something new whenever you are![/dim]")
        raise typer.Exit(code=1)

    active = data["active"]

    start_time = datetime.fromisoformat(data["active"]["start"])
    if past:
        # If the user wants to set a past time, we need to adjust the start time
        end_time = datetime.now() - parse_date_string(past)
    else:
        end_time = datetime.now()
    
    final_tags = (active.get("tags") or [])
    if tags:
        final_tags += tags

    final_notes = (active.get("notes") or "")
    if notes:
        final_notes += " " + notes

    duration = (end_time - start_time).total_seconds() / 60  # minutes
    
    record = active.copy()
    record.update({
        "end": end_time.isoformat(),
        "duration_minutes": round(duration, 2),
        "tags": final_tags,
        "notes": final_notes,
    })

    history = data.get("history", [])
    history.append(record)
    data["history"] = history
    
    data.pop("active")

    save_tracking(data)
    console.print(f"[success]⏹️ Well done! You spent [bold]{round(duration, 2)}[/bold] minutes on [bold]{title}[/bold].[/success]")
    console.print("[dim]🌱 Every minute you invest matters. Nice work![/dim]")
    



@app.command()
def status():
    """
    Show the current active tracking session.
    """
    data = load_tracking()
    if "active" in data:
        console.print(f"[info]Currently tracking '{data['active']['title']}' since {data['active']['start'].strftime("%m/%d/%y %H:%M")}[/info]")
    else:
        console.print("[info]No active session.[/info]")


def load_tracking():
    TIME_TRACK_FILE = get_time_file()
    if TIME_TRACK_FILE.exists():
        with open(TIME_TRACK_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tracking(data):
    TIME_TRACK_FILE = get_time_file()
    with open(TIME_TRACK_FILE, "w") as f:
        json.dump(data, f, indent=2)
