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
from rich.table import Table

from lifelog.config.config_manager import get_time_file
from lifelog.commands.utils.shared_options import category_option, project_option, past_option

from lifelog.commands.utils.shared_utils import parse_date_string, parse_args


app = typer.Typer(help="Track time spent in different life categories.")

console = Console()


@app.command()
def start(
    title: str = typer.Argument(..., help="The title of the activity you're tracking. Put in quotes if you want to include spaces. :)"),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(None, help="Additional +tags, or notes."),
    ):
    """
    Start tracking time for an activity. (e.g. working, resting).
    """
    now = datetime.now()
    try:
        if args != None:
            tags, notes = parse_args(args)
        else:
            tags, notes = [], []
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)
    
    data = load_tracking()

    if "active" in data:
        console.print(f"[yellow]⏳ You're already making progress on '{data['active']['title']}' since {datetime.fromisoformat(data['active']['start'])}.[/yellow]")
        console.print("[dim]🌱 You can stop it first if you want to switch tasks![/dim]")
        raise typer.Exit(code=1)
    
    if past:
        start = parse_date_string(past, now=now)
    
    else:
        start = now
    
    data["active"] = {
        "title": title,
        "category": category if category else "",
        "project": project if project else "",
        "start": start.isoformat(),
        "end": None,
        "duration_minutes": 0,
        "tags" : tags,
        "notes": notes if notes else [],
    }

    save_tracking(data)
    console.print(f"[success]▶️ Great choice! You're now tracking: [bold]{title}[/bold][/success]")
    if any([category, project, tags, notes]):
        console.print(f"[info]🌟 Details: {category or ''} {project or ''} {tags or ''} {notes or ''}[/info]")


@app.command()
def stop( 
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes."),
    ):
    """
    Stop the current timer and record the time block.
    """
    now = datetime.now()
    try:
        if args != None:
            tags, notes = parse_args(args)
        else:
            tags, notes = [], []
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)
    
    data = load_tracking()
    
    if "active" not in data:
        console.print("[yellow]⏸️ Looks like you're not actively tracking right now. Hope you got some time to rest![/yellow]")
        console.print("[dim]🌟 Ready to start something new whenever you are![/dim]")
        raise typer.Exit(code=1)

    active = data["active"]

    start_time = datetime.fromisoformat(data["active"]["start"])
    if past:
        # If the user wants to set a past time, we need to adjust the start time
        end_time = parse_date_string(past, future=False, now=now)
    else:
        end_time = now
    
    final_tags = (active.get("tags") or [])
    if tags:
        final_tags.append(tags)

    final_notes = (active.get("notes") or [])
    if notes:
        final_notes.append(notes)

    duration = (end_time - start_time).total_seconds() / 60  # minutes
    title = active["title"]
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

    console.print(f"[success]⏹️ Well done! You spent [bold]{round(duration, 2)}[/bold] minutes on [bold]{title}[/bold].[/success]")
    
    data.pop("active")

    save_tracking(data)
    console.print("[dim]🌱 Every minute you invest matters. Nice work![/dim]")
    

@app.command()
def status():
    """
    Show the current active tracking session.
    """
    data = load_tracking()
    if "active" in data:
        start_str = data['active']['start']
        start_dt = datetime.fromisoformat(start_str)  # ✅ parse the string into a real datetime
        console.print(f"[info]Currently tracking '{data['active']['title']}' since {start_dt.strftime('%m/%d/%y %H:%M')}[/info]")
    else:
        console.print("[info]No active session.[/info]")

# TODO: Convert time to hours/minutes/seconds if more than 24 hours, put translation of days next to it 562hrs(23.42days)
@app.command("summary")
def time_summary(
    by: str = typer.Option("title", help="Field to group time by: title, category, or project."),
    period: Optional[str] = typer.Option(None, help="Period to filter: 'day', 'week', 'month'. Leave blank for all time."),
):
    """
    📊 Summarize time tracked by title, category, or project.
    """
    data = load_tracking()
    history = data.get("history", [])

    if not history:
        console.print("[italic]No time tracking history found yet![/italic]")
        return

    now = datetime.now()
    if period:
        if period == "day":
            since = now - timedelta(days=1)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            console.print("[bold red]Invalid period.[/bold red] Must be 'day', 'week', or 'month'.")
            raise typer.Exit(code=1)

        # Filter only records in the selected period
        history = [h for h in history if datetime.fromisoformat(h["start"]) >= since]

    totals = {}

    # Group by the selected field
    for record in history:
        key = record.get(by, "(none)")
        if isinstance(key, list):  # Just in case, for notes/tags mistakes
            key = ", ".join(key)
        if not key:
            key = "(none)"
        totals[key] = totals.get(key, 0) + record.get("duration_minutes", 0)

    # Sort by largest time spent
    sorted_totals = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    # Display
    console.print(f"\n[bold green]🕒 Time Spent by {by.capitalize()}[/bold green]\n")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column(by.capitalize())
    table.add_column("Total Minutes", justify="right")

    for key, minutes in sorted_totals:
        table.add_row(key, f"[cyan]{round(minutes, 2)}[/cyan]")

    console.print(table)


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
