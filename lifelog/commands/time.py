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

from lifelog.commands.utils.db import time_repository
from lifelog.config.config_manager import get_time_file
from lifelog.commands.utils.shared_options import category_option, project_option, past_option

from lifelog.commands.utils.shared_utils import parse_date_string, parse_args


app = typer.Typer(help="Track time spent in different life categories.")

console = Console()


@app.command()
def start(
    title: str = typer.Argument(
        ..., help="The title of the activity you're tracking. Put in quotes if you want to include spaces. :)"),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Additional +tags, or notes."),
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

    active = time_repository.get_active_time_entry()

    if active:
        console.print(
            f"[yellow]⏳ You're already making progress on '{active['title']}' since {active['start']}.[/yellow]")
        raise typer.Exit(code=1)

    if past:
        start = parse_date_string(past, now=now)

    else:
        start = now

    time_repository.start_time_entry(
        title=title,
        category=category,
        project=project,
        start_time=start.isoformat()
    )
    console.print(
        f"[success]▶️ Great choice! You're now tracking: [bold]{title}[/bold][/success]")
    if any([category, project, tags, notes]):
        console.print(
            f"[info]🌟 Details: {category or ''} {project or ''} {tags or ''} {notes or ''}[/info]")


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

    # Calculate the end time and duration
    end_time = parse_date_string(past, now=now) if past else now

    # Stop the entry via repository (which calculates duration automatically)
    time_repository.stop_active_time_entry(
        end_time=end_time.isoformat(),
        tags=",".join(tags) if tags else None,
        notes=notes if notes else None
    )

    duration = (
        end_time - datetime.fromisoformat(active["start"])).total_seconds() / 60

    console.print(
        f"[success]⏹️ Well done! You spent [bold]{round(duration, 2)}[/bold] minutes on [bold]{active['title']}[/bold].[/success]")
    console.print("[dim]🌱 Every minute you invest matters. Nice work![/dim]")


@app.command()
def status():
    """
    Show the current active tracking session.
    """
    active = time_repository.get_active_time_entry()

    if active:
        start_str = active['start']
        start_dt = datetime.fromisoformat(start_str)

        # Optional: show if attached to a task
        task_info = f" [task #{active['task_id']}]" if active.get(
            'task_id') else ""

        # Duration live
        elapsed = datetime.now() - start_dt
        hours = elapsed.total_seconds() // 3600
        days = hours / 24

        time_str = f"{round(hours, 2)} hours ({round(days, 2)} days)" if hours > 24 else f"{round(hours, 2)} hours"

        console.print(
            f"[info]Currently tracking '{active['title']}'{task_info} since {start_dt.strftime('%m/%d/%y %H:%M')} — Elapsed: {time_str}[/info]")
    else:
        console.print("[info]No active session.[/info]")


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


def _format_duration(minutes: float) -> str:
    if minutes >= 60:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours} hrs {mins} min"
    else:
        return f"{int(minutes)} min"
