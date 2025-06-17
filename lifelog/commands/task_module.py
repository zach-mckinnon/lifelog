# lifelog/commands/task.py
'''
Lifelog Task Management Module
This module provides functionality to create, modify, delete, and manage tasks within the Lifelog application.
It includes features for tracking time spent on tasks, setting reminders, and managing task recurrence.
'''
from dataclasses import asdict

from datetime import datetime, timedelta
import re
import platform
import select
from shlex import quote
import shutil
import subprocess
import sys
import termios
import time
import tty
import typer
import json
from datetime import datetime, timedelta
from typing import List, Optional
import plotext as plt

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
import calendar


from lifelog.utils.db.models import Task, get_task_fields
from lifelog.utils.db import task_repository, time_repository
from lifelog.utils.shared_utils import add_category_to_config, add_project_to_config, add_tag_to_config, calculate_priority, format_datetime_for_user, format_due_for_display, get_available_categories, get_available_projects, get_available_tags, now_local, now_utc, parse_date_string, create_recur_schedule, parse_args, parse_offset_to_timedelta, utc_iso_to_local, validate_task_inputs
import lifelog.config.config_manager as cf
from lifelog.config.schedule_manager import IS_POSIX, apply_scheduled_jobs, build_linux_notifier, build_windows_notifier, save_config
from lifelog.utils.shared_options import category_option, project_option, due_option, impt_option, recur_option, past_option
from lifelog.utils.get_quotes import get_feedback_saying
from lifelog.utils.hooks import run_hooks


app = typer.Typer(help="Create and manage your personal tasks.")

console = Console()

MAX_TASKS_DISPLAY = 50

# Add a new task.


@app.command()
def add(
    title: str = typer.Argument(...,
                                help="The title of the task you need to get done."),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    importance: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[bool] = recur_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Add a new task.
    """
    now = now_local()
    tags, notes = [], []
    if args:
        try:
            tags, notes = parse_args(args)
            for tag in tags:
                if tag and tag not in get_available_tags():
                    add_tag_to_config(tag)
        except ValueError as e:
            console.print(f"[error]{e}[/error]")
            raise typer.Exit(code=1)
        except ValueError as e:
            console.print(f"[error]{e}[/error]")
            raise typer.Exit(code=1)

    # Validate and set up recurrence fields
    if category and category not in get_available_categories():
        if typer.confirm(f"Category '{category}' not in your config. Add it?"):
            add_category_to_config(category)
    if project and project not in get_available_projects():
        if typer.confirm(f"Project '{project}' not in your config. Add it?"):
            add_project_to_config(project)

    recur_interval = None
    recur_unit = None
    recur_days_of_week = None
    recur_base = None
    if recur:
        try:
            recur_data = create_recur_schedule("interactive")
            recur_interval = recur_data["interval"]
            recur_unit = recur_data["unit"]
            if "days_of_week" in recur_data:
                import json
                recur_days_of_week = json.dumps(recur_data["days_of_week"])
            recur_base = now.isoformat()
        except Exception as e:
            console.print(
                f"[bold red]❌ Invalid recurrence setup: {e}[/bold red]")
            raise typer.Exit(code=1)

    due_dt = None
    if due:
        while True:
            try:
                due_dt = parse_date_string(due, future=True, now=now)
                break
            except Exception as e:
                console.print(f"[bold red]❌ Invalid due date: {e}[/bold red]")
                if not Confirm.ask("[cyan]Enter a new date?[/cyan]"):
                    raise typer.Exit(code=1)
                due = typer.prompt(
                    "Enter a valid due date (e.g. 1d, tomorrow, 2025-12-31)")

    # Build data dict using model fields, ignoring extras
    task_data = {
        "title": title,
        "project": project,
        "category": category,
        "importance": importance if importance else 3,
        "created": now.isoformat(),
        "due": due_dt.isoformat() if due_dt else None,
        "status": "backlog",
        "priority": 0,  # calculated next
        "recur_interval": recur_interval,
        "recur_unit": recur_unit,
        "recur_days_of_week": recur_days_of_week,
        "recur_base": recur_base,
        "tags": ",".join(tags) if tags else None,
        "notes": " ".join(notes) if notes else None,
    }
    # Calculate and set priority
    task_data["priority"] = calculate_priority(task_data)

    # Validate and create Task instance (model-level validation)
    try:
        task = Task(**{k: task_data[k]
                    for k in get_task_fields() if k in task_data})
    except Exception as e:
        console.print(f"[bold red]❌ Error: {e}[/bold red]")
        raise typer.Exit(code=1)
    try:
        validate_task_inputs(
            title=title,
            importance=importance,
        )

    except Exception as e:
        console.print(f"[bold red]❌ {e}[/bold red]")
        raise typer.Exit(code=1)
    # Save using repository (already generic)
    try:
        task_repository.add_task(task)
        run_hooks("task", "created", task)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to save task: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]✅ Task added[/green]: [bold blue]{title}[/bold blue]")
    if due_dt:
        if Confirm.ask("Would you like to set a reminder before due?"):
            # Prompt for offset
            offset_str = typer.prompt(
                "How long before due for reminder? (e.g. '1d', '2h', '120')",
                type=str
            ).strip()
            if offset_str:
                try:
                    # Use the updated create_due_alert that accepts offset_str
                    create_due_alert(task, offset_str)
                except Exception as e:
                    console.print(
                        f"[bold red]❌ Could not set reminder: {e}[/bold red]")
                    # Not fatal; continue
                else:
                    console.print(
                        f"[green]✅ Reminder set {offset_str} before due.[/green]")
    console.print(get_feedback_saying("task_added"))


@app.command()
def list(
    title: Optional[str] = typer.Argument(
        "", help="Search by task title contains"),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    importance: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    sort: Optional[str] = typer.Option(
        "priority", help="Sort by 'priority', 'due', 'created', 'id'."),
    status: Optional[str] = typer.Option(
        None, help="Filter by status (e.g. 'backlog', 'active', 'completed')."),
    show_completed: bool = typer.Option(
        False, help="Include completed tasks."),
    args: Optional[List[str]] = typer.Argument(
        None, help="(Ignored currently, tags filtering not yet in DB)")
):
    """
    List tasks using clean SQL filtering & sorting.
    """
    tasks = task_repository.query_tasks(
        title_contains=title,
        category=category,
        project=project,
        importance=importance,
        due_contains=due,
        status=status,
        show_completed=show_completed,
        sort=sort
    )

    if not tasks:
        console.print(
            "[italic blue]🧹 Nothing to do! Enjoy your day. 🌟[/italic blue]")
        return

    table = Table(
        show_header=True,
        box=None,
        pad_edge=False,
        collapse_padding=True,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("ID", justify="right", width=2)
    table.add_column("Title", overflow="ellipsis", min_width=8)
    table.add_column("Priority", width=3, overflow="ellipsis")
    table.add_column("Due", style="yellow", width=8, overflow="ellipsis")

    for task in tasks:
        id_str = str(task.id)
        title_str = task.title
        due_raw = task.due
        due_str = "-"
        if due_raw:
            # If it's already a datetime, convert to ISO; else assume it's a string
            iso = due_raw.isoformat() if isinstance(due_raw, datetime) else due_raw
            due_str = format_due_for_display(iso)

        prio = str(task.priority)
        color = priority_color(prio)
        prio_text = Text(prio)
        prio_text.stylize(color)

        table.add_row(id_str, title_str, prio_text, due_str)

    console.print(table)


@app.command()
def agenda():
    """
    📅 View your calendar and top priority tasks side-by-side.
    """
    now = now_utc()

    # --- Get all non-completed tasks sorted by priority descending ---
    tasks = task_repository.query_tasks(
        show_completed=False,
        sort="priority"
    )

    if not tasks:
        console.print(
            "[italic blue]🧹 No upcoming tasks. Enjoy your day! 🌟[/italic blue]")
        return

    # --- Build the calendar view ---
    calendar_panel = build_calendar_panel(now, tasks)

    # --- Select top 3 by priority DESC and due ASC (already sorted by SQL) ---
    def sort_key(t):
        due_dt = datetime.fromisoformat(t.due) if t.due else datetime.max
        return due_dt

    top_three = sorted(tasks, key=sort_key)[:3]

    # --- Build compact task table ---
    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=None,
        pad_edge=False,
        collapse_padding=True,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("ID", justify="right", width=2)
    table.add_column("P", justify="center", width=1)
    table.add_column("Due", justify="center", width=5)
    table.add_column("Task", overflow="ellipsis", min_width=8)

    for task in top_three:
        id_str = str(task.id)
        prio_raw = task.priority
        prio_text = Text(str(prio_raw), style=priority_color(prio_raw))
        due_str = "-"
        if task.due:
            iso = task.due.isoformat() if isinstance(task.due, datetime) else task.due
            due_str = format_due_for_display(iso)
        title = task.title or "-"

        table.add_row(id_str, prio_text, due_str, title)

    # --- Render views side by side ---
    console.print(calendar_panel)
    console.print(table)


# Get information on a task TO DO: Make the ability to just say llog task task# to get info.
@app.command()
def info(id: int):
    """
    Show full details for a task.
    """
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    console.rule(f"📋 Task Details [ID {id}]")
    for key in get_task_fields():
        value = getattr(task, key, "-")
        if value is None or str(value).strip() == "":
            value = "-"
        console.print(f"[bold blue]{key.capitalize()}:[/bold blue] {value}")


# Start tracking a task (Like moving to in-progress)


@app.command()
def start(id: int):
    """
    Start or resume a task. Only one task can be tracked at a time.
    """
    now = now_utc()
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    # Assuming Task.status is a string or Enum; compare accordingly
    if getattr(task, "status", None) not in ["backlog", "active"]:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Task [[bold blue]{id}[/bold blue]] is not in a startable state (backlog or active only).")
        raise typer.Exit(code=1)

    # Check if another time log is already running
    active_entry = time_repository.get_active_time_entry()
    if active_entry:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Another time log is already running: {active_entry.title}")
        raise typer.Exit(code=1)

    # 1) Mark task as active in DB, set its start timestamp
    # Use ISO-format string for storage if the repository stores datetimes as ISO strings
    update_payload = {"status": "active", "start": now.isoformat()}
    task_repository.update_task(id, update_payload)
    # Optionally refresh the task object:
    task = task_repository.get_task_by_id(id)

    # 2) Start time tracking linked to the task.
    # Build a dict matching time_repository.start_time_entry signature:
    time_entry_data = {
        "title": task.title or "",
        "task_id": id,
        "start": now.isoformat(),
        "category": task.category,
        "project": task.project,
        "tags": task.tags,
        "notes": f"Started via task {id}",
    }
    try:
        time_repository.start_time_entry(time_entry_data)
    except Exception as e:
        console.print(
            f"[bold red]❌ Failed to start time entry: {e}[/bold red]")
        # Optionally roll back task status? For now, exit with error
        raise typer.Exit(code=1)

    run_hooks("task", "started", task)
    console.print(
        f"[green]▶️ Started[/green] task [bold blue][{id}][/bold blue]: {task.title}")


@app.command()
def modify(
    id: int = typer.Argument(..., help="The ID of the task to modify"),
    title: Optional[str] = typer.Option(None, help="New title"),
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional: +tags Notes..."),
    project: Optional[str] = project_option,
    category: Optional[str] = category_option,
    importance: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[bool] = recur_option,
):
    """
    Modify an existing task's fields. Only provide fields you want to update.
    """
    now = now_local()
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    tags, notes = [], []
    if args is not None:
        try:
            tags, notes = parse_args(args)
        except ValueError as e:
            console.print(f"[error]{e}[/error]")
            raise typer.Exit(code=1)

    updates = {}
    if title and title != task.title:
        updates["title"] = title
    if category and category != task.category:
        updates["category"] = category
    if project and project != task.project:
        updates["project"] = project
    if due:
        try:
            due_dt = parse_date_string(due, future=True, now=now)
            updates["due"] = due_dt.isoformat()
        except Exception as e:
            console.print(f"[bold red]❌ Invalid due date: {e}[/bold red]")
            raise typer.Exit(code=1)
    if importance is not None:
        updates["importance"] = importance
    if tags:
        updates["tags"] = ",".join(tags)
    if notes:
        updates["notes"] = " ".join(notes)
    if recur:
        try:
            recur_data = create_recur_schedule("interactive")
            updates["recur_interval"] = recur_data["interval"]
            updates["recur_unit"] = recur_data["unit"]
            if "days_of_week" in recur_data:
                import json
                updates["recur_days_of_week"] = json.dumps(
                    recur_data["days_of_week"])
            updates["recur_base"] = now.isoformat()
        except Exception as e:
            console.print(
                f"[bold red]❌ Recurrence setup failed: {e}[/bold red]")
            raise typer.Exit(code=1)

    # Priority recalc
    merged = asdict(task)
    merged.update(updates)
    try:
        updates["priority"] = calculate_priority(merged)
    except Exception as e:
        console.print(
            f"[yellow]⚠️ Could not recalculate priority: {e}[/yellow]")
        updates["priority"] = getattr(task, "priority", 1)

    if not updates:
        console.print("[yellow]⚠️ No changes were made.[/yellow]")
        raise typer.Exit(code=0)

    try:
        validate_task_inputs(
            title=updates.get("title", task.title),
            importance=updates.get("importance", task.importance),
        )

    except Exception as e:
        console.print(f"[bold red]❌ {e}[/bold red]")
        raise typer.Exit(code=1)

    task_repository.update_task(id, updates)
    updated_task = task_repository.get_task_by_id(id)
    run_hooks("task", "updated", updated_task)
    console.print(
        f"[green]✏️ Updated[/green] task [bold blue][{id}][/bold blue].")


@app.command()
def delete(id: int):
    """
    Delete a task by ID.
    """
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    task_repository.delete_task(id)
    console.print(
        f"[red]🗑️ Deleted[/red] task [bold blue][{id}][/bold blue]: {task.title}")


@app.command()
def stop(
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Pause the currently active task and stop timing, without marking it done.
    """
    now = now_utc()
    # parse_args returns lists; if args is None, treat as empty
    try:
        tags, notes = parse_args(args or [])
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    # Check if active time log exists
    active = time_repository.get_active_time_entry()
    if not active:
        console.print(
            "[yellow]⚠️ Warning[/yellow]: No active task is being tracked.")
        raise typer.Exit(code=1)

    # Use attribute access
    if not getattr(active, "task_id", None):
        console.print(
            "[yellow]⚠️ Warning[/yellow]: Active log is not linked to a task.")
        raise typer.Exit(code=1)

    task_id = active.task_id
    task = task_repository.get_task_by_id(task_id)
    if not task:
        console.print(
            "[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)

    # Determine end_time
    try:
        end_time = parse_date_string(past, now=now) if past else now
    except Exception as e:
        console.print(f"[bold red]❌ Invalid time: {e}[/bold red]")
        raise typer.Exit(code=1)

    # Stop the time log. pass datetime directly or ISO string:
    try:
        # time_repository.stop_active_time_entry accepts datetime
        updated_log = time_repository.stop_active_time_entry(
            end_time=end_time,
            tags=",".join(tags) if tags else None,
            notes=notes if notes else None
        )
    except Exception as e:
        console.print(f"[bold red]❌ Failed to stop timer: {e}[/bold red]")
        raise typer.Exit(code=1)

    # Update the task back to 'backlog'
    task_repository.update_task(task_id, {"status": "backlog"})

    # Compute duration: active.start is a datetime
    start_dt = getattr(active, "start", None)
    if isinstance(start_dt, datetime):
        duration_minutes = (end_time - start_dt).total_seconds() / 60
    else:
        duration_minutes = 0.0

    run_hooks("task", "stopped", task)
    console.print(
        f"[yellow]⏸️ Paused[/yellow] task [bold blue][{task.id}][/bold blue]: {task.title} — Duration: [cyan]{round(duration_minutes, 2)}[/cyan] minutes")


@app.command()
def done(id: int, past: Optional[str] = past_option, args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes.")):
    """
    Mark a task as completed.
    """
    now = now_utc()
    try:
        tags, notes = parse_args(args or [])
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()
    if not active:
        console.print("[yellow]⚠️ No active timer. No new log saved.[/yellow]")
        # Just mark task done directly
        task_repository.update_task(id, {"status": "done"})
        console.print(f"[green]✔️ Done[/green] [{id}]: {task.title}")
        run_hooks("task", "completed", task)
        return

    # Ensure active log belongs to this task
    if getattr(active, "task_id", None) != id:
        console.print(
            f"[bold red]❌ Error[/bold red]: Active log is not for task ID {id}.")
        raise typer.Exit(code=1)

    # Compute end_time
    try:
        end_time = parse_date_string(past, now=now) if past else now
    except Exception as e:
        console.print(f"[bold red]❌ Invalid time: {e}[/bold red]")
        raise typer.Exit(code=1)

    # Compute duration using active.start (a datetime)
    start_dt = getattr(active, "start", None)
    if isinstance(start_dt, datetime):
        duration = (end_time - start_dt).total_seconds() / 60
    else:
        duration = 0.0

    # Stop the active time log; pass datetime or ISO string
    try:
        time_repository.stop_active_time_entry(
            end_time=end_time,
            tags=",".join(tags) if tags else None,
            notes=notes if notes else None
        )
    except Exception as e:
        console.print(
            f"[bold red]❌ Failed to stop active time entry: {e}[/bold red]")
        raise typer.Exit(code=1)

    # Mark task as done
    task_repository.update_task(id, {"status": "done"})
    console.print(
        f"[green]✔️ Task Complete! [/green] task [bold blue]{task.title}[/bold blue] — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")
    console.print(get_feedback_saying("task_completed"))
    run_hooks("task", "completed", task)


def read_char_nonblocking(timeout: float = 1.0):
    """
    Read a single character from stdin without blocking for more than `timeout` seconds.
    Returns the character as a string, or None if no input is available within timeout.
    Works on Unix-like systems.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        # Set terminal to raw mode so we can read single chars
        tty.setcbreak(fd)
        # Use select to wait up to `timeout` seconds
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            ch = sys.stdin.read(1)
            return ch
        else:
            return None
    finally:
        # Restore terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


@app.command("focus")
def focus_cli(
    id: int = typer.Argument(..., help="The ID of the task to focus on"),
    pomodoro: bool = typer.Option(
        True, "--pomodoro/--no-pomodoro",
        help="Enable back-to-back Pomodoro cycles"
    ),
    focus_len: int = typer.Option(
        30, "--focus", "-f", min=1, help="Minutes per focus block"),
    break_len: int = typer.Option(
        5, "--break", "-b", min=1, help="Minutes per break block"),
):
    """
    Distraction-free CLI “focus mode” for a single task.
    Starts a time entry, guides you through Pomodoro (if enabled),
    lets you pause or mark done, and then stops the time entry.
    """
    # 1) Look up the task
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[red]❌ Task ID {id} not found.[/red]")
        raise typer.Exit(1)

    # 2) Start time entry if not already active for this task
    active = time_repository.get_active_time_entry()
    if not (active and getattr(active, "task_id", None) == id):
        now = now_utc()
        entry_data = {
            "title":   task.title or "",
            "task_id": id,
            "start":   now.isoformat(),
            "category": task.category,
            "project":  task.project,
            "notes":    "Focus mode start",
            # 'uid' will be auto-generated inside start_time_entry if missing
        }
        try:
            time_repository.start_time_entry(entry_data)
            run_hooks("task", "started", task)
            console.print(
                f"[green]▶️ Focus mode started for task {id}.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to start time entry: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[bold blue]Entering focus mode for:[/] {task.title}")
    console.print(
        "[dim]Commands: [p]ause & exit, [d]one & exit, [t]oggle Pomodoro on/off, [l]log distracted time[/dim]")

    total_distracted = 0  # in minutes
    in_break = False
    block_start = time.time()
    # Flag to indicate whether we are in a focus block or break block.
    # If pomodoro is False, we ignore in_break and simply run a continuous focus block.

    # Helper to compute elapsed seconds since block_start
    def block_elapsed():
        return int(time.time() - block_start)

    # Helper to display status line
    def show_status():
        te = block_elapsed()
        mm, ss = divmod(te, 60)
        status = "Break" if in_break else "Focus"
        # \r to return to start of line; end="" to avoid newline
        console.print(
            f"\r[{status}] {mm:02}:{ss:02} — total distracted: {total_distracted}m", end="")

    # Main loop: repeats roughly every second (via read_char_nonblocking timeout)
    try:
        while True:
            show_status()
            # Read single char, wait up to 1 second
            key = read_char_nonblocking(timeout=1.0)
            if key:
                # Normalize key to lowercase
                key = key.lower()
            # Handle keys:
            if key == "p":
                console.print("\n[yellow]⏸️ Pausing focus mode.[/yellow]")
                break  # exit loop and stop time entry
            elif key == "d":
                console.print("\n[green]✔️ Marking task done.[/green]")
                # Stop time entry
                try:
                    time_repository.stop_active_time_entry(
                        end_time=now_utc().isoformat())
                except Exception as e:
                    console.print(f"[red]Error stopping time entry: {e}[/red]")
                # Mark task done
                try:
                    task_repository.update_task(id, {"status": "done"})
                    run_hooks("task", "completed", task)
                except Exception as e:
                    console.print(
                        f"[red]Error updating task status: {e}[/red]")
                return  # exit command entirely
            elif key == "t":
                pomodoro = not pomodoro
                mode = "ON" if pomodoro else "OFF"
                console.print(f"\n[cyan]Pomodoro {mode}[/cyan]")
                # Reset block timing whenever toggled
                block_start = time.time()
                in_break = False
                continue
            elif key == "l":
                # Allow user to log extra distracted minutes at any time without ending the block
                console.print(
                    "\n[magenta]Log distracted time (minutes):[/magenta] ", end="")
                # Blocking prompt for minutes (user types number then Enter)
                extra = typer.prompt("", default="0")
                try:
                    lost = int(extra)
                except ValueError:
                    lost = 0
                total_distracted += lost
                console.print(
                    f"[magenta]Added {lost}m distracted. Total now: {total_distracted}m[/magenta]")
                # Continue without resetting block timer
                continue

            # Pomodoro behavior: only if enabled
            if pomodoro:
                # Determine current block limit in seconds
                limit = break_len * 60 if in_break else focus_len * 60
                if block_elapsed() >= limit:
                    # Block complete
                    if in_break:
                        console.print(
                            "\n[green]✨ Break over — back to focus.[/green]")
                    else:
                        console.print("\n[cyan]⏰ Focus block complete![/cyan]")
                        # Prompt for distracted minutes now
                        extra = typer.prompt(
                            "Distracted minutes?", default="0")
                        try:
                            lost = int(extra)
                        except ValueError:
                            lost = 0
                        total_distracted += lost
                        run_hooks("task", "pomodoro_done", task)
                    # Flip mode and reset timer
                    in_break = not in_break
                    block_start = time.time()
            # If Pomodoro disabled, we do nothing special here (continuous focus).
            # Loop repeats after ~1 second.
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted by user. Exiting focus mode.[/yellow]")
    finally:
        # 3) Stop time entry when exiting focus mode (unless already stopped by “done”)
        try:
            time_repository.stop_active_time_entry(
                end_time=now_utc().isoformat())
            run_hooks("task", "stopped", task)
            console.print("[yellow]🔒 Focus mode exited.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error stopping time entry on exit: {e}[/red]")


@app.command()
def burndown():
    """
    📉 Remaining Task Burndown Over the Next N Days.
    Shows:
      - Actual Tasks Open
      - Ideal Burn Line
      - Overdue Count
      - Completions per Day
    """

    try:
        # Attempt to get tasks with error handling
        try:
            tasks = task_repository.get_all_tasks()
        except Exception as e:
            console.print(f"[red]Error fetching tasks: {e}[/red]")
            console.print("[yellow]Using empty task list[/yellow]")
            tasks = []

        now = now_utc()
        start_date = now - timedelta(days=2)
        end_date = now + timedelta(days=3)

        # Generate date range with error handling
        try:
            all_dates = []
            date_objs = []
            current_date = start_date
            while current_date <= end_date:
                all_dates.append(current_date.strftime('%Y-%m-%d'))
                date_objs.append(current_date)
                current_date += timedelta(days=1)
        except Exception as e:
            console.print(f"[red]Error generating date range: {e}[/red]")
            return

        # Initialize metrics arrays safely
        open_counts = []
        overdue_counts = []
        completed_per_day = []
        added_per_day = []

        # Calculate open tasks count safely
        try:
            open_now = sum(1 for t in tasks if t and getattr(
                t, 'status', None) != "done")
            total_days = len(all_dates) if all_dates else 1
            ideal_per_day = open_now / \
                (total_days - 1) if total_days > 1 else open_now
        except Exception as e:
            console.print(f"[red]Error calculating task metrics: {e}[/red]")
            return

        # Process tasks for each date safely
        for i, dstr in enumerate(all_dates):
            try:
                date_obj = date_objs[i]
                not_done_count = 0
                overdue_count = 0
                completed_today = 0
                added_today = 0

                for task in tasks:
                    if not task:
                        continue

                    # Safely get task attributes
                    status = getattr(task, 'status', '')
                    due = getattr(task, 'due', None)
                    completed = getattr(task, 'completed_at', None)
                    created = getattr(task, 'created_at', None)

                    # Process due date
                    if due and status != "done":
                        try:
                            due_date = datetime.fromisoformat(due)
                            if due_date.date() <= date_obj.date():
                                not_done_count += 1
                            if due_date.date() < now.date() and date_obj.date() >= now.date():
                                overdue_count += 1
                        except (ValueError, TypeError) as e:
                            console.print(
                                f"[yellow]Warning: Unable to parse date for task. Some task stats may be incomplete. Details: {str(e)}[/yellow]")

                    # Process completed tasks
                    if completed:
                        try:
                            completed_date = datetime.fromisoformat(
                                completed).date()
                            if completed_date == date_obj.date():
                                completed_today += 1
                        except (ValueError, TypeError) as e:
                            console.print(
                                f"[yellow]Warning: Unable to parse date for task. Some task stats may be incomplete. Details: {str(e)}[/yellow]")

                    # Process created tasks
                    if created:
                        try:
                            created_date = datetime.fromisoformat(
                                created).date()
                            if created_date == date_obj.date():
                                added_today += 1
                        except (ValueError, TypeError) as e:
                            console.print(
                                f"[yellow]Warning: Unable to parse date for task. Some task stats may be incomplete. Details: {str(e)}[/yellow]")

                open_counts.append(not_done_count)
                overdue_counts.append(overdue_count)
                completed_per_day.append(completed_today)
                added_per_day.append(added_today)

            except Exception as e:
                console.print(f"[red]Error processing date {dstr}: {e}[/red]")
                # Push placeholder values to maintain array sizes
                open_counts.append(0)
                overdue_counts.append(0)
                completed_per_day.append(0)
                added_per_day.append(0)

        # Generate ideal line safely
        try:
            ideal_line = [max(0, int(round(open_now - ideal_per_day * i)))
                          for i in range(total_days)]
        except Exception as e:
            console.print(f"[red]Error generating ideal line: {e}[/red]")
            ideal_line = []

        # Format dates for plotting
        try:
            plot_dates = [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d")
                          for d in all_dates]
        except Exception as e:
            console.print(f"[red]Error formatting dates: {e}[/red]")
            plot_dates = []

        # Generate plot with comprehensive error handling
        try:
            plt.clf()
            plt.theme("matrix")
            plt.title("Task Burndown")

            if plot_dates and open_counts:
                plt.plot(plot_dates, open_counts,
                         marker="*", label="Tasks Left")
            if plot_dates and ideal_line:
                plt.plot(plot_dates, ideal_line,
                         marker=".", label="Ideal Burn")
            if plot_dates and overdue_counts:
                plt.plot(plot_dates, overdue_counts, marker="!",
                         label="Overdue", color="red")
            if plot_dates and completed_per_day:
                plt.scatter(plot_dates, completed_per_day, marker="o",
                            label="Completed/Day", color="green")
            if plot_dates and added_per_day:
                plt.scatter(plot_dates, added_per_day, marker="+",
                            label="Added/Day", color="yellow")

            plt.xlabel("Date")
            plt.ylabel("Count")
            plt.legend()
            plt.show()
        except Exception as e:
            console.print(f"[red]Error generating plot: {e}[/red]")
            console.print("[yellow]Showing summary instead[/yellow]")

        # Display summary metrics safely
        try:
            console.print(
                f"[bold]Open now:[/] {open_counts[-1] if open_counts else 'N/A'}   "
                f"[bold]Overdue now:[/] {overdue_counts[-1] if overdue_counts else 'N/A'}"
            )
            console.print(
                f"[bold]Completed in window:[/] {sum(completed_per_day)}   "
                f"[bold]Added in window:[/] {sum(added_per_day)}"
            )
            if total_days > 1:
                avg_completion = sum(completed_per_day) / (total_days-1)
                console.print(
                    f"[bold]Avg completed/day:[/] {avg_completion:.2f}")
        except Exception as e:
            console.print(f"[red]Error displaying summary: {e}[/red]")

    except Exception as e:
        console.print(
            f"[bold red]Unexpected error in burndown command:[/bold red]")
        console.print(f"[red]{e}[/red]")
        console.print(
            "[yellow]Please check your task data and try again[/yellow]")


def build_calendar_panel(now: datetime, tasks: list) -> Panel:
    """Build a calendar panel showing the current month with due dates highlighted."""
    cal = calendar.TextCalendar(firstweekday=0)
    month_str = cal.formatmonth(now.year, now.month)

    # gather days_of_week to highlight
    due_days = {
        datetime.fromisoformat(t.due).day
        for t in tasks
        if t.get("due")
        and datetime.fromisoformat(t.due).month == now.month
        and datetime.fromisoformat(t.due).year == now.year
    }

    def highlight_month(text: str, due_days: set, today: int) -> Text:
        plain_text = text  # Do NOT modify this in place
        styled = Text(plain_text)
        for match in re.finditer(r'\b(\d{1,2})\b', plain_text):
            day = int(match.group(1))
            if day in due_days:
                style = "reverse" if day == today else "on blue"
                styled.stylize(style, match.start(), match.end())
        return styled

    cal_text = highlight_month(month_str, due_days, now.day)
    return Panel(cal_text, border_style="#7d00ff", expand=False)


@app.command("auto_recur")
def auto_recur():
    """
    Check all recurring tasks and create new instances if due.
    """
    tasks = task_repository.get_all_tasks()
    now = now_utc()
    today_weekday = now.weekday()
    new_tasks_count = 0

    for task in tasks:
        recur_interval = task.recur_interval
        recur_unit = task.recur_unit
        recur_base = task.recur_base
        recur_days_of_week = task.recur_days_of_week

        if not (recur_interval and recur_unit and recur_base):
            continue

        base_dt = datetime.fromisoformat(recur_base)
        interval = recur_interval
        unit = recur_unit
        days_of_week = json.loads(
            recur_days_of_week) if recur_days_of_week else []

        should_recur = False

        if unit == "day":
            days_since = (now.date() - base_dt.date()).days
            if days_since > 0 and days_since % interval == 0:
                should_recur = True
        elif unit == "week":
            days_since = (now.date() - base_dt.date()).days
            if days_since > 0:
                weeks_since = days_since // 7
                if days_of_week:
                    if weeks_since % interval == 0 and today_weekday in days_of_week:
                        should_recur = True
                else:
                    if days_since % (interval * 7) == 0:
                        should_recur = True
        elif unit == "month":
            months_since = (now.year - base_dt.year) * \
                12 + (now.month - base_dt.month)
            if months_since % interval == 0 and now.day == base_dt.day:
                should_recur = True
        elif unit == "year":
            years_since = now.year - base_dt.year
            if years_since > 0 and now.month == base_dt.month and now.day == base_dt.day:
                should_recur = True

        if should_recur:
            new_task_data = clone_task_for_db(task, now)
            task_repository.add_task(new_task_data)
            task_repository.update_task(
                task.id, {"recur_base": now.isoformat()})
            new_tasks_count += 1

    if new_tasks_count:
        console.print(
            f"[green]🔁 Recreated {new_tasks_count} recurring task(s).[/green]")
    else:
        console.print("[cyan]ℹ️ No recurring tasks needed today.[/cyan]")


def clone_task_for_db(task, now):
    """
    Clone task for SQL-based insertion.
    """
    new_due = None
    if task.due and task.created:
        try:
            due_dt = datetime.fromisoformat(task.due)
            created_dt = datetime.fromisoformat(task.created)
            offset = due_dt - created_dt
            new_due = (now + offset).replace(microsecond=0).isoformat()
        except Exception:
            new_due = None

    return Task(
        title=task.title,
        project=task.project,
        category=task.category,
        importance=task.importance if hasattr(task, "importance") else 1,
        created=now.replace(hour=0, minute=0, second=0,
                            microsecond=0).isoformat(),
        due=new_due,
        status="backlog",
        start=None,
        end=None,
        priority=0,
        recur_interval=task.recur_interval,
        recur_unit=task.recur_unit,
        recur_days_of_week=task.recur_days_of_week,
        recur_base=now.isoformat(),
        tags=task.tags,
        notes=task.notes
    )


def get_due_color(due_str: str, now: datetime) -> str:
    """
    Returns a color string based on how close the due time is to 'now'.
    """
    try:
        due_dt = datetime.fromisoformat(due_str)
    except ValueError:
        return "white"  # Default color if parsing fails

    delta = due_dt - now
    if delta.total_seconds() < 0:
        return "#700000"  # Overdue
    elif delta <= timedelta(minutes=30):
        return "#ff0000"
    elif delta <= timedelta(hours=1):
        return "#ff3636"
    elif delta <= timedelta(hours=3):
        return "#ff7373"
    elif delta <= timedelta(hours=6):
        return "#fa9898"
    else:
        return "white"


def priority_color(priority_value):
    priority_as_int = float(priority_value)
    if priority_as_int >= 20.0:
        return "red"
    elif priority_as_int >= 15.0:
        return "orange3"
    elif priority_as_int >= 10.0:
        return "yellow"
    elif priority_as_int >= 5.0:
        return "green3"
    else:
        return "blueviolet"

# Calculate the priority using an Eisenhower Matrix.


def parse_due_offset(due_str):
    # Expected format: '+5dT18:00'
    if due_str.startswith("+") and "T" in due_str:
        try:
            days_of_week_part, time_part = due_str[1:].split("T")
            days_of_week = int(days_of_week_part.rstrip("d"))
            hour, minute = map(int, time_part.split(":"))
            return timedelta(days_of_week=days_of_week, hours=hour, minutes=minute)
        except Exception as e:
            console.print(
                f"[yellow]Could not parse due offset '{due_str}'. Using default of 1 day. Details: {str(e)}[/yellow]")

    return timedelta(days_of_week=1)  # default fallback


def create_due_alert(task: Task, offset_str: str):
    """
    Schedule a one-off reminder for `task` at (due_local_time - offset).
    On POSIX: uses `at` if available, else falls back to cron via schedule_manager.
    On Windows: uses schtasks.exe to run a PowerShell modal + sound.
    """
    # — 1) Parse and normalize the due time into a LOCAL-TZ aware datetime
    if not task.due:
        raise ValueError("Task has no due date")

    # Parse ISO → aware UTC → to user's local TZ
    due_local: datetime = utc_iso_to_local(task.due)
    # — 2) Compute alert time
    offset = parse_offset_to_timedelta(offset_str)
    alert_local = due_local - offset

    now_l = now_local()
    if alert_local < now_l:
        console.print(
            f"[yellow]⚠️ Reminder time {alert_local.strftime('%Y-%m-%d %H:%M')} is in the past. Scheduling immediately.[/yellow]"
        )
        alert_local = now_l + timedelta(seconds=5)

    # Build the textual message
    msg = f"Reminder: Task [{task.id}] \"{task.title}\" is due at {due_local.strftime('%Y-%m-%d %H:%M')}"

    system = platform.system()
    if system in ("Linux", "Darwin"):
        # POSIX
        notifier = build_linux_notifier(msg)

        if shutil.which("at"):
            # format for at: "HH:MM YYYY-MM-DD"
            at_time = alert_local.strftime("%H:%M %m/%d/%Y")
            # e.g. echo "<notifier>" | at 15:30 06/20/2025
            full = f"echo {quote(notifier)} | at {at_time}"
            subprocess.run(["bash", "-lc", full], check=True)
            console.print(
                f"[green]✅ Reminder scheduled via at at {alert_local.strftime('%Y-%m-%d %H:%M')}[/green]"
            )
        else:
            # fallback to cron entries
            from lifelog.config.schedule_manager import save_config, apply_scheduled_jobs
            import lifelog.config.config_manager as cf
            cfg = cf.load_config()
            name = f"task_due_{task.id}"
            entry = {
                "schedule": f"{alert_local.minute} {alert_local.hour} {alert_local.day} {alert_local.month} *",
                "command": notifier
            }
            cron_sec = cfg.get("cron", {})
            cron_sec[name] = entry
            cfg["cron"] = cron_sec
            if not save_config(cfg):
                raise RuntimeError("Failed to save cron reminder")
            ok = apply_scheduled_jobs()
            if ok:
                console.print(
                    f"[green]✅ Reminder scheduled at {alert_local.strftime('%Y-%m-%d %H:%M')}[/green]")
            else:
                console.print(
                    f"[yellow]⚠️ Could not schedule via cron – you may need to `crontab -l` or run with sudo[/yellow]"
                )

    elif system == "Windows":
        # Windows Scheduled Task
        # Build our PowerShell one-liner
        ps_cmd = build_windows_notifier(msg)
        name = f"Lifelog_task_due_{task.id}"
        # delete any existing
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # format
        date_str = alert_local.strftime("%m/%d/%Y")
        time_str = alert_local.strftime("%H:%M")
        sch = [
            "schtasks", "/Create",
            "/SC", "ONCE",
            "/TN", name,
            "/TR", " ".join(ps_cmd),
            "/ST", time_str,
            "/SD", date_str,
            "/RL", "HIGHEST",
            "/F"
        ]
        subprocess.run(sch, check=True)
        console.print(
            f"[green]✅ Reminder scheduled via Windows Task Scheduler at {alert_local.strftime('%Y-%m-%d %H:%M')}[/green]"
        )

    else:
        raise RuntimeError(f"Unsupported OS for reminders: {system}")


def clear_due_alert(task):
    if IS_POSIX:
        doc = cf.load_config()
        cron_section = doc.get("cron", {})
        name = f"task_due_{task.id}"
        if name in cron_section:
            del cron_section[name]
            doc["cron"] = cron_section
            save_config(doc)
            apply_scheduled_jobs()
            console.print(
                f"[green]✅ Reminder cleared for task {task.id}[/green]")
        else:
            console.print(
                f"[yellow]No reminder found for task {task.id}[/yellow]")
    else:
        name = f"Lifelog_task_due_{task.id}"
        try:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", name, "/F"], check=False)
            console.print(
                f"[green]✅ Reminder cleared for task {task.id}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to clear reminder: {e}[/red]")
