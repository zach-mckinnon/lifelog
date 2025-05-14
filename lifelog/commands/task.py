# lifelog/commands/task.py
'''
Lifelog Task Management Module
This module provides functionality to create, modify, delete, and manage tasks within the Lifelog application.
It includes features for tracking time spent on tasks, setting reminders, and managing task recurrence.
The module uses JSON files for data storage and integrates with a cron job system for scheduling reminders.
'''
from lifelog.commands.utils.db import time_repository, task_repository
import re
import typer
import json
from datetime import date, datetime, timedelta
from tomlkit import table
from typing import List, Optional
import plotext as plt

from rich.console import Console, Group
from rich.prompt import Confirm
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
import calendar


from lifelog.commands.utils.db import task_repository, time_repository
from lifelog.commands.utils.shared_utils import parse_date_string, create_recur_schedule, safe_format_notes, serialize_task, parse_args
from lifelog.commands.utils.feedback import get_feedback_saying
import lifelog.config.config_manager as cf
from lifelog.config.cron_manager import apply_scheduled_jobs, save_config
from lifelog.commands.utils.shared_options import category_option, project_option, due_option, impt_option, recur_option, past_option


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
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[bool] = recur_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Add a new task.
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

    if not title:
        console.print(
            "[bold red]Your task must have a title! How else will you know what to do??[/bold red]")
        if Confirm.ask(f"[yellow]Add a title (no to exit)?[/yellow]"):
            title = typer.prompt("Enter a title")
        else:
            raise typer.Exit(code=1)

    doc = cf.load_config()
    existing_categories = cf.get_config_section("categories").keys()

    if category not in existing_categories and category != None:
        console.print(f"[blue]⚠️ Category '{category}' not found.[/blue]")
        if Confirm.ask(f"[yellow]Would you like to create it now?[/yellow]"):
            try:
                doc.setdefault("categories", {})
                doc["categories"][category] = category
                cf.save_config(doc)
                console.print(
                    f"[green]✅ Category '{category}' added to your config.[/green]")
            except Exception as e:
                console.print(
                    f"[bold red]Failed to create category: {e}[/bold red]")
                raise typer.Exit(code=1)

    if project:
        doc.setdefault("projects", {})
        if project not in doc["projects"]:
            console.print(
                f"[yellow]⚠️ Project '{project}' not found.[/yellow]")
            if Confirm.ask(f"[yellow]Create project '{project}' now?[/yellow]"):
                try:
                    doc["projects"][project] = project
                    cf.save_config(doc)
                    console.print(
                        f"[green]✅ Project '{project}' added to your config.[/green]")
                except Exception as e:
                    console.print(
                        f"[bold red]Failed to create project: {e}[/bold red]")
                    raise typer.Exit(code=1)
            else:
                raise typer.Exit(code=1)

    impt = impt if impt else 1

    if due:
        while True:
            try:
                due_dt = parse_date_string(due, future=True, now=now)
                break  # valid, exit loop
            except Exception as e:
                console.print(f"[bold red]❌ Invalid due date: {e}[/bold red]")
                if not Confirm.ask("[cyan]Enter a new date?[/cyan]"):
                    raise typer.Exit(code=1)
                due = typer.prompt(
                    "Enter a valid due date (e.g. 1d, tomorrow, 2025-12-31)")
        if due_dt < now:
            console.print("[bold red]⚠️ Due date is in the past![/bold red]")
            if not Confirm.ask("[red]Add anyway?[/red]"):
                raise typer.Exit(code=1)
    else:
        due_dt = None

    existing_task = task_repository.task_exists_with_title(title)
    if existing_task:
        console.print(
            f"[bold yellow]⚠️ Task with the same title already exists![/bold yellow]")
        if not Confirm.ask("[cyan]Would you like to overwrite it?[/cyan]"):
            console.print("[yellow]⚠️ Task not added.[/yellow]")
            raise typer.Exit(code=1)
        else:
            task_repository.delete_task(existing_task["id"])

    # --- Recur handling ---
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

    task_data = {
        "title": title,
        "project": project,
        "category": category,
        "impt": impt if impt else 1,
        "created": now.isoformat(),
        "due": due_dt.isoformat() if due_dt else None,
        "status": "backlog",
        "start": None,
        "end": None,
        "priority": 0,
        "recur_interval": recur_interval,
        "recur_unit": recur_unit,
        "recur_days_of_week": recur_days_of_week,
        "recur_base": recur_base,
    }

    task_data["priority"] = calculate_priority(task_data)

    # --- Save to DB ---
    try:
        task_repository.add_task(task_data)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to save task: {e}[/bold red]")
        raise typer.Exit(code=1)

    # --- Optional Reminder ---
    if due_dt and Confirm.ask("[yellow]Set reminder before due?[/yellow]"):
        try:
            create_due_alert(task_data)
        except Exception as e:
            console.print(
                f"[bold red]❌ Failed to create due alert: {e}[/bold red]")

    # --- Done ---
    console.print(
        f"[green]✅ Task added[/green]: [bold blue]{title}[/bold blue]")
    console.print(get_feedback_saying("task_added"))


# TODO: Improve the filtering and sorting options to properly work for priority by default.
@app.command()
def list(
    title: Optional[str] = typer.Argument(
        "", help="Search by task title contains"),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    impt: Optional[int] = impt_option,
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
        importance=impt,
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
    table.add_column("Priority", overflow="ellipsis")
    table.add_column("Due", style="yellow", overflow="ellipsis", width=5)

    for task in tasks:
        id_str = str(task["id"])
        title_str = task["title"]
        due_raw = task["due"]
        due_str = "-"
        if due_raw:
            due_dt = datetime.fromisoformat(due_raw)
            due_str = due_dt.strftime("%m/%d")

        prio = str(task["priority"])
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
    console = Console()
    now = datetime.now()

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
        due_dt = datetime.fromisoformat(
            t["due"]) if t.get("due") else datetime.max
        return (due_dt)

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
        id_str = str(task["id"])
        prio_raw = task.get("priority", 0)
        prio_text = Text(str(prio_raw), style=priority_color(prio_raw))
        due_str = "-"
        if task.get("due"):
            due_str = datetime.fromisoformat(task["due"]).strftime("%m/%d")
        title = task.get("title", "-")

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
    for key, value in task.items():
        if value is None or str(value).strip() == "":
            value = "-"
        console.print(f"[bold blue]{key.capitalize()}:[/bold blue] {value}")

# Start tracking a task (Like moving to in-progress)


@app.command()
def start(id: int):
    """
    Start or resume a task. Only one task can be tracked at a time.
    """
    now = datetime.now()
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    if task["status"] not in ["backlog", "active"]:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Task [[bold blue]{id}[/bold blue]] is not in a startable state (backlog or active only).")
        raise typer.Exit(code=1)

    # Check if another time log is already running
    active_entry = time_repository.get_active_time_entry()
    if active_entry:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Another time log is already running.. {active_entry['title']}")
        raise typer.Exit(code=1)

    # Mark task as active in DB
    task_repository.update_task(
        id, {"status": "active", "start": now.isoformat()})

    # Start time tracking linked to the task
    time_repository.start_time_entry(
        task["title"], task_id=id, start_time=now.isoformat())

    console.print(
        f"[green]▶️ Started[/green] task [bold blue][{id}][/bold blue]: {task['title']}")

# Modify an existing task.


@app.command()
def modify(
    id: int = typer.Argument(..., help="The ID of the task to modify"),
    title: Optional[str] = typer.Option(None, help="New title"),
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional: +tags Notes..."),
    project: Optional[str] = project_option,
    category: Optional[str] = category_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[bool] = recur_option,
):
    """
    Modify an existing task's fields. Only provide fields you want to update.
    """
    now = datetime.now()
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    try:
        if args is not None:
            tags, notes = parse_args(args)
        else:
            tags, notes = [], []
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    updates = {}
    if title and title != task.get("title"):
        updates["title"] = title
    if category and category != task.get("category"):
        updates["category"] = category
    if project and project != task.get("project"):
        updates["project"] = project
    if due:
        try:
            parse_date_string(due)
            updates["due"] = due
        except Exception as e:
            console.print(f"[bold red]❌ Invalid due date: {e}[/bold red]")
            raise typer.Exit(code=1)
    if impt is not None:
        updates["importance"] = impt

    # Handle recurrence using your SQL model columns
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

    # Recalculate priority
    updates["priority"] = calculate_priority({**task, **updates})

    if not updates:
        console.print(
            "[yellow]⚠️ No changes were made - you can always come back later when you're ready! ✌️[/yellow]")
        raise typer.Exit(code=0)

    task_repository.update_task(id, updates)

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
        f"[red]🗑️ Deleted[/red] task [bold blue][{id}][/bold blue]: {task['title']}")

# Pause a task (Like putting back to to-do) but keep logged time and do not set to done.


@app.command()
def stop(
    past: Optional[str] = past_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Pause the currently active task and stop timing, without marking it done.
    """
    now = datetime.now()
    tags, notes = parse_args(args or [])

    # Check if active time log exists
    active = time_repository.get_active_time_entry()
    if not active:
        console.print(
            "[yellow]⚠️ Warning[/yellow]: No active task is being tracked.")
        raise typer.Exit(code=1)

    if not active.get("task_id"):
        console.print(
            "[yellow]⚠️ Warning[/yellow]: Active log is not linked to a task.")
        raise typer.Exit(code=1)

    task_id = active["task_id"]
    task = task_repository.get_task_by_id(task_id)
    if not task:
        console.print(
            "[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)

    # Stop the time log
    end_time = parse_date_string(past, now=now) if past else now
    time_repository.stop_active_time_entry(
        end_time=end_time.isoformat(),
        tags=",".join(tags) if tags else None,
        notes=notes if notes else None
    )

    # Update the task back to 'backlog' and optionally handle custom tracking array if still needed
    updates = {
        "status": "backlog"
    }
    task_repository.update_task(task_id, updates)

    duration_minutes = (
        end_time - datetime.fromisoformat(active["start"])).total_seconds() / 60

    console.print(
        f"[yellow]⏸️ Paused[/yellow] task [bold blue][{task['id']}][/bold blue]: {task['title']} — Duration: [cyan] {round(duration_minutes, 2)} [/cyan] minutes")


# Set a task to completed.
@app.command()
def done(id: int, past: Optional[str] = past_option, args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes.")):
    """
    Mark a task as completed.
    """
    now = datetime.now()
    tags, notes = parse_args(args or [])

    # Lookup task directly from SQL
    task = task_repository.get_task_by_id(id)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    # Check if there's an active time entry
    active = time_repository.get_active_time_entry()
    if not active:
        console.print("[yellow]⚠️ No active timer. No new log saved.[/yellow]")

        # Just mark task done directly
        task_repository.update_task(id, {"status": "done"})
        console.print(f"[green]✔️ Done[/green] [{id}]: {task['title']}")
        return

    # Validate active log matches the task being marked done
    if active.get("task_id") != id:
        console.print(
            f"[bold red]❌ Error[/bold red]: Active log is not for task ID {id}.")
        raise typer.Exit(code=1)

    # Calculate duration
    start_time = datetime.fromisoformat(active["start"])
    end_time = parse_date_string(past, now=now) if past else now
    duration = (end_time - start_time).total_seconds() / 60

    # Stop the active time log and update with final tags/notes
    time_repository.stop_active_time_entry(
        end_time=end_time.isoformat(),
        tags=",".join(tags) if tags else None,
        notes=notes if notes else None
    )

    # Update task to done status
    task_repository.update_task(id, {"status": "done"})

    console.print(
        f"[green]✔️ Task Complete! [/green] task [bold blue]{task['title']}[/bold blue] — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")
    console.print(get_feedback_saying("task_done"))


@app.command()
def burndown(
):
    """
    📉 Remaining priority burndown over the next N days_of_week.
    """
    tasks = task_repository.get_all_tasks()

    now = datetime.now()
    plt.date_form(input_form='Y-m-d H:M:S', output_form='d/m/Y')
    start_date = now - timedelta(days=2)
    end_date = now + timedelta(days=3)

    all_dates = []
    current_date = start_date
    while current_date <= end_date:
        all_dates.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)

    all_tasks_in_range = []
    for d in all_dates:
        not_done_count = 0
        for task in tasks:
            if task and task.get("status") != "done":
                due_date_str = task.get("due")
                if due_date_str:
                    try:
                        due_date = datetime.fromisoformat(
                            due_date_str).strftime('%Y-%m-%d %H:%M:%S')

                        print(due_date)
                        if due_date <= d:
                            not_done_count += 1
                    except ValueError as e:
                        console.print(
                            f"Warning: Could not parse date: {due_date_str} for task: {task.get('title')}. Error: {e}")

        all_tasks_in_range.append(not_done_count)

    if all_tasks_in_range != []:
        plt.clf()
        plt.theme("matrix")
        formatted_dates = [datetime.strptime(
            date_str, "%Y-%m-%d").strftime("%d/%m/%Y") for date_str in all_dates]
        plt.plot(formatted_dates, all_tasks_in_range, marker="*")
        plt.xticks(formatted_dates, [date.strftime(
            "%m/%d") for date in [datetime.strptime(d, "%Y-%m-%d") for d in all_dates]])
        plt.xlabel("Date")
        plt.ylabel("Tasks Due")
        plt.title("Task Burndown")
        plt.show()
    else:
        console.print(
            f"Warning: Not enough data to create chart.. let's fill it up! ")


def build_calendar_panel(now: datetime, tasks: list) -> Panel:
    """Build a calendar panel showing the current month with due dates highlighted."""
    cal = calendar.TextCalendar(firstweekday=0)
    month_str = cal.formatmonth(now.year, now.month)

    # gather days_of_week to highlight
    due_days = {
        datetime.fromisoformat(t["due"]).day
        for t in tasks
        if t.get("due")
        and datetime.fromisoformat(t["due"]).month == now.month
        and datetime.fromisoformat(t["due"]).year == now.year
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
    now = datetime.now()
    today_weekday = now.weekday()
    new_tasks_count = 0

    for task in tasks:
        # Check for recurrence info
        recur_interval = task.get("recur_interval")
        recur_unit = task.get("recur_unit")
        recur_base = task.get("recur_base")
        recur_days_of_week = task.get("recur_days_of_week")

        if not (recur_interval and recur_unit and recur_base):
            continue  # skip non-recurring

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
            # Clone the task as a new DB row
            new_task_data = clone_task_for_db(task, now)
            task_repository.add_task(new_task_data)

            # Update the old task's last recur date (important for tracking!)
            task_repository.update_task(
                task["id"], {"recur_base": now.isoformat()})
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
    if task.get("due") and task.get("created"):
        try:
            due_dt = datetime.fromisoformat(task["due"])
            created_dt = datetime.fromisoformat(task["created"])
            offset = due_dt - created_dt
            new_due = (now + offset).replace(microsecond=0).isoformat()
        except Exception:
            new_due = None

    return {
        "title": task["title"],
        "project": task.get("project"),
        "category": task.get("category"),
        "impt": task.get("impt", 1),
        "created": now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
        "due": new_due,
        "status": "backlog",
        "start": None,
        "end": None,
        "priority": 0,
        "recur_interval": task.get("recur_interval"),
        "recur_unit": task.get("recur_unit"),
        "recur_days_of_week": task.get("recur_days_of_week"),
        "recur_base": now.isoformat(),
    }

# Load the task from the json file storing them.


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


def calculate_priority(task):
    coeff = {
        "importance": 5.0,
        "urgency_due": 12.0,
        "active": 4.0,
    }
    now = datetime.now()
    score = 0
    importance = task.get("impt", 1)
    score += importance * coeff["importance"]

    if task.get("status") == "active":
        score += coeff["active"]

    # Urgency due based on days_of_week remaining
    due = task.get("due")
    if due:
        try:
            due_date = datetime.fromisoformat(due)
            days_left = (due_date - now).days
            score += coeff["urgency_due"] * max(0, 1 - days_left / 10)
        except:
            pass

    return round(score, 2)


def parse_due_offset(due_str):
    # Expected format: '+5dT18:00'
    if due_str.startswith("+") and "T" in due_str:
        try:
            days_of_week_part, time_part = due_str[1:].split("T")
            days_of_week = int(days_of_week_part.rstrip("d"))
            hour, minute = map(int, time_part.split(":"))
            return timedelta(days_of_week=days_of_week, hours=hour, minutes=minute)
        except:
            pass
    return timedelta(days_of_week=1)  # default fallback


def create_due_alert(task):
    user_input = typer.prompt(
        "How long before due would you like an alert? (examples: '120' for minutes or '1d' for 1 day)",
        type=str
    )
    due = task["due"]
    now = datetime.now()
    if isinstance(due, str):
        due_time = datetime.fromisoformat(due)
    else:
        due_time = due

    # Try to parse user input
    if user_input.isdigit():
        # Just simple minutes
        alert_minutes = int(user_input)
        alert_time = due_time - timedelta(minutes=alert_minutes)
    else:
        # Parse like '1d', '2h', etc.
        # pretend it's future to get a positive delta
        parsed_delta_start = parse_date_string(
            user_input, future=True, now=now)
        if parsed_delta_start is None:
            console.print("[error]Invalid time format for alert![/error]")
            raise typer.Exit(code=1)

        # Calculate the time offset difference
        offset = parsed_delta_start - datetime.now()
        # Now subtract that offset from the due time
        alert_time = due_time - offset

    cron_time = f"{alert_time.minute} {alert_time.hour} {alert_time.day} {alert_time.month} *"

    doc = cf.load_config()
    cron_section = doc.get("cron", table())
    cron_section[f"task_alert_{task['id']}"] = {
        "schedule": cron_time,
        "command": f"notify-send '⏰ Reminder: Task [{task['id']}] {task['title']} is due soon!'"
    }

    doc["cron"] = cron_section
    save_config(doc)
    apply_scheduled_jobs()
