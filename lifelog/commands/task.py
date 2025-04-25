# lifelog/commands/task.py
import typer
import json
from datetime import datetime, timedelta
from pathlib import Path
import lifelog.config.config_manager as cf
from lifelog.config.cron_manager import apply_cron_jobs, load_cron_config, save_config
from lifelog.commands.utils.shared_options import tags_option, notes_option, category_option, project_option, due_option, impt_option, recur_option
from tomlkit import table
from typing import List, Optional
from lifelog.commands.utils.feedback import get_feedback_saying
from rich.console import Console

app = typer.Typer(help="Create and manage your personal tasks.")

console = Console()

LOG_FILE = cf.get_log_file()
TIME_FILE = cf.get_time_file()
TASK_FILE = cf.get_task_file()

# Load the task from the json file storing them.
def load_tasks():
    if TASK_FILE.exists():
        with open(TASK_FILE, "r") as f:
            return json.load(f)
    return []

# Save tasks to JSON
def save_tasks(tasks):
    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TASK_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

# Load the categories for time tracking.
def load_time_categories():
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            data = json.load(f)
            history = data.get("history", [])
            return list({entry["category"] for entry in history})
    return []

# Get the next ID in tasks. 
def next_id(tasks):
    return max([t.get("id", 0) for t in tasks] + [0]) + 1

# Calculate the priority using an Eisenhower Matrix.
def calculate_priority(task):
    coeff = {
        "importance": 5.0,
        "urgency_due": 12.0,
        "active": 4.0,
        "tags": 1.0,
        "project": 1.0
    }

    score = 0
    importance = task.get("impt", 1)
    score += importance * coeff["importance"]

    if task.get("status") == "active":
        score += coeff["active"]

    if task.get("tags"):
        score += coeff["tags"] * min(len(task["tags"]), 3)

    if task.get("project"):
        score += coeff["project"]

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

def get_recur_interval(recur):
    if recur == "daily":
        return timedelta(days=1)
    elif recur == "weekly":
        return timedelta(weeks=1)
    elif recur == "monthly":
        return timedelta(days=30)  # approximation
    return None


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
    alert_minutes = typer.prompt("How many minutes before due would you like an alert?", type=int)
    due_time = datetime.fromisoformat(task["due"])
    alert_time = due_time - timedelta(minutes=alert_minutes)
    cron_time = f"{alert_time.minute} {alert_time.hour} {alert_time.day} {alert_time.month} *"

    doc = load_cron_config()
    cron_section = doc.get("cron", table())
    cron_section[f"task_alert_{task['id']}"] = {
        "schedule": cron_time,
        "command": f"notify-send '⏰ Reminder: Task [{task['id']}] {task['title']} is due soon!'"
    }
    doc["cron"] = cron_section
    save_config(doc)
    apply_cron_jobs()


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


# Add a new task.
@app.command()
def add(
    title: str,
    category: str = category_option,
    project: Optional[str] = project_option,
    due: str = due_option,
    impt: int = impt_option,
   recur: str = recur_option,
    tags: List[str] = tags_option,
    notes: Optional[str] = notes_option
):
    """
    Add a new task.
    """
    existing_categories = load_time_categories()
    if category not in existing_categories:
        confirm = typer.confirm(f"[yellow]Category '{category}' not found in time history. Create it anyway?[/yellow]")
        if not confirm:
            raise typer.Exit(code=1)

    parsed_tags = [tag.lstrip("+") for tag in tags]

    tasks = load_tasks()
    task = {
        "id": next_id(tasks),
        "title": title,
        "project": project,
        "category": category,
        "tags": parsed_tags,
        "impt": impt,
        "created": datetime.now().isoformat(),
        "due": due,
        "status": "pending",
        "start": None,
        "end": None,
        "recur": recur,
        "notes":notes
    }

    if recur:
        task["recur_base"] = task["created"]
        doc = load_cron_config()
        cron_section = doc.get("cron", table())
        if "recur_auto" not in cron_section:
            cron_section["recur_auto"] = {
                "schedule": "0 0 * * *",
                "command": "llog task auto_recur"
            }
            doc["cron"] = cron_section
            save_config(doc)
            apply_cron_jobs()

    if due and typer.confirm("[yellow]Would you like a reminder before the due time?[/yellow]"):
        create_due_alert(task)


    task["priority"] = calculate_priority(task)
    tasks.append(task)
    save_tasks(tasks)
    saying = get_feedback_saying("task_added")
    console.print(f"[green]✅ Task added[/green]: [bold blue][{task['id']}][/bold blue] {task['title']} \n {saying}")
    


# Start tracking a task (Like moving to in-progress)
@app.command()
def start(task_id: int):
    """
    Start or resume a task. Only one task can be tracked at a time.
    """
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        console.print(f"[bold red]❌ Error[/bold red]: Task ID {task_id} not found.")
        raise typer.Exit(code=1)

    if task["status"] not in ["pending", "active"]:
        console.print(f"[yellow]⚠️ Warning[/yellow]: Task [[bold blue]{task_id}[/bold blue]] is not in a startable state (pending or active only).")
        raise typer.Exit(code=1)

    task["status"] = "active"
    if not task.get("start"):
        task["start"] = datetime.now().isoformat()
    save_tasks(tasks)

    
    data = {}
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            data = json.load(f)

    if "active" in data:
        console.print("[yellow]⚠️ Warning[/yellow]: Another task or category is already being timed.")
        raise typer.Exit(code=1)

    data["active"] = {
        "category": f"task:{task_id}",
        "start": datetime.now().isoformat()
    }

    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)

    console.print(f"[green]▶️ Started[/green] task [bold blue][{task_id}][/bold blue]: {task['title']}")


# List all tasks sorted by priority. 
# TO DO - Allow filtering list by project, category, or tags. 
@app.command()
def list(
    project: Optional[str] = project_option, 
    category: Optional[str] = category_option, 
    tag: Optional[str] = tags_option, 
    status: Optional[str] = notes_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    notes: Optional[str] = notes_option
    ):
    """
    List tasks sorted by priority. Defaults to all non-completed tasks.
    """
    tasks = load_tasks()

    filtered_tasks = [t for t in tasks if t["status"] != "completed"]

    if project:
        filtered_tasks = [t for t in filtered_tasks if t.get("project") == project]
    if category:
        filtered_tasks = [t for t in filtered_tasks if t.get("category") == category]
    if tag:
        filtered_tasks = [t for t in filtered_tasks if tag in t.get("tags", [])]
    if status:
        filtered_tasks = [t for t in filtered_tasks if t.get("status") == status]
    if impt is not None:
        filtered_tasks = [t for t in filtered_tasks if t.get("impt") == impt]
    if due:
        filtered_tasks = [t for t in filtered_tasks if t.get("due") and due in t["due"]]
    if notes:
        filtered_tasks = [t for t in filtered_tasks if t.get("notes") and notes in t["notes"]]

    filtered_tasks.sort(key=lambda x: x.get("priority", 0), reverse=True)

    if not filtered_tasks:
        console.print("[italic]No tasks to display.[/italic]")
        return

    for task in filtered_tasks:
        line = f"[bold blue][{task['id']}][/bold blue] {task['title']}"
        line += f" [dim](Priority: {task.get('priority', 0)})[/dim]"
        if task.get("status") == "active":
            line += " [bold green][ACTIVE][/bold green]"
        elif task.get("status") == "paused":
            line += " [bold yellow][PAUSED][/bold yellow]"
        if task.get("project"):
            line += f" [dim]Project:[/dim] [magenta]{task['project']}[/magenta]"
        if task.get("category"):
            line += f" [dim]Category:[/dim] [cyan]{task['category']}[/cyan]"
        if task.get("due"):
            line += f" [dim]Due:[/dim] [yellow]{task['due']}[/yellow]"
        if task.get("tags"):
            line += f" [dim]Tags:[/dim] [green]{', '.join(task['tags'])}[/green]"
        if task.get("impt"):
            line += f" [dim]Importance:[/dim] [bold]{task['impt']}[/bold]"
        if task.get("notes"):
            line += f" [dim]Notes:[/dim] [italic]{task['notes'][:20]}...[/italic]" # Show a snippet
        console.print(line)

# Modify an existing task.
@app.command()
def modify(
    task_id: int = typer.Argument(..., help="The ID of the task to modify"),
    title: Optional[str] = typer.Option(None, "-t", "--title", help="New title for the task"),
    project: Optional[str] = project_option, 
    category: Optional[str] = category_option, 
    tags: Optional[str] = tags_option, 
    status: Optional[str] = notes_option,
    impt: Optional[int] = impt_option,
    due: Optional[str] = due_option,
    notes: Optional[str] = notes_option,
    recur: Optional[str] = typer.Option(None, "-r", "--recur", help="New recurrence rule"),
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
    if status is not None:
        task["status"] = status
    if impt is not None:
        task["impt"] = impt
    if recur is not None:
        task["recur"] = recur
        task["recur_base"] = task.get("recur_base", datetime.now().isoformat()) # Keep existing or set new
    if tags is not None:
        task["tags"] = [tag.lstrip("+") for tag in tags]
    if notes is not None:
        task["notes"] = notes

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
@app.command()
def stop(
    notes: Optional[str] = notes_option
):
    """
    Pause the currently active task and stop timing, without marking it done.
    """
    tasks = load_tasks()

    if not TIME_FILE.exists():
        console.print("[yellow]⚠️ Warning[/yellow]: No time tracking file found.")
        raise typer.Exit(code=1)

    with open(TIME_FILE, "r") as f:
        data = json.load(f)

    if "active" not in data:
        console.print("[yellow]⚠️ Warning[/yellow]: No active task is being tracked.")
        raise typer.Exit(code=1)

    active = data["active"]
    if not active["category"].startswith("task:"):
        console.print("[yellow]⚠️ Warning[/yellow]: Active tracker is not linked to a task.")
        raise typer.Exit(code=1)

    task_id = int(active["category"].split(":")[1])
    task = next((t for t in tasks if t["id"] == task_id), None)

    if not task:
        console.print("[bold red]❌ Error[/bold red]: Task for active tracking not found.")
        raise typer.Exit(code=1)

    start_time = datetime.fromisoformat(active["start"])
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() / 60

    console.print(f"[yellow]⏸️ Paused[/yellow] task [bold blue][{task_id}][/bold blue]: {task['title']} — Duration: [cyan]{round(duration, 2)}[/cyan] minutes")

    history = data.get("history", [])
    history.append({
        "category": task.get("category", f"task:{task_id}"),
        "start": active["start"],
        "end": end_time.isoformat(),
        "duration_minutes": round(duration, 2),
        "notes": notes if notes else ""
    })
    data["history"] = history
    data.pop("active")

    task["status"] = "pending"
    save_tasks(tasks)
    with open(TIME_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Set a task to completed. 
@app.command()
def done(task_id: int, notes: Optional[str] = notes_option):
    """
    Mark a task as completed.
    """
    tasks = load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        console.print("[bold red]❌ Error[/bold red]: Task ID not found. Are you sure that's the right id?")
        raise typer.Exit(code=1)

    task["status"] = "completed"
    task["notes"] = (task.get("notes") or "")
    task["end"] = datetime.now().isoformat()
    save_tasks(tasks)
    console.print(f"[green]✅ Task [{task_id}] marked as done.[/green]")
    saying = get_feedback_saying("task_completed")
    if saying:
        console.print(f"[blue]🏆 {saying}[/blue]")

@app.command()
def auto_recur():
    """
    Automatically recreate recurring tasks at midnight.
    """
    tasks = load_tasks()
    now = datetime.now()
    new_tasks = []

    for task in tasks:
        if not task.get("recur"):
            continue

        recur_base = task.get("recur_base") or task.get("created")
        base_dt = datetime.fromisoformat(recur_base)
        interval = get_recur_interval(task["recur"])
        if not interval:
            continue

        if now.date() == (base_dt + interval).date():
            new_task = task.copy()
            new_task["id"] = next_id(tasks + new_tasks)
            new_task["created"] = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            new_task["due"] = (now + parse_due_offset(task["due"])).replace(microsecond=0).isoformat()
            new_task["status"] = "pending"
            new_task["start"] = None
            new_task["end"] = None
            new_task["priority"] = calculate_priority(new_task)
            new_tasks.append(new_task)
            task["recur_base"] = now.isoformat()

    save_tasks(tasks + new_tasks)
    if new_tasks:
        console.print(f"[green]🔁 Recreated {len(new_tasks)} recurring task(s).[/green]")


