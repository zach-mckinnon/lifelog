# lifelog/commands/task.py
''' 
Lifelog Task Management Module
This module provides functionality to create, modify, delete, and manage tasks within the Lifelog application. 
It includes features for tracking time spent on tasks, setting reminders, and managing task recurrence. 
The module uses JSON files for data storage and integrates with a cron job system for scheduling reminders.
'''
import typer
import json
from datetime import datetime, timedelta
from tomlkit import table
from typing import List, Optional
from jsonschema import validate, ValidationError

from rich.console import Console, Group
from rich.prompt import Confirm
from rich.table import Table
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text
from rich import box
import calendar

from lifelog.commands.utils.shared_utils import parse_date_string, parse_recur_string, serialize_task, parse_args
from lifelog.commands.utils.feedback import get_feedback_saying
import lifelog.config.config_manager as cf
from lifelog.config.cron_manager import apply_scheduled_jobs, save_config
from lifelog.commands.utils.shared_options import category_option, project_option, due_option, impt_option, recur_option


app = typer.Typer(help="Create and manage your personal tasks.")

console = Console()

MAX_TASKS_DISPLAY = 50

# Add a new task.
@app.command()
def add(
    args: List[str] = typer.Argument(..., help="Title +tags Notes..."),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[str] = recur_option,

):
    """
    Add a new task.
    """
    try:
        title, tags, notes, past = parse_args(args)
        if not title:
            raise ValueError("Please ensure you have a title! How else will you know what to do??")
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)
    
    doc = cf.load_config()
    existing_categories = cf.get_config_section("categories").keys()
    
    if category not in existing_categories and category != None:
        console.print(f"[yellow]⚠️ Category '{category}' not found.[/yellow]")
        if Confirm.ask(f"[yellow]Would you like to create it now?[/yellow]"):
            try:
                doc.setdefault("categories", {})
                doc["categories"][category] = category
                cf.save_config(doc)
                console.print(f"[green]✅ Category '{category}' added to your config.[/green]")
            except Exception as e:
                console.print(f"[bold red]Failed to create category: {e}[/bold red]")
                raise typer.Exit(code=1)
            
    
    if project:
        doc.setdefault("projects", {})
        if project not in doc["projects"]:
            console.print(f"[yellow]⚠️ Project '{project}' not found.[/yellow]")
            if Confirm.ask(f"[yellow]Create project '{project}' now?[/yellow]"):
                try:
                    doc["projects"][project] = project
                    cf.save_config(doc)
                    console.print(f"[green]✅ Project '{project}' added to your config.[/green]")
                except Exception as e:
                    console.print(f"[bold red]Failed to create project: {e}[/bold red]")
                    raise typer.Exit(code=1)
            else:
                raise typer.Exit(code=1)
        
    impt = impt if impt else 1

    try:
        recur_data = parse_recur_string(recur) if recur else None
    except Exception as e:
        console.print(f"[bold red]❌ Invalid recurrence format: {e}[/bold red]")
        raise typer.Exit(code=1)
    
    try:
        due_dt = parse_date_string(due, future=True) if due else None
    except Exception as e:
        console.print(f"[bold red]❌ Invalid due date format: {e}[/bold red]")
        raise typer.Exit(code=1)

    tasks = load_tasks()
    for task in tasks:
        if task["title"] == title:
            console.print(f"[yellow]⚠️ Task with the same title already exists![/yellow]")
            if Confirm.ask("[yellow]Would you like to overwrite it?[/yellow]"):
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
        "tags": tags,
        "impt": impt,
        "created": datetime.now().isoformat(),
        "due": due_dt.isoformat() if isinstance(due_dt, datetime) else due_dt,
        "status": "backlog",
        "start": None,
        "end": None,
        "recur": recur_data,
        "notes":notes,
        "tracking": []

    }

    if recur:
        task["recur_base"] = datetime.now().isoformat()
        
    if due_dt:
        if due_dt < datetime.now():
            console.print("[bold red]⚠️ Due date is in the past![/bold red]")
            if not Confirm.ask("[red]Do you want to add it anyway?[/red]"):
                raise typer.Exit(code=1)

        console.print("[yellow]⏰ Task has a due date![/yellow]")
        if Confirm.ask("[yellow]Would you like to set a reminder alert before it's due?[/yellow]"):
            try:
                create_due_alert(task)
            except Exception as e:
                console.print(f"[bold red]❌ Failed to create due alert: {e}[/bold red]")
                raise typer.Exit(code=1)


    task["priority"] = calculate_priority(task)
    tasks.append(task)
    try:
        save_tasks(tasks)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to save tasks: {e}[/bold red]")
        raise typer.Exit(code=1)

    saying = get_feedback_saying("task_added")
    console.print(f"[green]✅ Task added[/green]: [bold blue][{task['id']}][/bold blue] {task['title']}")
    console.print(saying)
    

# TODO: Improve the filtering and sorting options to properly work for priority by default.
@app.command()
def list(
    args: Optional[List[str]] = typer.Argument(None, help="Optional search: Title keywords or +tags."),
    category: Optional[str] = category_option,
    project: Optional[str] = project_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    sort: Optional[str] = typer.Option("id", help="Sort by 'priority', 'due', 'created', or 'id'."),
    status: Optional[str] = typer.Option(None, help="Filter by status (e.g. 'backlog', 'active', 'completed')."),
    show_completed: bool = typer.Option(False, help="Include completed tasks.")
):
    """
    List your tasks, sorted and filtered your way! 🌈
    """
    tasks = load_tasks()

    # Only show active / non-completed by default
    if not show_completed:
        tasks = [t for t in tasks if t.get("status") != "done"]

    # Parse search input
    title, tags, notes, past = parse_args(args or [])

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
        console.print(f"[yellow]Available options:[/yellow] {', '.join(sort_options.keys())}")
        raise typer.Exit(code=1)
    
    # Apply Filters
    if title:
        tasks = [t for t in tasks if title.lower() in t.get("title", "").lower()]

    if tags:
        tasks = [t for t in tasks if any(tag in t.get("tags", []) for tag in tags)]

    if category:
        tasks = [t for t in tasks if t.get("category") == category]

    if project:
        tasks = [t for t in tasks if t.get("project") == project]

    if due:
        tasks = [t for t in tasks if t.get("due") and due in t["due"]]

    if impt is not None:
        tasks = [t for t in tasks if t.get("impt") == impt]
    
    if status:
        tasks = [t for t in tasks if t.get("status") == status]

    if notes:
        tasks = [t for t in tasks if notes.lower() in (t.get("notes") or "").lower()]
    
    
    sort_func = sort_options.get(sort, sort_options["id"])

    reverse_sort = sort == "priority"  # Only reverse if sorting by priority
    
    tasks.sort(key=sort_func, reverse=reverse_sort)

    if len(tasks) == MAX_TASKS_DISPLAY:
        console.print(f"[dim]Showing first {MAX_TASKS_DISPLAY} tasks. Use filters to narrow down.[/dim]")
    tasks = tasks[:MAX_TASKS_DISPLAY]

    # Nothing Found
    if not tasks:
        console.print("[italic blue]🧹 Nothing to do! Enjoy your day. 🌟[/italic blue]")
        return

    # Build the Table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", justify="right")
    table.add_column("Title")
    table.add_column("Priority")
    table.add_column("Due", style="yellow")
    table.add_column("Category", style="cyan")
    table.add_column("Project", style="magenta")
    table.add_column("Tags", style="green")

    for task in tasks:
        prio = task.get("priority", 0)
        color = priority_color(prio)
        prio_str = f"[{color}]{prio}[/]"

        table.add_row(
            str(task["id"]),
            task["title"],
            prio_str,
            task.get("due", "-"),
            task.get("category", "-"),
            task.get("project", "-"),
            ", ".join(task.get("tags", [])) or "-"
        )

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

    # ─── Build Agenda Text ───────────────────────────────────────────────────
    today = now.date()
    tomorrow = today + timedelta(days=1)
    two_weeks_later = today + timedelta(days=14)

    # Filter tasks
    today_tasks = [t for t in tasks if t.get("due") and datetime.fromisoformat(t["due"]).date() == today]
    tomorrow_tasks = [t for t in tasks if t.get("due") and datetime.fromisoformat(t["due"]).date() == tomorrow]
    upcoming_tasks = [
        t for t in tasks 
        if t.get("due") 
        and tomorrow < datetime.fromisoformat(t["due"]).date() <= two_weeks_later
    ]

    # Build sections
    panels = []

    if today_tasks:
        today_table = build_agenda_table(today_tasks, title="📅 Today")
        panels.append(Panel(today_table, border_style="#ff8300"))
    else:
        panels.append(Panel(Text("Nothing scheduled for today!", style="dim"), title="📅 Today", border_style="cyan"))

    if tomorrow_tasks:
        tomorrow_table = build_agenda_table(tomorrow_tasks, title="📅 Tomorrow")
        panels.append(Panel(tomorrow_table, border_style="#ffe000"))
    else:
        panels.append(Panel(Text("Nothing scheduled for tomorrow!", style="dim"), title="📅 Tomorrow", border_style="green"))

    if upcoming_tasks:
        upcoming_table = build_agenda_table(upcoming_tasks, title="📅 Upcoming (Next 2 Weeks)")
        panels.append(Panel(upcoming_table, border_style="#5fff00"))
    else:
        panels.append(Panel(Text("No upcoming tasks in the next 2 weeks.", style="dim"), title="📅 Upcoming", border_style="magenta"))

    agenda_panel = Panel(
    Group(*panels),  # <- THIS stacks them neatly inside
    border_style="#7d00ff",
    expand=True
)
    
    # ─── Print Side by Side ──────────────────────────────────────────────────
    if len(tasks) == MAX_TASKS_DISPLAY:
        console.print(f"[dim]Showing first {MAX_TASKS_DISPLAY} tasks. Use filters to narrow down.[/dim]")

    console.rule("[bold cyan]📅 Agenda View[/bold cyan]")
    console.print("\n")
    console.print(Columns([calendar_panel, agenda_panel], equal=False, expand=False))


def build_calendar_panel(now: datetime, tasks: list) -> Panel:
    """Build a calendar panel showing the current and next month with due dates highlighted."""
    cal = calendar.TextCalendar(firstweekday=0)

    # Get current and next month text
    this_month_str = cal.formatmonth(now.year, now.month)
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)  # Safely move to next month
    next_month_str = cal.formatmonth(next_month.year, next_month.month)

    # Gather due dates
    due_dates_this = set()
    due_dates_next = set()
    for task in tasks:
        due = task.get("due")
        if due:
            due_date = datetime.fromisoformat(due).date()
            if due_date.month == now.month and due_date.year == now.year:
                due_dates_this.add(due_date.day)
            elif due_date.month == next_month.month and due_date.year == next_month.year:
                due_dates_next.add(due_date.day)

    # Function to build month text with highlights
    def build_month_text(month_str: str, highlight_days: set, current_day: Optional[int] = None) -> Text:
        month_text = Text(month_str)
        for day in range(1, 32):
            day_str = f"{day:2}"
            idx = month_text.plain.find(day_str)
            if idx != -1:
                style = None
                if current_day and day == current_day:
                    style = "reverse"
                elif current_day and day in highlight_days:
                    style = "on-blue"
                elif day in highlight_days:
                    style = "on-yellow"
                if style:
                    month_text.stylize(style, idx, idx + len(day_str))
        return month_text

    # Build both months
    cal_text = Text()
    cal_text.append(build_month_text(this_month_str, due_dates_this, now.day))
    cal_text.append("\n\n")  # Space between months
    cal_text.append(build_month_text(next_month_str, due_dates_next))

    # Final panel
    calendar_panel = Panel(
        cal_text,
        border_style="#7d00ff",
        expand=True,
    )

    return calendar_panel


def build_agenda_table(tasks, title="🗓️ Agenda"):
    """Build a table for the given list of tasks."""

    tasks = tasks[:MAX_TASKS_DISPLAY]

    table = Table(title=title, show_header=True, header_style="#d70000", box=box.SIMPLE)
    table.add_column("ID", justify="center", style="white")
    table.add_column("Priority", justify="center")
    table.add_column("Due Date", justify="center")
    table.add_column("Task", justify="center", style="cyan")
    table.add_column("Created", justify="center", style="green")
    table.add_column("Project", justify="center", style="")
    table.add_column("Category", justify="center", style="green")
    table.add_column("Tags", justify="center", style="blue")
    table.add_column("Notes", justify="center", style="white")


    for task in tasks:
        id_ = str(task["id"])
        prio = str(task.get("priority", 0))
        title = task["title"]
        due_raw = task.get("due")
        created_raw = task.get("created")
        project = task.get("project", "-")
        category = task.get("category", "-")
        notes = task.get("notes", "-")

        due = datetime.fromisoformat(due_raw).strftime("%m/%d/%y %H:%M") if due_raw else due_raw
        created = datetime.fromisoformat(created_raw).strftime("%m/%d/%y %H:%M") if created_raw else created_raw
        tags = ", ".join(task.get("tags", [])) if task.get("tags") else "-"
        now = datetime.now()
        due_color = get_due_color(due_raw, now) if due_raw else "white"
        due_text = Text(due, style=due_color)
        prio_color = priority_color(prio)
        priority = Text(prio, style=prio_color)
        table.add_row(id_, priority, due_text, title, created, tags, project, category, notes)

    return table


# Get information on a task TO DO: Make the ability to just say llog task task# to get info. 
@app.command()
def info(task_id: int):
    """
    Show full details for a task.
    """
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {task_id} not found.")
        raise typer.Exit(code=1)

    for key, value in task.items():
        console.print(f"[bold blue]{key.capitalize()}:[/bold blue] {value}")


# Start tracking a task (Like moving to in-progress)
@app.command()
def start(task_id: int):
    """
    Start or resume a task. Only one task can be tracked at a time.
    """
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    task_title = ""
    if task:
        task_title = task.get("title", "Unknown Task")
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {task_id} not found.")
        raise typer.Exit(code=1)

    if task["status"] not in ["backlog", "active"]:
        console.print(f"[yellow]⚠️ Warning[/yellow]: Task [[bold blue]{task_id}[/bold blue]] is not in a startable state (pending or active only).")
        raise typer.Exit(code=1)

    task["status"] = "active"
    if not task.get("start"):
        task["start"] = datetime.now().isoformat()
    save_tasks(tasks)

    
    data = {}
    TIME_FILE = cf.get_time_file()
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            data = json.load(f)

    if "active" in data:
        console.print(f"[yellow]⚠️ Warning[/yellow]: Another time log is already running.. {data['active']["title"]}")
        raise typer.Exit(code=1)

    data["active"] = {
        "title": f"{task_title}",
        "start": datetime.now().isoformat(),
        "task" : True
    }

    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)

    console.print(f"[green]▶️ Started[/green] task [bold blue][{task_id}][/bold blue]: {task['title']}")


# Modify an existing task.
@app.command()
def modify(
    task_id: int = typer.Argument(..., help="The ID of the task to modify"),
    title: Optional[str] = typer.Option(None, help="New title for the task"),
    project: Optional[str] = project_option, 
    category: Optional[str] = category_option, 
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    recur: Optional[str] = recur_option,
):
    """
    Modify an existing task's fields. Only provide fields you want to update.
    """
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {task_id} not found.")
        raise typer.Exit(code=1)


    if title is not None:
        task["title"] = title
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
        task["recur_base"] = task.get("recur_base", datetime.now().isoformat()) # Keep existing or set new

    task["priority"] = calculate_priority(task)
    save_tasks(tasks)
    console.print(f"[green]✏️ Updated[/green] task [bold blue][{task_id}][/bold blue].")


# Delete a task.
@app.command()
def delete(task_id: int):
    """
    Delete a task by ID.
    """
    tasks = load_tasks()
    tasks = [t for t in tasks if t["id"] != task_id]
    save_tasks(tasks)
    console.print(f"[red]🗑️ Deleted[/red] task [bold blue][{task_id}][/bold blue].")


# Pause a task (Like putting back to to-do) but keep logged time and do not set to done. 
@app.command()
def stop(
    args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes."),
):
    """
    Pause the currently active task and stop timing, without marking it done.
    """
    tasks = load_tasks()
    title, tags, notes, past = parse_args(args or [])

    if not TIME_FILE.exists():
        TIME_FILE = cf.get_time_file()
        console.print("[yellow]⚠️ Warning[/yellow]: No time tracking file found.")
        raise typer.Exit(code=1)

    with open(TIME_FILE, "r") as f:
        data = json.load(f)

    if "active" not in data:
        console.print("[yellow]⚠️ Warning[/yellow]: No active task is being tracked.")
        raise typer.Exit(code=1)

    active = data["active"]
    if not active["task"] == True:
        console.print("[yellow]⚠️ Warning[/yellow]: Active tracker is not linked to a task.")
        raise typer.Exit(code=1)
    
    # ─── Find linked Task ─────────────────────────────────────────────────────
    task_id = int(active["category"].split(":")[1])
    task = next((t for t in tasks if t["id"] == task_id), None)
    
    if not task:
        console.print("[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)
    
    # ─── Finalize Timing Info ─────────────────────────────────────────────────
    start_time = datetime.fromisoformat(active["start"])
    if past:
        end_time = datetime.now() - parse_date_string(past)
    else:
        end_time = datetime.now()
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
    
    console.print(f"[yellow]⏸️ Paused[/yellow] task [bold blue][{task_id}][/bold blue]: {task['title']} — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")


# Set a task to completed. 
@app.command()
def done(task_id: int, args: Optional[List[str]] = typer.Argument(None, help="Optional +tags and notes.")):
    """
    Mark a task as completed.
    """
    tasks = load_tasks()
    title, tags, notes, past = parse_args(args or [])

    TIME_FILE = cf.get_time_file()
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            data = json.load(f)

    if "active" not in data:
        console.print("[yellow]⚠️ Warning[/yellow]: No active task is being tracked. No time tracking will be saved. ")

    active = data["active"]
    console.log(active)
    if active["task"] == False:
        console.print("[yellow]⚠️ Warning[/yellow]: Active tracker is not linked to a task.")
        for i in tasks["history"]:
            if i["id"] == task_id:
                task = i
                
    
    # ─── Find linked Task ─────────────────────────────────────────────────────
    task_title = active["title"]
    task = next((t for t in tasks if t["title"] == task_title), None)
    
    if not task:
        console.print("[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)
    
    # ─── Finalize Timing Info ─────────────────────────────────────────────────
    start_time = datetime.fromisoformat(active["start"])
    if past:
        end_time = datetime.now() - parse_date_string(past)
    else:
        end_time = datetime.now()
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
    task["status"] = "done"

    save_tasks(tasks)
    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)
    
    console.print(f"[yellow]Task Complete! [/yellow] task [bold blue][{task_id}][/bold blue]: {task['title']} — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")
    console.print(get_feedback_saying("task_done"))


def auto_recur():
    tasks = load_tasks()
    now = datetime.now()
    today_weekday = now.strftime("%a").lower()[0]  # 'm', 't', 'w', 't', 'f', 's', 's'
    new_tasks = []

    for task in tasks:
        recur = task.get("recur")
        if not recur:
            continue

        recur_base = task.get("recur_base") or task.get("created")
        base_dt = datetime.fromisoformat(recur_base)

        every = recur.get("every", 1)  # default 1
        unit = recur.get("unit", "day")
        days = recur.get("days", [])

        if unit == "day":
            if (now.date() - base_dt.date()).days % every == 0:
                new_tasks.append(clone_task(task, now))
        elif unit == "week":
            weeks_since = (now.date() - base_dt.date()).days // 7
            if weeks_since % every == 0 and today_weekday in days:
                new_tasks.append(clone_task(task, now))
        elif unit == "month":
            months_since = (now.year - base_dt.year) * 12 + (now.month - base_dt.month)
            if months_since % every == 0 and now.day == base_dt.day:
                new_tasks.append(clone_task(task, now))

    save_tasks(tasks + new_tasks)
    if new_tasks:
        console.print(f"[green]🔁 Recreated {len(new_tasks)} recurring task(s).[/green]")


def clone_task(task, now):
    new_task = task.copy()
    new_task["id"] = next_id(load_tasks())
    new_task["created"] = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
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

    score = 0
    importance = task.get("impt", 1)
    score += importance * coeff["importance"]

    if task.get("status") == "active":
        score += coeff["active"]

    # Urgency due based on days remaining
    due = task.get("due")
    if due:
        try:
            due_date = datetime.fromisoformat(due)
            days_left = (due_date - datetime.now()).days
            score += coeff["urgency_due"] * max(0, 1 - days_left / 10)
        except:
            pass

    return round(score, 2)


def parse_due_offset(due_str):
    # Expected format: '+5dT18:00'
    if due_str.startswith("+") and "T" in due_str:
        try:
            days_part, time_part = due_str[1:].split("T")
            days = int(days_part.rstrip("d"))
            hour, minute = map(int, time_part.split(":"))
            return timedelta(days=days, hours=hour, minutes=minute)
        except:
            pass
    return timedelta(days=1)  # default fallback


def create_due_alert(task):
    user_input = typer.prompt(
        "How long before due would you like an alert? (examples: '120' for minutes or '1d' for 1 day)",
        type=str
    )
    due = task["due"]
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
        parsed_delta_start = parse_date_string(user_input, future=True)  # pretend it's future to get a positive delta
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
