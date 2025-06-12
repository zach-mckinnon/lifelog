# lifelog/commands/time.py
''' 
Lifelog CLI - Time Tracking Module
This module provides functionality to track time spent on different activities or categories.
It allows users to start and stop timers, view current tracking status, and manage time records.
'''

from typing import List, Optional
import typer
from datetime import datetime, timedelta

from rich.console import Console
from rich.table import Table

from lifelog.utils.db.models import TimeLog
from lifelog.utils.db import time_repository
from lifelog.utils.shared_options import category_option, project_option, past_option

from lifelog.utils.shared_utils import (
    add_category_to_config,
    add_project_to_config,
    get_available_categories,
    get_available_projects,
    parse_date_string,
    parse_args,
)

app = typer.Typer(help="Track time spent in different life categories.")

console = Console()


@app.command("start")
def start(
    title: str = typer.Argument(..., help="Activity title"),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Additional +tags, or notes."
    ),
):
    """
    Start tracking time for an activity.
    """
    now = datetime.now()
    try:
        tags, notes = parse_args(args or [])
    except ValueError as e:
        console.print(f"[bold red]Error parsing args: {e}[/bold red]")
        raise typer.Exit(code=1)

    # Add new category/project if not existing
    if category and category not in get_available_categories():
        if typer.confirm(f"Add new category '{category}'?"):
            add_category_to_config(category)
    if project and project not in get_available_projects():
        if typer.confirm(f"Add new project '{project}'?"):
            add_project_to_config(project)

    # Check if already active
    active = time_repository.get_active_time_entry()
    if active:
        console.print(
            f"[yellow]⏳ Already tracking: '{active.title}' since {active.start}.[/yellow]"
        )
        raise typer.Exit(code=1)

    # Determine start time
    start_dt = parse_date_string(past, now=now) if past else now

    # Build TimeLog instance; tags and notes to None if empty
    tag_str = ",".join(tags) if tags else None
    note_str = " ".join(notes) if notes else None
    data = {
        "title": title,
        "start": start_dt,
        "category": category,
        "project": project,
        "tags": tag_str,
        "notes": note_str,
    }
    # Start entry in repository; assume repo accepts TimeLog
    try:
        time_repository.start_time_entry(data)
    except Exception as e:
        console.print(f"[bold red]Failed to start time entry: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✅ Started tracking: '{title}'[/green]")


@app.command("stop")
def stop(
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."
    ),
):
    """
    Stop the current timer and record the time block.
    """
    now = datetime.now()
    try:
        tags, notes = parse_args(args or [])
    except ValueError as e:
        console.print(f"[bold red]Error parsing args: {e}[/bold red]")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()
    if not active:
        console.print(
            "[yellow]⏸️ Looks like you're not actively tracking right now. Hope you got some time to rest![/yellow]"
        )
        console.print(
            "[dim]🌟 Ready to start something new whenever you are![/dim]"
        )
        raise typer.Exit(code=1)

    # Determine end time
    end_time = parse_date_string(past, now=now) if past else now

    # Stop the entry in the DB; repository returns updated TimeLog
    try:
        updated = time_repository.stop_active_time_entry(
            end_time=end_time,
            tags=",".join(tags) if tags else None,
            notes=" ".join(notes) if notes else None
        )
    except Exception as e:
        console.print(f"[bold red]Failed to stop time entry: {e}[/bold red]")
        raise typer.Exit(code=1)

    # Compute distracted and actual focused minutes
    distracted = updated.distracted_minutes or 0
    # Ensure start/end are datetime
    if updated.start and updated.end:
        total_minutes = (updated.end - updated.start).total_seconds() / 60
    else:
        total_minutes = 0
    actual_minutes = max(0, total_minutes - distracted)

    console.print(
        f"[green]⏹️ You spent [bold]{round(actual_minutes, 2)}[/bold] minutes on [bold]{updated.title}[/bold] "
        f"(Distracted: {distracted} min).[/green]"
    )
    console.print(
        f"[green]⏹️ Well done! You spent [bold]{round(total_minutes, 2)}[/bold] minutes on [bold]{updated.title}[/bold].[/green]"
    )
    console.print("[dim]🌱 Every minute you invest matters. Nice work![/dim]")


@app.command("summary")
def time_summary(
    by: str = typer.Option(
        "title", help="Field to group time by: title, category, or project."
    ),
    period: Optional[str] = typer.Option(
        None, help="Period to filter: 'day', 'week', 'month'. Leave blank for all time."
    ),
):
    """
    📊 Summarize time tracked by title, category, or project.
    Shows focused (duration minus distracted) and distracted minutes.
    """
    now = datetime.now()
    # Determine 'since' cutoff
    if period:
        if period == "day":
            since = now - timedelta(days=1)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            console.print(
                "[bold red]Invalid period.[/bold red] Must be 'day', 'week', or 'month'."
            )
            raise typer.Exit(code=1)
    else:
        # default to last year
        since = now - timedelta(days=365)

    # Fetch all TimeLog entries since 'since'
    try:
        history = time_repository.get_all_time_logs(since=since)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch time logs: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not history:
        console.print("[italic]No time tracking history found yet![/italic]")
        return

    # Validate 'by' field
    valid_fields = {"title", "category", "project"}
    if by not in valid_fields:
        console.print(
            f"[bold red]Invalid group field '{by}'. Choose title, category, or project.[/bold red]")
        raise typer.Exit(code=1)

    # Group by field: use getattr
    totals = {}
    distracted_totals = {}
    for record in history:
        # record is TimeLog; access attribute
        key = getattr(record, by, None) or "(none)"
        # If grouping by tags and tags stored as comma-separated string, split/join:
        # But since 'by' only allows title/category/project, skip special tags logic here.
        duration = record.duration_minutes or 0
        distracted = record.distracted_minutes or 0
        focus = max(0, duration - distracted)
        totals[key] = totals.get(key, 0) + focus
        distracted_totals[key] = distracted_totals.get(key, 0) + distracted

    # Sort descending by focused time
    sorted_totals = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    console.print(
        f"\n[bold green]🕒 Focused Time by {by.capitalize()}[/bold green]\n")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column(by.capitalize())
    table.add_column("Focus Minutes", justify="right")
    table.add_column("Distracted", justify="right")

    for key, minutes in sorted_totals:
        distracted = distracted_totals.get(key, 0)
        formatted = _format_duration(minutes)
        table.add_row(key, f"[cyan]{formatted}[/cyan]", str(distracted))

    console.print(table)


@app.command("distracted")
def distracted(
    duration: str = typer.Argument(...,
                                   help="How long were you distracted (e.g. 5m, 10m)?"),
    notes: Optional[str] = typer.Option(None, help="Optional notes.")
):
    """
    Log a distracted block (does not stop the current session).
    """
    now = datetime.now()
    # Parse duration like '5m', '10m', '1h'
    mins = None
    try:
        if duration.endswith('m'):
            mins = int(duration[:-1])
        elif duration.endswith('h'):
            mins = int(float(duration[:-1]) * 60)
        elif duration.isdigit():
            mins = int(duration)
        else:
            raise ValueError
    except ValueError:
        console.print(f"[bold red]Invalid duration: {duration}[/bold red]")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()
    note_str = notes if notes else None

    if active:
        # Increment distracted_minutes on active session
        try:
            new_distracted = time_repository.add_distracted_minutes_to_active(
                mins)
        except Exception as e:
            console.print(
                f"[bold red]Failed to update distracted minutes: {e}[/bold red]")
            raise typer.Exit(code=1)

        # Also log a separate distraction block if desired
        start_dt = now - timedelta(minutes=mins)
        distraction = TimeLog(
            title="Distracted",
            start=start_dt,
            end=now,
            category="distracted",
            duration_minutes=mins,
            notes=note_str
        )
        try:
            time_repository.add_time_entry(distraction)
        except Exception as e:
            console.print(
                f"[yellow]Warning: failed to log separate distraction entry: {e}[/yellow]")

        console.print(
            f"[green]✅ Distracted time (+{mins} min) logged for current session "
            f"(Total distracted: {new_distracted} min).[/green]"
        )
    else:
        # No active session: log distraction as standalone entry
        start_dt = now - timedelta(minutes=mins)
        distraction = TimeLog(
            title="Distracted",
            start=start_dt,
            end=now,
            category="distracted",
            duration_minutes=mins,
            notes=note_str
        )
        try:
            time_repository.add_time_entry(distraction)
        except Exception as e:
            console.print(
                f"[bold red]Failed to log distraction entry: {e}[/bold red]")
            raise typer.Exit(code=1)
        console.print(
            f"[green]✅ Distracted time ({mins} min) logged as standalone block.[/green]")


def _format_duration(minutes: float) -> str:
    """
    Format minutes into a human-readable string.
    """
    if minutes >= 60:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours} hrs {mins} min"
    else:
        return f"{int(minutes)} min"
