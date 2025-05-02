# lifelog/commands/task.py
''' 
Lifelog Task Management Module
This module provides functionality to create, modify, delete, and manage tasks within the Lifelog application. 
It includes features for tracking time spent on tasks, setting reminders, and managing task recurrence. 
The module uses JSON files for data storage and integrates with a cron job system for scheduling reminders.
'''
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
                console.print(
                    f"[bold red]❌ Invalid due date format: {e}[/bold red]")
                if not Confirm.ask("[cyan]Would you like to enter a new date?[/cyan]"):
                    raise typer.Exit(code=1)
                due = typer.prompt(
                    "Enter a valid due date (e.g. 1d, tomorrow, 2025-12-31)")
    else:
        due_dt = None

    tasks = load_tasks()
    for task in tasks:
        if task["title"] == title:
            console.print(
                f"[bold yellow]⚠️ Task with the same title already exists![/bold yellow]")
            if Confirm.ask("[cyan]Would you like to overwrite it?[/cyan]"):
                tasks.remove(task)
                break
            else:
                console.print("[yellow]⚠️ Task not added.[/yellow]")
                raise typer.Exit(code=1)

    task = {
        "id": next_id(tasks),
        "title": title,
        "project": project,
        "category": category,
        "impt": impt,
        "created": now.isoformat(),
        "due": due_dt.isoformat() if isinstance(due_dt, datetime) else due_dt,
        "status": "backlog",
        "start": None,
        "end": None,
        "recur": "",
        "tags": tags if tags else [],
        "notes": notes if notes else [],
        "tracking": []

    }

    if recur:
        try:
            recur_data = create_recur_schedule(recur) if recur else None
            task["recur_base"] = now.isoformat()
            task["recur"] = recur_data

        except Exception as e:
            console.print(
                f"[bold red]❌ Invalid recurrence format: {e}[/bold red]")
            raise typer.Exit(code=1)
    else:
        recur = None
    if due_dt:
        if due_dt < now:
            console.print("[bold red]⚠️- Due date is in the past![/bold red]")
            if not Confirm.ask("[red]Do you want to add it anyway?[/red]"):
                raise typer.Exit(code=1)

        console.print("⏰ Task has a due date!")
        if Confirm.ask("[yellow]Would you like to set a reminder alert before it's due?[/yellow]"):
            try:
                create_due_alert(task)
            except Exception as e:
                console.print(
                    f"[bold red]❌ Failed to create due alert: {e}[/bold red]")
                raise typer.Exit(code=1)

    task["priority"] = calculate_priority(task)
    tasks.append(task)
    try:
        save_tasks(tasks)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to save tasks: {e}[/bold red]")
        raise typer.Exit(code=1)

    saying = get_feedback_saying("task_added")
    console.print(
        f"[green]✅ Task added[/green]: [bold blue][{task['id']}][/bold blue] {task['title']}")
    console.print(saying)


# TODO: Improve the filtering and sorting options to properly work for priority by default.
@app.command()
def list(
    title: Optional[str] = typer.Argument(
        "", help="The title of the activity you're tracking."),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    sort: Optional[str] = typer.Option(
        "priority", help="Sort by 'priority', 'due', 'created', or 'id'."),
    status: Optional[str] = typer.Option(
        None, help="Filter by status (e.g. 'backlog', 'active', 'completed')."),
    show_completed: bool = typer.Option(
        False, help="Include completed tasks."),
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional search: Title keywords or +tags.")
):
    """
    List your tasks, sorted and filtered your way! 🌈
    Add -c to filter by category, -pr for project, etc..
    Sort the order with priority, due, created date, or id. 
    Include completed items in the list with --show-completed
    """
    tasks = load_tasks()

    # Only show active / non-completed by default
    if not show_completed:
        tasks = [t for t in tasks if t.get("status") != "done"]

    # Parse search input
    tags, notes = parse_args(args or [])

    # Smart Sorting
    sort_options = {
        "priority": lambda t: t.get("priority", 0),
        "due": lambda t: datetime.fromisoformat(t["due"]) if t.get("due") else datetime.max,
        "created": lambda t: datetime.fromisoformat(t["created"]) if t.get("created") else datetime.max,
        "id": lambda t: t.get("id", 0),
        "status": lambda t: t.get("status", "backlog"),
    }
    if sort not in sort_options:
        console.print(f"[bold red]❌ Invalid sort option: '{sort}'.[/bold red]")
        console.print(
            f"[yellow]Available options:[/yellow] {', '.join(sort_options.keys())}")
        raise typer.Exit(code=1)

    if title:
        tasks = [t for t in tasks if title.lower() in t.get("title", "").lower()]

    if tags:
        tasks = [t for t in tasks if any(
            tag in t.get("tags", []) for tag in tags)]

    if category:
        tasks = [t for t in tasks if t.get("category") == category]

    if project:
        tasks = [t for t in tasks if t.get("project") == project]

    if impt is not None:
        tasks = [t for t in tasks if t.get("impt") == impt]

    if status:
        tasks = [t for t in tasks if t.get("status") == status]

    if tags:
        tags_raw = [t for t in tasks if t.get("tags") == tags]
        tags = ", ".join(tags_raw) if tags_raw else "-"

    if notes:
        notes_raw = [t for t in tasks if t.get("notes") == notes]
        notes = safe_format_notes(notes_raw)

    # 3. Apply due filter ONLY if user asked for it
    if due:
        tasks = [t for t in tasks if t.get("due") and due in t["due"]]

    # 4. Finally, if show_completed is False, filter out "done" tasks
    if not show_completed and not status:
        tasks = [t for t in tasks if t.get("status") != "done"]

    sort_func = sort_options.get(sort, sort_options["id"])

    reverse_sort = sort == "priority"  # Only reverse if sorting by priority

    tasks.sort(key=sort_func, reverse=reverse_sort)

    if len(tasks) >= MAX_TASKS_DISPLAY:
        console.print(
            f"[dim]Showing first {MAX_TASKS_DISPLAY} tasks. Use filters to narrow down.[/dim]")
    tasks = tasks[:MAX_TASKS_DISPLAY]

    # Nothing Found
    if not tasks:
        console.print(
            "[italic blue]🧹 Nothing to do! Enjoy your day. 🌟[/italic blue]")
        return

    # Build the Table
    table = Table(
        show_header=True,          # hide header row to save space
        box=None,                   # remove all borders
        # no padding around table edges :contentReference[oaicite:0]{index=0}
        pad_edge=False,
        # merge adjacent cell padding :contentReference[oaicite:1]{index=1}
        collapse_padding=True,
        # zero vertical, 1-space horizontal padding :contentReference[oaicite:2]{index=2}
        padding=(0, 1),
        # auto-fit to terminal width :contentReference[oaicite:3]{index=3}
        expand=True,
    )
    table.add_column("ID", justify="right", width=2)
    table.add_column("Title", overflow="ellipsis", min_width=8,)
    table.add_column("Priority", overflow="ellipsis", )
    table.add_column("Due", style="yellow", overflow="ellipsis", width=5)

    for task in tasks:
        id_str = str(task.get("id", "-"))
        title = task.get("title", "-")
        due_raw = task.get("due", "")
        due_str = "-"
        if due_raw:
            due_dt = datetime.fromisoformat(due_raw)
            due_str = due_dt.strftime("%m/%d")

        prio = str(task.get("priority", "-"))
        color = priority_color(prio)
        prio_text = Text(prio)
        prio_text.stylize(color)

        table.add_row(id_str, title, prio_text, due_str)
    console.print(table)


@app.command()
def agenda():
    """
    📅 View your calendar and tasks side-by-side!
    """
    console = Console()
    now = datetime.now()

    tasks = load_tasks()
    tasks = [t for t in tasks if t.get("status") != "done"]
    # ─── Build Calendar Text ─────────────────────────────────────────────────
    calendar_panel = build_calendar_panel(now, tasks)

    # ─── Pick top 3 by priority desc, then due asc ───────────────────────────
    def sort_key(t):
        prio = t.get("priority", 0)
        due_dt = (
            datetime.fromisoformat(t["due"])
            if t.get("due")
            else datetime.max
        )
        return (-prio, due_dt)

    top_three = sorted(tasks, key=sort_key)[:3]

 # ─── Build a very compact table ──────────────────────────────────────────
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
        # ID
        id_str = str(task["id"])
        # Priority with color
        prio_raw = task.get("priority", 0)
        prio_text = Text(str(prio_raw), style=priority_color(prio_raw))
        # Due as MM/DD
        due_str = "-"
        if task.get("due"):
            due_str = datetime.fromisoformat(task["due"]).strftime("%m/%d")
        # Title
        title = task.get("title", "-")

        table.add_row(id_str, prio_text, due_str, title)

    # ─── Render vertically ────────────────────────────────────────────────────
    console.print(calendar_panel)
    console.print(table)


# Get information on a task TO DO: Make the ability to just say llog task task# to get info.
@app.command()
def info(id: int):
    """
    Show full details for a task.
    """
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == id), None)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    for key, value in task.items():
        console.print(f"[bold blue]{key.capitalize()}:[/bold blue] {value}")


# Start tracking a task (Like moving to in-progress)
@app.command()
def start(id: int):
    """
    Start or resume a task. Only one task can be tracked at a time.
    """
    now = datetime.now()
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == id), None)
    task_title = ""
    if task:
        task_title = task.get("title", "Unknown Task")
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    if task["status"] not in ["backlog", "active"]:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Task [[bold blue]{id}[/bold blue]] is not in a startable state (pending or active only).")
        raise typer.Exit(code=1)

    task["status"] = "active"
    if not task.get("start"):
        task["start"] = now.isoformat()
    save_tasks(tasks)

    data = {}
    TIME_FILE = cf.get_time_file()
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            data = json.load(f)

    if "active" in data:
        console.print(
            f"[yellow]⚠️ Warning[/yellow]: Another time log is already running.. {data['active']['title']}")
        raise typer.Exit(code=1)

    data["active"] = {
        "id": task["id"],
        "title": f"{task_title}",
        "start": now.isoformat(),
        "task": True
    }

    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)

    console.print(
        f"[green]▶️ Started[/green] task [bold blue][{id}][/bold blue]: {task['title']}")


# Modify an existing task.
@app.command()
def modify(
    id: int = typer.Argument(..., help="The ID of the task to modify"),
    title: str = typer.Argument(...,
                                help="The title of the activity you're tracking."),
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional: New title +tags Notes..."),
    project: Optional[str] = project_option,
    category: Optional[str] = category_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[str] = recur_option,
):
    """
    Modify an existing task's fields. Only provide fields you want to update.
    """
    now = datetime.now()
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == id), None)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {id} not found.")
        raise typer.Exit(code=1)

    try:
        if args != None:
            tags, notes = parse_args(args)
        else:
            tags, notes = [], []

    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    if not task:
        console.print(f"[bold red]❌ task with ID {id} not found.[/bold red]")
        raise typer.Exit(code=1)

    # ---- Apply safe modifications only ----
    changes_made = False

    if title and title != task.get("title"):
        task["title"] = title
        changes_made = True

    if category and category != task.get("category"):
        task["category"] = category
        changes_made = True

    if tags:
        current_tags = task.get("tags", [])
        task["tags"] = current_tags + tags
    if notes:
        current_notes = task.get("notes", [])
        task["notes"] = current_notes.append(notes)

    if not changes_made:
        console.print(
            "[yellow]⚠️ No changes were made - you can always come back later when you're ready! ✌️[/yellow]")
        raise typer.Exit(code=0)

    if project is not None:
        task["project"] = project
    if category is not None:
        task["category"] = category
    if due is not None:
        task["due"] = due
    if impt is not None:
        task["impt"] = impt
    if recur is not None:
        task["recur"] = recur
        task["recur_base"] = task.get(
            "recur_base", now.isoformat())  # Keep existing or set new

    task["priority"] = calculate_priority(task)

    save_tasks(tasks)
    console.print(
        f"[green]✏️ Updated[/green] task [bold blue][{id}][/bold blue].")


# Delete a task.
@app.command()
def delete(id: int):
    """
    Delete a task by ID.
    """
    tasks = load_tasks()
    tasks = [t for t in tasks if t["id"] != id]
    save_tasks(tasks)
    console.print(f"[red]🗑️ Deleted[/red] task [bold blue][{id}][/bold blue].")


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
    tasks = load_tasks()
    tags, notes = parse_args(args or [])

    TIME_FILE = cf.get_time_file()
    if not TIME_FILE.exists():
        console.print(
            "[yellow]⚠️ Warning[/yellow]: No time tracking file found.")
        raise typer.Exit(code=1)

    with open(TIME_FILE, "r") as f:
        data = json.load(f)

    if "active" not in data:
        console.print(
            "[yellow]⚠️ Warning[/yellow]: No active task is being tracked.")
        raise typer.Exit(code=1)

    active = data["active"]
    if not active["task"] == True:
        console.print(
            "[yellow]⚠️ Warning[/yellow]: Active task is not linked to a task.")
        raise typer.Exit(code=1)

    # ─── Find linked Task ─────────────────────────────────────────────────────
    task_id = active.get("id")   # already an integer
    task = next((t for t in tasks if t["id"] == task_id), None)

    if not task:
        console.print(
            "[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)

    # ─── Finalize Timing Info ─────────────────────────────────────────────────
    start_time = datetime.fromisoformat(active["start"])
    if past:
        end_time = parse_date_string(past, now=now)
    else:
        end_time = now
    duration = (end_time - start_time).total_seconds() / 60

    # ─── Merge tags and notes ─────────────────────────────────────────────────
    final_tags = (active.get("tags") or []) + (tags or [])
    final_notes = (active.get("notes") or "")
    if notes:
        final_notes += " " + notes

    # ─── Clone Active for History Entry ───────────────────────────────────────
    history_entry = active.copy()
    history_entry.update({
        "end": end_time.isoformat(),
        "duration_minutes": round(duration, 2),
        "tags": final_tags,
        "notes": final_notes,
    })

    # ─── Append to Global Time History ────────────────────────────────────────
    history = data.get("history", [])
    history.append(history_entry)
    data["history"] = history

    data.pop("active")

    # ─── Update Task Tracking Array ───────────────────────────────────────────
    task.setdefault("tracking", [])
    task_tracking_entry = {
        "start": history_entry["start"],
        "end": history_entry["end"],
        "duration_minutes": history_entry["duration_minutes"],
        "tags": history_entry["tags"],
        "notes": history_entry["notes"],
    }
    task["tracking"].append(task_tracking_entry)

    # ─── Set Task Back to Backlog ─────────────────────────────────────────────
    task["status"] = "backlog"

    save_tasks(tasks)
    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)

    console.print(
        f"[yellow]⏸️ Paused[/yellow] task [bold blue][{task["id"]}][/bold blue]: {task['title']} — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")


# Set a task to completed.
@app.command()
def done(id: int, past: Optional[str] = past_option, args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes.")):
    """
    Mark a task as completed.
    """
    # ─── Load tasks and parse any extra tags/notes ────────────────────────────
    tasks = load_tasks()
    tags, notes = parse_args(args or [])
    now = datetime.now()
    # ─── Load or initialize time‐tracking file ───────────────────────────────
    TIME_FILE = cf.get_time_file()
    try:
        with open(TIME_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"history": []}

    # ─── If no active timer, warn & mark done, then exit early ────────────────
    if "active" not in data:
        console.print("[yellow]⚠️ No active timer. No new log saved.[/yellow]")
        task = next((t for t in tasks if t["id"] == id), None)
        if task:
            total = sum(e["duration_minutes"]
                        for e in task.get("tracking", []))
            console.print(f"[cyan]Total tracked so far:[/cyan] {total:.2f}m")

            # mark task done
            task["status"] = "done"

            # write time file first to clear any leftover active entry
            with open(TIME_FILE, "w") as f:
                json.dump(data, f, indent=2)

            save_tasks(tasks)
            console.print(f"[green]✔️ Done[/green] [{id}]: {task['title']}")
        return

    # ─── We know there is an active entry ────────────────────────────────────
    active = data["active"]

    # ─── Lookup by the stored ID, not by title ───────────────────────────────
    task_id = active.get("id")
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        console.print(
            "[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)

    # ─── Compute duration ─────────────────────────────────────────────────────
    start_time = datetime.fromisoformat(active["start"])
    end_time = parse_date_string(past, now=now) if past else now
    duration = (end_time - start_time).total_seconds() / 60

    # ─── Merge any tags/notes provided at stop time ──────────────────────────
    final_tags = (active.get("tags") or []) + (tags or [])
    final_notes = active.get("notes", "") or ""
    if notes:
        final_notes += " " + notes

    # ─── Build and append the history entry ──────────────────────────────────
    history_entry = active.copy()
    history_entry.update({
        "end": end_time.isoformat(),
        "duration_minutes": round(duration, 2),
        "tags": final_tags,
        "notes": final_notes,
    })
    data.setdefault("history", []).append(history_entry)

    # remove the active marker
    data.pop("active", None)

    # ─── Also append to the task’s own tracking array ────────────────────────
    task.setdefault("tracking", []).append({
        "start": history_entry["start"],
        "end": history_entry["end"],
        "duration_minutes": history_entry["duration_minutes"],
        "tags": history_entry["tags"],
        "notes": history_entry["notes"],
    })

    # ─── Finally set the task status to done ────────────────────────────────
    task["status"] = "done"

    # ─── Persist both files (time file first, then tasks) ────────────────────
    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)
    save_tasks(tasks)

    # ─── User feedback ───────────────────────────────────────────────────────
    console.print(
        f"[yellow]Task Complete! [/yellow] task [bold blue][{id}][/bold blue]: "
        f"{task['title']} — Duration: [cyan]{round(duration, 2)}[/cyan] minutes"
    )
    console.print(get_feedback_saying("task_done"))


@app.command()
def burndown(
):
    """
    📉 Remaining priority burndown over the next N days_of_week.
    """
    tasks = load_tasks()

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


def auto_recur():
    tasks = load_tasks()
    now = datetime.now()
    today_weekday = now.weekday()
    new_tasks = []

    for task in tasks:
        recur = task.get("recur") or {}
        if not bool(recur):
            continue

        recur_base = task.get("last_created") or task.get("created")
        base_dt = datetime.fromisoformat(recur_base)

        interval = recur.get("interval", 1)  # default 1
        unit = recur.get("unit", "day")
        days_of_week = recur.get("days_of_week", [])

        if unit == "day":
            days_of_week_since = (now.date() - base_dt.date()).days_of_week
            if days_of_week_since > 0 and days_of_week_since % interval == 0:
                new_tasks.append(clone_task(task, now))
        elif unit == "week":
            days_of_week_since = (now.date() - base_dt.date()).days_of_week
            # only consider future weeks
            if days_of_week_since > 0:
                if days_of_week:
                    # user specified weekdays_of_week → fire on those weeks & days_of_week
                    weeks_since = days_of_week_since // 7
                    if weeks_since % interval == 0 and today_weekday in days_of_week:
                        new_tasks.append(clone_task(task, now))
                else:
                    # no weekdays_of_week specified → fire every `interval` weeks
                    # on the same weekday as the base date
                    if days_of_week_since % (interval * 7) == 0:
                        new_tasks.append(clone_task(task, now))
        elif unit == "month":
            months_since = (now.year - base_dt.year) * \
                12 + (now.month - base_dt.month)
            if months_since % interval == 0 and now.day == base_dt.day:
                new_tasks.append(clone_task(task, now))

        elif unit == "year":
            years_since = now.year - base_dt.year
            if (years_since > 0 and now.month == base_dt.month and now.day == base_dt.day):
                new_tasks.append(clone_task(task, now))

    save_tasks(tasks + new_tasks)
    if new_tasks:
        console.print(
            f"[green]🔁 Recreated {len(new_tasks)} recurring task(s).[/green]")


def clone_task(task, now):
    new_task = task.copy()
    new_task["id"] = next_id(load_tasks())
    new_task["created"] = now.replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    if task.get("due"):
        try:
            due_dt = datetime.fromisoformat(task["due"])
            offset = due_dt - datetime.fromisoformat(task["created"])
            new_due = now + offset
            new_task["due"] = new_due.replace(microsecond=0).isoformat()
        except Exception:
            new_task["due"] = None
    else:
        new_task["due"] = None

    new_task["status"] = "backlog"
    new_task["start"] = None
    new_task["end"] = None
    new_task["last_created"] = now.isoformat()
    new_task["priority"] = calculate_priority(new_task)
    return new_task

# Load the task from the json file storing them.


def load_tasks():
    TASK_FILE = cf.get_task_file()
    if TASK_FILE.exists():
        with open(TASK_FILE, "r") as f:
            return json.load(f)
    return []

# Save tasks to JSON


def save_tasks(tasks):
    TASK_FILE = cf.get_task_file()
    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TASK_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


# Get the next ID in tasks.
def next_id(tasks):
    return max([t.get("id", 0) for t in tasks] + [0]) + 1


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
            days_of_week_left = (due_date - now).days_of_week
            score += coeff["urgency_due"] * max(0, 1 - days_of_week_left / 10)
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
