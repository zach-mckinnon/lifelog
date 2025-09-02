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
from lifelog.utils.cli_enhanced import cli
from lifelog.utils.cli_decorators import (
    with_loading, with_operation_header, database_operation,
    interactive_command, with_performance_monitoring
)

from lifelog.utils.shared_utils import (
    add_category_to_config,
    add_project_to_config,
    get_available_categories,
    get_available_projects,
    now_utc,
    parse_date_string,
    parse_args,
    parse_offset_to_timedelta,
)

app = typer.Typer(help="⏱️  Track time spent in different life categories.")

console = Console()


@app.command("start")
@with_operation_header("Starting Time Tracking", "Initialize new time tracking session")
@database_operation("Start Time Entry")
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
    🚀 Start tracking time for an activity with enhanced interface.
    """
    now = now_utc()
    with cli.thinking("Parsing arguments"):
        try:
            tags, notes = parse_args(args or [])
        except ValueError as e:
            cli.error(f"Error parsing arguments: {e}")
            raise typer.Exit(code=1)

    if category and category not in get_available_categories():
        if cli.enhanced_confirm(f"Create new category '{category}'?"):
            with cli.loading_operation(f"Adding category '{category}'"):
                add_category_to_config(category)
            cli.success(f"Category '{category}' added")

    if project and project not in get_available_projects():
        if cli.enhanced_confirm(f"Create new project '{project}'?"):
            with cli.loading_operation(f"Adding project '{project}'"):
                add_project_to_config(project)
            cli.success(f"Project '{project}' added")

    with cli.thinking("Checking for active sessions"):
        active = time_repository.get_active_time_entry()
        if active:
            duration = cli.format_relative_time(active.start)
            cli.warning(
                f"Already tracking: '{active.title}' (started {duration})")

            if not cli.enhanced_confirm("Stop current session and start new one?", default=False):
                cli.info("Keeping current session active")
                return

            with cli.loading_operation("Stopping current session"):
                time_repository.stop_active_time_entry(now)

    start_dt = parse_date_string(past, now=now) if past else now

    tag_str = ",".join(tags) if tags else None
    note_str = " ".join(notes) if notes else None
    data = {
        "title": title,
        "start": start_dt.isoformat() if isinstance(start_dt, datetime) else start_dt,
        "category": category,
        "project": project,
        "tags": tag_str,
        "notes": note_str,
    }

    time_repository.start_time_entry(data)

    summary_data = {
        "Activity": title,
        "Category": category or "None",
        "Project": project or "None",
        "Tags": ", ".join(tags) if tags else "None",
        "Started": start_dt.strftime("%H:%M:%S")
    }

    cli.success(f"Started tracking: '{title}'")
    cli.display_summary_card("Time Tracking Session", summary_data)


@app.command("stop")
@with_operation_header("Stopping Time Tracking", "Finalize current tracking session")
@database_operation("Stop Time Entry")
def stop(
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."
    ),
):
    """
    ⏹️ Stop the current timer and record the time block with enhanced feedback.
    """
    now = now_utc()

    with cli.thinking("Processing arguments"):
        try:
            tags, notes = parse_args(args or [])
        except ValueError as e:
            cli.error(f"Error parsing arguments: {e}")
            raise typer.Exit(code=1)

    with cli.thinking("Checking for active session"):
        active = time_repository.get_active_time_entry()
        if not active:
            cli.warning("No active time tracking session found")
            cli.info(
                "Ready to start tracking whenever you are! Use 'llog time start' to begin.")
            return

    if active.start:
        current_duration = (now - active.start).total_seconds() / 60
        duration_display = cli.format_duration(current_duration)
        cli.info(f"Current session: '{active.title}' ({duration_display})")

    end_time = parse_date_string(past, now=now) if past else now

    with cli.loading_operation("Finalizing time entry", "Time entry completed"):
        updated = time_repository.stop_active_time_entry(
            end_time=end_time,
            tags=",".join(tags) if tags else None,
            notes=" ".join(notes) if notes else None
        )

    distracted = updated.distracted_minutes or 0
    if updated.start and updated.end:
        total_minutes = (updated.end - updated.start).total_seconds() / 60
    else:
        total_minutes = 0
    actual_minutes = max(0, total_minutes - distracted)

    session_data = {
        "Activity": updated.title,
        "Category": updated.category or "None",
        "Project": updated.project or "None",
        "Total Time": cli.format_duration(total_minutes),
        "Focused Time": cli.format_duration(actual_minutes),
        "Distracted Time": cli.format_duration(distracted),
        "Efficiency": f"{(actual_minutes/total_minutes*100):.1f}%" if total_minutes > 0 else "N/A"
    }

    cli.success(
        f"Session completed: {cli.format_duration(total_minutes)} on '{updated.title}'")
    cli.display_summary_card("Time Tracking Summary", session_data)

    if total_minutes >= 60:
        cli.info("🏆 Great focus! You completed a substantial work session.")
    elif total_minutes >= 25:
        cli.info("✨ Nice work! That's a solid pomodoro session.")
    else:
        cli.info("🌱 Every minute you invest matters. Nice work!")


@app.command("status")
@database_operation("Check Status", show_performance=False)
def status():
    """
    📊 Show current time tracking status with enhanced display.
    """
    with cli.thinking("Checking time tracking status"):
        active = time_repository.get_active_time_entry()

    if not active:
        cli.info("⏸️ No active time tracking session")
        cli.info(
            "Ready to start tracking! Use 'llog time start <activity>' to begin.")
        return

    now = now_utc()
    if active.start:
        current_duration = (now - active.start).total_seconds() / 60
        duration_display = cli.format_duration(current_duration)
        time_ago = cli.format_relative_time(active.start)
    else:
        duration_display = "Unknown"
        time_ago = "Unknown"

    session_data = {
        "Activity": active.title,
        "Category": active.category or "None",
        "Project": active.project or "None",
        "Duration": duration_display,
        "Started": time_ago,
        "Tags": active.tags or "None"
    }

    cli.success(f"⏱️ Currently tracking: '{active.title}'")
    cli.display_summary_card("Active Session", session_data)

    if current_duration >= 90:
        cli.info("💡 Consider taking a break - you've been focused for a while!")
    elif current_duration >= 25:
        cli.info("🍅 You're in a great flow state! Keep it up.")


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
    now = now_utc()
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
        since = now - timedelta(days=365)

    try:
        history = time_repository.get_all_time_logs(since=since)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch time logs: {e}[/bold red]")
        raise typer.Exit(code=1)

    if not history:
        console.print("[italic]No time tracking history found yet![/italic]")
        return

    valid_fields = {"title", "category", "project"}
    if by not in valid_fields:
        console.print(
            f"[bold red]Invalid group field '{by}'. Choose title, category, or project.[/bold red]")
        raise typer.Exit(code=1)

    totals = {}
    distracted_totals = {}
    for record in history:
        key = getattr(record, by, None) or "(none)"
        duration = record.duration_minutes or 0
        distracted = record.distracted_minutes or 0
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
    now = now_utc()
    try:
        duration_td = parse_offset_to_timedelta(duration)
        mins = int(duration_td.total_seconds() / 60)
    except ValueError:
        console.print(f"[bold red]Invalid duration: {duration}[/bold red]")
        console.print("[dim]Examples: '5m', '1h', '30'[/dim]")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()
    note_str = notes if notes else None

    if active:
        try:
            new_distracted = time_repository.add_distracted_minutes_to_active(
                mins)
        except Exception as e:
            console.print(
                f"[bold red]Failed to update distracted minutes: {e}[/bold red]")
            raise typer.Exit(code=1)

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
