# lifelog/commands/task.py
'''
Lifelog Task Management Module
This module provides functionality to create, modify, delete, and manage tasks within the Lifelog application.
It includes features for tracking time spent on tasks, setting reminders, and managing task recurrence.
'''
import sys
from lifelog.utils.hooks import run_hooks
from lifelog.utils.get_quotes import get_feedback_saying
from lifelog.utils.shared_options import category_option, project_option, due_option, impt_option, recur_option, past_option
from lifelog.config.schedule_manager import IS_POSIX, apply_scheduled_jobs, build_linux_notifier, build_windows_notifier, save_config
import lifelog.config.config_manager as cf
from lifelog.utils.shared_utils import add_category_to_config, add_project_to_config, add_tag_to_config, calculate_priority, format_datetime_for_user, format_due_for_display, get_available_categories, get_available_projects, get_available_tags, now_local, parse_date_string, create_recur_schedule, parse_args, parse_offset_to_timedelta, utc_iso_to_local, validate_task_inputs
from lifelog.utils.db import task_repository, time_repository
from lifelog.utils.db.models import Task, get_task_fields
import calendar
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.text import Text
from lifelog.utils.cli_decorators import (
    with_loading, with_operation_header, database_operation,
    interactive_command, with_performance_monitoring, multi_step_command
)
from lifelog.utils.cli_enhanced import cli
from rich.layout import Layout
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.prompt import Confirm
from rich.console import Console
import select
import time
from dataclasses import asdict

from datetime import datetime, timedelta, timezone
import re
import platform
from shlex import quote
import shutil
import subprocess
try:
    import termios
    import tty
    HAS_TERMIOS = True
except ImportError:
    termios = None
    tty = None
    HAS_TERMIOS = False
import typer
import json
from datetime import datetime, timedelta
from typing import List, Optional
_plt = None


def get_plotext():
    """Lazy load plotext only when needed for charts"""
    global _plt
    if _plt is None:
        import plotext as plt
        _plt = plt
    return _plt


# For Windows:
try:
    import msvcrt
except ImportError:
    msvcrt = None


app = typer.Typer(help="Create and manage your personal tasks.")

console = Console()

MAX_TASKS_DISPLAY = 50


@app.command()
@with_operation_header("Adding New Task", "Create and configure task with validation")
@database_operation("Add Task")
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
    ✨ Add a new task with enhanced validation and feedback.
    """
    now = now_local()
    tags, notes = [], []

    if args:
        with cli.thinking("Parsing task arguments"):
            try:
                tags, notes = parse_args(args)
                for tag in tags:
                    if tag and tag not in get_available_tags():
                        with cli.loading_operation(f"Adding tag '{tag}'"):
                            add_tag_to_config(tag)
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

    task_data = {
        "title": title,
        "project": project,
        "category": category,
        "importance": importance if importance else 3,
        "created": now.isoformat(),
        "due": due_dt.isoformat() if due_dt else None,
        "status": "backlog",
        "priority": 0,  # calculated
        "recur_interval": recur_interval,
        "recur_unit": recur_unit,
        "recur_days_of_week": recur_days_of_week,
        "recur_base": recur_base,
        "tags": ",".join(tags) if tags else None,
        "notes": " ".join(notes) if notes else None,
    }
    task_data["priority"] = calculate_priority(task_data)

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
    try:
        task_repository.add_task(task)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to save task: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]✅ Task added[/green]: [bold blue]{title}[/bold blue]")
    if due_dt:
        if Confirm.ask("Would you like to set a reminder before due?"):
            offset_str = typer.prompt(
                "How long before due for reminder? (e.g. '1d', '2h', '120')",
                type=str
            ).strip()
            if offset_str:
                try:
                    create_due_alert(task, offset_str)
                except Exception as e:
                    console.print(
                        f"[bold red]❌ Could not set reminder: {e}[/bold red]")
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
    now = now_local()

    tasks = task_repository.query_tasks(
        show_completed=False,
        sort="priority"
    )

    if not tasks:
        console.print(
            "[italic blue]🧹 No upcoming tasks. Enjoy your day! 🌟[/italic blue]")
        return

    calendar_panel = build_calendar_panel(now, tasks)

    def sort_key(t):
        if t.due:
            return t.due
        else:
            return datetime.max.replace(tzinfo=timezone.utc)

    top_three = sorted(tasks, key=sort_key)[:3]

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

    console.print(calendar_panel)
    console.print(table)


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


@app.command()
def start(id: int):
    """
    Start or resume a task. Only one task can be tracked at a time.
    """
    now = now_local()
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    status = getattr(task, "status", None)
    if hasattr(status, 'value'):
        status_val = status.value
    else:
        status_val = status
    if status_val not in ["backlog", "active"]:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Task [[bold blue]{id}[/bold blue]] is not in a startable state (backlog or active only).")
        raise typer.Exit(code=1)

    active_entry = time_repository.get_active_time_entry()
    if active_entry:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Another time log is already running: {active_entry.title}")
        raise typer.Exit(code=1)

    update_payload = {"status": "active", "start": now.isoformat()}
    task_repository.update_task(id, update_payload)

    task = task_repository.get_task_by_id(id)

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
        raise typer.Exit(code=1)

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
    now = now_local()
    try:
        tags, notes = parse_args(args or [])
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    active = time_repository.get_active_time_entry()
    if not active:
        console.print(
            "[yellow]⚠️ Warning[/yellow]: No active task is being tracked.")
        raise typer.Exit(code=1)

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

    try:
        end_time = parse_date_string(past, now=now) if past else now
    except Exception as e:
        console.print(f"[bold red]❌ Invalid time: {e}[/bold red]")
        raise typer.Exit(code=1)

    try:
        updated_log = time_repository.stop_active_time_entry(
            end_time=end_time,
            tags=",".join(tags) if tags else None,
            notes=notes if notes else None
        )
    except Exception as e:
        console.print(f"[bold red]❌ Failed to stop timer: {e}[/bold red]")
        raise typer.Exit(code=1)

    task_repository.update_task(task_id, {"status": "backlog"})

    start_dt = getattr(active, "start", None)
    if start_dt and isinstance(start_dt, datetime):
        try:
            duration_minutes = (end_time - start_dt).total_seconds() / 60
        except (TypeError, AttributeError):
            duration_minutes = 0.0
    else:
        duration_minutes = 0.0

    console.print(
        f"[yellow]⏸️ Paused[/yellow] task [bold blue][{task.id}][/bold blue]: {task.title} — Duration: [cyan]{round(duration_minutes, 2)}[/cyan] minutes")


@app.command()
def done(id: int, past: Optional[str] = past_option, args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes.")):
    """
    Mark a task as completed.
    """
    now = now_local()
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
        task_repository.update_task(id, {"status": "done"})
        console.print(f"[green]✔️ Done[/green] [{id}]: {task.title}")
        return

    if getattr(active, "task_id", None) != id:
        console.print(
            f"[bold red]❌ Error[/bold red]: Active log is not for task ID {id}.")
        raise typer.Exit(code=1)

    try:
        end_time = parse_date_string(past, now=now) if past else now
    except Exception as e:
        console.print(f"[bold red]❌ Invalid time: {e}[/bold red]")
        raise typer.Exit(code=1)

    start_dt = getattr(active, "start", None)
    print(start_dt, type(start_dt))
    if isinstance(start_dt, str):
        try:
            start_dt = datetime.fromisoformat(start_dt)
        except ValueError:
            console.print(
                f"[bold red]❌ Invalid start time format: {start_dt}[/bold red]")
            raise typer.Exit(code=1)
    if start_dt and not isinstance(start_dt, datetime):
        try:
            duration = (end_time - start_dt).total_seconds() / 60
        except (TypeError, AttributeError):
            duration = 0.0
    else:
        duration = 0.0

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

    task_repository.update_task(id, {"status": "done"})
    console.print(
        f"[green]✔️ Task Complete! [/green] task [bold blue]{task.title}[/bold blue] — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")
    console.print(get_feedback_saying("task_completed"))


def read_char_nonblocking(timeout: float = 1.0):
    """
    Cross-platform single-character non-blocking read:
    - On Windows, uses msvcrt.
    - On Unix-like, uses select+termios/tty.
    """
    if msvcrt:
        # Windows path
        start_time = time.time()
        while True:
            if msvcrt.kbhit():
                return msvcrt.getwch()
            if (time.time() - start_time) >= timeout:
                return None
            time.sleep(0.01)
    elif termios and tty:
        # Unix-like path
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)
            if rlist:
                return sys.stdin.read(1)
            else:
                return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    else:
        return None


@app.command("focus")
def focus_cli(
    id: int = typer.Argument(..., help="The ID of the task to focus on"),
    pomodoro: bool = typer.Option(
        True, "--pomodoro/--no-pomodoro",
        help="Enable back-to-back Pomodoro cycles"
    ),
    focus_len: int = typer.Option(
        30, "--focus", "-f", min=1, help="Minutes per focus block"
    ),
    break_len: int = typer.Option(
        5, "--break", "-b", min=1, help="Minutes per break block"
    ),
    refresh_interval: int = typer.Option(
        5, "--refresh-interval", "-r", min=1,
        help="Seconds between big-timer refreshes (e.g., 5 means the ASCII timer updates every 5s)"
    ),
):
    """
    Distraction-free CLI “focus mode” for a single task.
    Shows a big timer (ASCII via pyfiglet if available) and a progress bar in-place.
    Supports Pomodoro cycles, pause/exit, mark done, toggle Pomodoro, and log distracted time without stopping the timer.
    Uses monotonic clock to avoid drift, refreshes big timer only every `refresh_interval` seconds to reduce flicker.
    """
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[red]❌ Task ID {id} not found.[/red]")
        raise typer.Exit(1)

    active = time_repository.get_active_time_entry()
    if not (active and getattr(active, "task_id", None) == id):
        now = now_local()
        entry_data = {
            "title":   task.title or "",
            "task_id": id,
            "start":   now.isoformat(),
            "category": task.category,
            "project":  task.project,
            "notes":    "Focus mode start",
        }
        try:
            time_repository.start_time_entry(entry_data)
            console.print(
                f"[green]▶️ Focus mode started for task {id}.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to start time entry: {e}[/red]")
            raise typer.Exit(1)

    console.clear()
    console.print(f"[bold blue]Entering focus mode for:[/] {task.title}")
    commands_text = (
        "[dim]Commands: [bold]p[/bold]=pause & exit, "
        "[bold]d[/bold]=done & exit, "
        "[bold]t[/bold]=toggle Pomodoro on/off, "
        "[bold]l[/bold]=log distracted time[/dim]"
    )
    console.print(commands_text)

    total_distracted = 0  # in minutes
    in_break = False

    figler = None
    try:
        from pyfiglet import Figlet
        figler = Figlet(font="big")
    except ImportError:
        figler = None
    except Exception:
        figler = None

    def render_big_timer(remaining_secs: int) -> str:
        """
        Return ASCII art for remaining_secs if pyfiglet available, else simple MM:SS.
        """
        mm, ss = divmod(remaining_secs, 60)
        text = f"{mm:02}:{ss:02}"
        if figler:
            try:
                return figler.renderText(text)
            except Exception:
                return text
        else:
            return text

    try:
        while True:
            duration_secs = (break_len * 60) if in_break else (focus_len * 60)
            start_block = time.monotonic()

            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None),
                TextColumn("{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            )
            task_desc = "Break" if in_break else "Focus"
            prog_task = progress.add_task(task_desc, total=duration_secs)

            layout = Layout()
            layout.split(
                Layout(name="header", size=3),
                Layout(name="upper", ratio=3),
                Layout(name="lower", size=3),
                Layout(name="footer", size=3),
            )
            header_panel = Panel(
                Align.left(
                    f"[bold blue]Mode:[/] {task_desc}    [bold]Task:[/] {task.title}"),
                style="bold blue"
            )
            layout["header"].update(header_panel)
            footer_panel = Panel(
                Align.center(commands_text),
                style="dim"
            )
            layout["footer"].update(footer_panel)

            last_render_time = 0
            last_remaining = None

            with Live(layout, refresh_per_second=1, console=console, screen=False):
                while True:
                    elapsed = time.monotonic() - start_block
                    if elapsed < 0:
                        elapsed = 0.0
                    if elapsed > duration_secs:
                        elapsed = duration_secs
                    remaining = int(duration_secs - elapsed)

                    if last_remaining is None:
                        do_render = True
                    else:
                        if (elapsed - last_render_time) >= refresh_interval:
                            do_render = True
                        elif remaining < refresh_interval and last_remaining != remaining:
                            do_render = True
                        else:
                            do_render = False

                    if do_render:
                        big_text = render_big_timer(remaining)
                        timer_panel = Panel(
                            Align.center(big_text, vertical="middle"),
                            title=task_desc,
                            border_style="green" if not in_break else "magenta",
                            padding=(1, 2),
                        )
                        layout["upper"].update(timer_panel)
                        last_render_time = elapsed
                        last_remaining = remaining

                    progress.update(prog_task, completed=elapsed)
                    layout["lower"].update(progress)

                    key = read_char_nonblocking(timeout=1.0)
                    if key:
                        key = key.lower()
                        if key == "p":
                            console.print(
                                "\n[yellow]⏸️ Pausing focus mode.[/yellow]")
                            return
                        elif key == "d":
                            console.print(
                                "\n[green]✔️ Marking task done.[/green]")
                            try:
                                time_repository.stop_active_time_entry(
                                    end_time=now_local().isoformat())
                            except Exception as e:
                                console.print(
                                    f"[red]Error stopping time entry: {e}[/red]")
                            try:
                                task_repository.update_task(
                                    id, {"status": "done"})
                            except Exception as e:
                                console.print(
                                    f"[red]Error updating task status: {e}[/red]")
                            return
                        elif key == "t":
                            pomodoro = not pomodoro
                            console.print(
                                f"\n[cyan]Pomodoro {'ON' if pomodoro else 'OFF'}[/cyan]")
                            break
                        elif key == "l" and not in_break:
                            Live.stop(layout)
                            extra = console.input("Distracted minutes? ")
                            try:
                                lost = int(extra.strip())
                            except Exception:
                                lost = 0
                            total_distracted += lost
                            console.print(
                                f"[magenta]Added {lost}m distracted. Total now: {total_distracted}m[/magenta]")
                            header_panel = Panel(
                                Align.left(
                                    f"[bold blue]Mode:[/] {task_desc}    [bold]Task:[/] {task.title}"),
                                style="bold blue"
                            )
                            layout["header"].update(header_panel)
                            layout["footer"].update(footer_panel)
                            start_block = time.monotonic() - elapsed
                            last_render_time = 0
                            last_remaining = None
                            continue

                    if elapsed >= duration_secs:
                        break

            if in_break:
                console.print("[green]✨ Break over — back to focus.[/green]")
            else:
                console.print("[cyan]⏰ Focus block complete![/cyan]")
                extra = console.input("Distracted minutes? ")
                try:
                    lost = int(extra.strip())
                except Exception:
                    lost = 0
                total_distracted += lost

            if pomodoro:
                in_break = not in_break
            else:
                console.print(
                    "[yellow]Continuous focus block complete; exiting focus mode.[/yellow]")
                break

    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted by user. Exiting focus mode.[/yellow]")

    finally:
        try:
            time_repository.stop_active_time_entry(
                end_time=now_local().isoformat())
            console.print("[yellow]🔒 Focus mode exited.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error stopping time entry on exit: {e}[/red]")


def build_calendar_panel(now: datetime, tasks: list) -> Panel:
    """Build a calendar panel showing the current month with due dates highlighted."""
    cal = calendar.TextCalendar(firstweekday=0)
    month_str = cal.formatmonth(now.year, now.month)

    due_days = set()
    for t in tasks:
        if t.due:
            try:
                if isinstance(t.due, datetime):
                    due_dt = t.due
                else:
                    due_dt = datetime.fromisoformat(t.due)

                if (due_dt.month == now.month and due_dt.year == now.year):
                    due_days.add(due_dt.day)
            except (ValueError, TypeError, AttributeError):
                continue

    def highlight_month(text: str, due_days: set, today: int) -> Text:
        plain_text = text
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
    now = now_local()
    today_weekday = now.weekday()
    new_tasks_count = 0

    for task in tasks:
        recur_interval = task.recur_interval
        recur_unit = task.recur_unit
        recur_base = task.recur_base
        recur_days_of_week = task.recur_days_of_week

        if not (recur_interval and recur_unit and recur_base):
            continue

        try:
            if isinstance(recur_base, datetime):
                base_dt = recur_base
            else:
                base_dt = datetime.fromisoformat(recur_base)
        except (ValueError, TypeError):
            continue
        interval = recur_interval
        unit = recur_unit
        try:
            days_of_week = json.loads(
                recur_days_of_week) if recur_days_of_week else []
        except (json.JSONDecodeError, TypeError):
            days_of_week = []

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
            if isinstance(task.due, datetime):
                due_dt = task.due
            else:
                due_dt = datetime.fromisoformat(task.due)

            if isinstance(task.created, datetime):
                created_dt = task.created
            else:
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
        return "white"

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
    try:
        priority_as_int = float(priority_value or 0)
    except (ValueError, TypeError):
        priority_as_int = 0.0

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


def parse_due_offset(due_str):
    if due_str.startswith("+") and "T" in due_str:
        try:
            days_of_week_part, time_part = due_str[1:].split("T")
            days_of_week = int(days_of_week_part.rstrip("d"))
            hour, minute = map(int, time_part.split(":"))
            return timedelta(days_of_week=days_of_week, hours=hour, minutes=minute)
        except Exception as e:
            console.print(
                f"[yellow]Could not parse due offset '{due_str}'. Using default of 1 day. Details: {str(e)}[/yellow]")

    return timedelta(days_of_week=1)


def create_due_alert(task: Task, offset_str: str):
    """
    Schedule a one-off reminder for `task` at (due_local_time - offset).
    On POSIX: uses `at` if available, else falls back to cron via schedule_manager.
    On Windows: uses schtasks.exe to run a PowerShell modal + sound.
    """
    if not task.due:
        raise ValueError("Task has no due date")

    due_local: datetime = utc_iso_to_local(task.due)
    offset = parse_offset_to_timedelta(offset_str)
    alert_local = due_local - offset

    now_l = now_local()
    if alert_local < now_l:
        console.print(
            f"[yellow]⚠️ Reminder time {alert_local.strftime('%Y-%m-%d %H:%M')} is in the past. Scheduling immediately.[/yellow]"
        )
        alert_local = now_l + timedelta(seconds=5)

    msg = f"Reminder: Task [{task.id}] \"{task.title}\" is due at {due_local.strftime('%Y-%m-%d %H:%M')}"

    system = platform.system()
    if system in ("Linux", "Darwin"):
        notifier = build_linux_notifier(msg)

        if shutil.which("at"):
            at_time = alert_local.strftime("%H:%M %m/%d/%Y")
            full = f"echo {quote(notifier)} | at {at_time}"
            subprocess.run(["bash", "-lc", full], check=True, timeout=30)
            console.print(
                f"[green]✅ Reminder scheduled via at at {alert_local.strftime('%Y-%m-%d %H:%M')}[/green]"
            )
        else:
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
        ps_cmd = build_windows_notifier(msg)
        name = f"Lifelog_task_due_{task.id}"
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
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
        subprocess.run(sch, check=True, timeout=30)
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
                ["schtasks", "/Delete", "/TN", name, "/F"], check=False, timeout=30)
            console.print(
                f"[green]✅ Reminder cleared for task {task.id}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to clear reminder: {e}[/red]")
