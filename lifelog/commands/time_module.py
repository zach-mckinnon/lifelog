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

from lifelog.utils.shared_utils import add_category_to_config, add_project_to_config, get_available_categories, get_available_projects, parse_date_string, parse_args


app = typer.Typer(help="Track time spent in different life categories.")

console = Console()


def start(
    title: str = typer.Argument(..., help="Activity title"),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Additional +tags, or notes."),
):
    now = datetime.now()
    tags, notes = parse_args(args or [])
    if category and category not in get_available_categories():
        if typer.confirm(f"Add new category '{category}'?"):
            add_category_to_config(category)
    if project and project not in get_available_projects():
        if typer.confirm(f"Add new project '{project}'?"):
            add_project_to_config(project)
    active = time_repository.get_active_time_entry()
    if active:
        console.print(
            f"[yellow]⏳ Already tracking: '{active.title}' since {active.start}.[/yellow]")
        raise typer.Exit(code=1)
    start_dt = parse_date_string(past, now=now) if past else now
    log = TimeLog(
        title=title,
        start=start_dt,
        category=category,
        project=project,
        tags=",".join(tags),
        notes=notes
    )
    time_repository.start_time_entry(log)
    console.print(f"[green]Started tracking: '{title}'[/green]")


@app.command()
def stop(
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Stop the current timer and record the time block.
    """
    now = datetime.now()
    try:
        tags, notes = parse_args(args or [])
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()

    if not active:
        console.print(
            "[yellow]⏸️ Looks like you're not actively tracking right now. Hope you got some time to rest![/yellow]")
        console.print(
            "[dim]🌟 Ready to start something new whenever you are![/dim]")
        raise typer.Exit(code=1)

    end_time = parse_date_string(past, now=now) if past else now

    # Stop the entry in the DB and get updated log
    updated = time_repository.stop_active_time_entry(
        end_time=end_time,
        tags=",".join(tags) if tags else None,
        notes=notes if notes else None
    )
    distracted = updated.distracted_minutes or 0
    actual_minutes = max(
        0, ((updated.end - updated.start).total_seconds() / 60) - distracted)
    console.print(
        f"[success]⏹️ You spent [bold]{round(actual_minutes, 2)}[/bold] minutes on [bold]{updated.title}[/bold] (Distracted: {distracted} min).[/success]"
    )
    # Access model attributes
    duration = (
        (updated.end if updated else end_time) -
        (updated.start if updated else active.start)
    ).total_seconds() / 60

    console.print(
        f"[success]⏹️ Well done! You spent [bold]{round(duration, 2)}[/bold] minutes on [bold]{updated.title if updated else active.title}[/bold].[/success]")
    console.print("[dim]🌱 Every minute you invest matters. Nice work![/dim]")


@app.command("summary")
def time_summary(
    by: str = typer.Option(
        "title", help="Field to group time by: title, category, or project."),
    period: Optional[str] = typer.Option(
        None, help="Period to filter: 'day', 'week', 'month'. Leave blank for all time."),
):
    """
    📊 Summarize time tracked by title, category, or project.
    """
    since = None

    now = datetime.now()
    if period:
        if period == "day":
            since = now - timedelta(days=1)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            console.print(
                "[bold red]Invalid period.[/bold red] Must be 'day', 'week', or 'month'.")
            raise typer.Exit(code=1)
    else:
        since = now - timedelta(days=365)

    history = time_repository.get_all_time_logs(since=since)

    if not history:
        console.print("[italic]No time tracking history found yet![/italic]")
        return

    # Group by field
    totals = {}
    for record in history:
        key = record.get(by) or "(none)"
        if isinstance(key, list):
            key = ", ".join(key)
        totals[key] = totals.get(
            key, 0) + (record.get("duration_minutes") or 0)

    sorted_totals = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    console.print(
        f"\n[bold green]🕒 Time Spent by {by.capitalize()}[/bold green]\n")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column(by.capitalize())
    table.add_column("Total Minutes", justify="right")

    for key, minutes in sorted_totals:
        formatted = _format_duration(minutes)
        table.add_row(key, f"[cyan]{formatted}[/cyan]")

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
    mins = None
    # Parse duration like '5m', '10m', '1h'
    if duration.endswith('m'):
        mins = int(duration[:-1])
    elif duration.endswith('h'):
        mins = int(float(duration[:-1]) * 60)
    elif duration.isdigit():
        mins = int(duration)
    else:
        console.print(f"[error]Invalid duration: {duration}[/error]")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()
    if active:
        # Just increment the distracted_minutes
        new_distracted = time_repository.add_distracted_minutes_to_active(mins)
        # Optionally, also log as a new "Distracted" entry
        distraction = TimeLog(
            title="Distracted",
            start=now - timedelta(minutes=mins),
            end=now,
            category="distracted",
            duration_minutes=mins,
            notes=notes
        )
        time_repository.add_time_entry(distraction)
        console.print(
            f"[green]Distracted time (+{mins} min) logged for current session (Total distracted: {new_distracted} min).[/green]")
    else:
        # No session, log as a local distraction (and increment daily stat elsewhere if desired)
        start = now - timedelta(minutes=mins)
        distraction = TimeLog(
            title="Distracted",
            start=start,
            end=now,
            category="distracted",
            duration_minutes=mins,
            notes=notes
        )
        time_repository.add_time_entry(distraction)
        console.print(
            f"[green]Distracted time ({mins} min) logged as local block.[/green]")


@app.command("summary")
def time_summary(
    by: str = typer.Option(
        "title", help="Field to group time by: title, category, or project."),
    period: Optional[str] = typer.Option(
        None, help="Period to filter: 'day', 'week', 'month'. Leave blank for all time."),
):
    """
    📊 Summarize time tracked by title, category, or project.
    """
    since = None
    now = datetime.now()
    if period:
        if period == "day":
            since = now - timedelta(days=1)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            console.print(
                "[bold red]Invalid period.[/bold red] Must be 'day', 'week', or 'month'.")
            raise typer.Exit(code=1)
    else:
        since = now - timedelta(days=365)

    history = time_repository.get_all_time_logs(since=since)

    if not history:
        console.print("[italic]No time tracking history found yet![/italic]")
        return

    # Group by field
    totals = {}
    distracted_totals = {}
    for record in history:
        key = getattr(record, by, None) or "(none)"
        # If tags field and grouping, prettify:
        if by == "tags" and isinstance(key, str):
            key = key.replace(",", ", ")
        duration = record.duration_minutes or 0
        distracted = getattr(record, 'distracted_minutes', 0) or 0
        focus = max(0, duration - distracted)
        totals[key] = totals.get(key, 0) + focus
        distracted_totals[key] = distracted_totals.get(key, 0) + distracted

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
        table.add_row(key, f"[cyan]{formatted}[/cyan]", f"{distracted}")

    console.print(table)


def _format_duration(minutes: float) -> str:
    if minutes >= 60:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours} hrs {mins} min"
    else:
        return f"{int(minutes)} min"
