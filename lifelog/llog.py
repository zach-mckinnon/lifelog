#!/home/zach.mckinnon/lifelog/.venv/bin/python
from datetime import datetime
import json
from pathlib import Path
import random
import subprocess
import sys
from typing import List, Optional
import typer
import requests

from lifelog.commands.utils import get_quotes
import lifelog.config.config_manager as cf
from lifelog.commands import time, task, track, report, environmental_sync

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


LOG_FILE = cf.get_log_file()
TIME_FILE = cf.get_time_file()
INIT_MARKER = cf.get_init_marker()
FIRST_COMMAND_FLAG_FILE = cf.get_fc_file()
FEEDBACK_FILE = cf.get_feedback_file()
DAILY_QUOTE_FILE = cf.get_daily_quote_file()

app = typer.Typer(help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")
console = Console()


def check_first_command_of_day():
    today = datetime.now().date()
    flag_data = {}

    if FIRST_COMMAND_FLAG_FILE.exists():
        try:
            with open(FIRST_COMMAND_FLAG_FILE, "r") as f:
                flag_data = json.load(f)
        except json.JSONDecodeError:
            console.print("[yellow]⚠️ Warning[/yellow]: Could not read first command flag.")

    last_executed_date = flag_data.get("last_executed")

    if last_executed_date != str(today):
        save_first_command_flag(str(today))
        return True
    return False

def save_first_command_flag(date_str):
    FIRST_COMMAND_FLAG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(FIRST_COMMAND_FLAG_FILE, "w") as f:
            json.dump({"last_executed": date_str}, f)
    except IOError:
        console.print(f"[yellow]⚠️ Warning[/yellow]: Could not save first command flag.")

# Example integration:
def greet_user():
    daily_quote = get_quotes.get_daily_quote()
    if daily_quote:
        console.print(f"[bold green]☀️ Good day![/bold green] Here's your daily inspiration: [italic]{daily_quote}[/italic]")
    else:
        console.print("[bold green]☀️ Good day![/bold green]")

# 🛠 Default data to bootstrap the app
DEFAULT_HABITS = [
    {"name": "Take Vitamins", "description": "Daily multivitamin"},
    {"name": "Drink Water", "description": "Track hydration throughout the day"},
    {"name": "Sleep Before Midnight", "description": "Go to bed before 12am"},
]


def schedule_background_cron_tasks():
    """
    Sets up background cron jobs for pulling external data if not already present.
    """
    try:
        cron_jobs = [
            ("lifelog_weather", "llog sync weather"),
            ("lifelog_moon", "llog sync moon"),
            ("lifelog_air", "llog sync air"),
        ]

        # Only add if not already present
        existing = subprocess.check_output(["crontab", "-l"], text=True) if sys.platform != "win32" else ""

        cron_lines = []
        for key, command in cron_jobs:
            cron_line = f"*/180 * * * * {command}  # {key}"
            if key not in existing:
                cron_lines.append(cron_line)

        if cron_lines:
            updated = existing + "\n" + "\n".join(cron_lines)
            subprocess.run("(crontab -l; echo \"{}\") | crontab -".format("\n".join(cron_lines)), shell=True)
            console.print("[cyan]✅ Background cron jobs scheduled.[/cyan]")
        else:
            console.print("[dim]⏳ Cron jobs already exist.[/dim]")

    except Exception as e:
        console.print(f"[red]Could not schedule cron jobs:[/red] {e}")

def get_user_location():
    try:
        response = requests.get('https://ipinfo.io/json')
        data = response.json()
        zip_code = data.get('postal')
        loc = data.get("loc", "0,0").split(",")
        latitude, longitude = float(loc[0]), float(loc[1])

        if zip_code:
            print(f"Detected ZIP code: {zip_code}")
            consent = input("Use this ZIP code? (Y/n): ").strip().lower()
            if consent in ("", "y", "yes"):
                cfg = cf.load_cron_config()
                cfg["location"] = {
                    "zip": zip_code,
                    "latitude": latitude,
                    "longitude": longitude
                }
                cf.save_config(cfg) 
                return
            
    except Exception:
        pass

    # Fallback to manual entry
    while True:
        zip_code = input("Enter your ZIP code: ").strip()
        if zip_code.isdigit() and len(zip_code) == 5:
            cfg = cf.load_cron_config()
            cfg["location"] = {"zip": zip_code}
            cf.save_config(cfg) 
            break
        else:
            print("Please enter a valid 5-digit ZIP code.")

def ensure_initialized():
    if not INIT_MARKER.exists():
        init_data()
        schedule_background_cron_tasks()



ensure_initialized()

# Register all modules
app.add_typer(track.app, name="track", help="Track recurring self-measurements like mood, energy, pain, as well as habits and goals.", invoke_without_command=True,)
app.add_typer(time.app, name="time", help="Track time in categories like resting, working, socializing.")
app.add_typer(task.app, name="task", help="Create, track, and complete actionable tasks.")
app.add_typer(report.app, name="report", help="View detailed reports and insights.")
app.add_typer(environmental_sync.app, name="env", help="Sync and view environmental data.")


@app.command("help")
def help_command():
    """Show a categorized list of available commands with Rich styling."""
    table = Table(title="🧠 Lifelog CLI – Command Guide", show_lines=True, expand=True)
    table.add_column("Category", style="bold magenta", no_wrap=True)
    table.add_column("Command Examples", style="cyan")

    table.add_row(
        "Habit and Metric Tracking",
        """\
llog track add mood scale --min 1 --max 10
llog track list
llog track mood 7 "Feeling decent" +morning"""
    )

    table.add_row(
        "Time Tracking",
        """\
llog time start work
llog time stop
llog time status"""
    )

    table.add_row(
        "Task Management",
        """\
llog task add "Clean desk" --project Home --due tomorrow
llog task list --project Home
llog task 42
llog task modify 42 --title "Tidy desk"
llog task done 42"""
    )
    
    table.add_row(
        "Reporting and Insights",
        """\
llog report summary        # Quick summaries (time, tasks, habits)
llog report diagnostics    # Diagnostic analytics (e.g. low mood root causes)
llog report correlations   # Top metric correlations
llog report predict        # Forecast future tracker trends
llog report prescribe      # Prescriptive advice based on patterns
llog report describe       # Descriptive analytics overview"""
    )
    console.print(table)
    console.print(Panel.fit("[italic green]Tip:[/] Use [bold]--help[/bold] on any command to see options.\nExample: [bold yellow]llog report --help[/bold yellow]"))

@app.command("entry", add_help_option=False)
def shortcut_entry(
    args: List[str] = typer.Argument(..., help="Usage: llog entry <tracker> <value> ['notes'] [+tags]")
):
    """
    Shortcut alias for `track.entry` to allow quick entry like: `llog entry mood 5 'Feeling okay' +evening`
    """
    from commands.track import track

    if len(args) < 2:
        console.print("[bold red]Usage:[/bold red] llog entry <tracker> <value> [notes] [+tags]")
        raise typer.Exit(code=1)

    name = args[0]
    value = args[1]
    extras = args[2:] if len(args) > 2 else []

    track(name, value, extras)

@app.command("task")
def task_detail(task_id: Optional[int] = None):
    """
    Show details of a specific task by ID.
    """
    if task_id:
        return task.info(task_id)

@app.command("init")
def init_data():
    """
    Initialize default data files and starter entries.
    """
    console.print("[bold green]🛠 Initializing Lifelog...[/bold green]")

    files_to_create = {
        TIME_FILE: {"history": []},
        LOG_FILE: {
            "habits": [
                {"name": "Take Vitamins", "description": "Daily multivitamin"},
                {"name": "Drink Water", "description": "Track hydration throughout the day"},
                {"name": "Sleep Before Midnight", "description": "Go to bed before 12am"},
            ],
            "log": []
        }
    }

    for path, default_data in files_to_create.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(default_data, f, indent=2)
            console.print(f"[green]✅ Created[/green] {path}")
        else:
            console.print(f"[yellow]⚠️ Already exists[/yellow] {path}")
    
    INIT_MARKER.touch()

sync_app = typer.Typer(help="Pull external data sources into lifelog.")
sync_app.command()(environmental_sync.weather)
sync_app.command()(environmental_sync.air)
sync_app.command()(environmental_sync.moon)
sync_app.command()(environmental_sync.satellite)

app.add_typer(sync_app, name="sync", help="Fetch external environmental data")

def load_feedback_sayings():
    """Loads the feedback sayings from the JSON file."""
    if FEEDBACK_FILE.exists():
        try:
            with open(FEEDBACK_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[yellow]⚠️ Warning[/yellow]: Could not decode feedback sayings.")
    return {}

def get_feedback_saying(context):
    """Retrieves a random feedback saying for a given context."""
    sayings = load_feedback_sayings()
    if context in sayings and sayings[context]:
        return random.choice(sayings[context])
    return None


if __name__ == "__main__":
    app()