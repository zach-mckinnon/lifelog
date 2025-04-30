#!/usr/bin/env python3
# llog.py
''' 
Lifelog CLI
A command-line interface for tracking habits, time, tasks, and environmental data.
This CLI allows users to log their daily activities, manage tasks, and sync environmental data.
'''
from datetime import datetime
import json
from pathlib import Path
from tomlkit import table
import typer
import requests # type: ignore

from lifelog.commands.utils import get_quotes
import lifelog.config.config_manager as cf
from lifelog.config.cron_manager import apply_scheduled_jobs
from lifelog.commands import time, task, track, report, environmental_sync, debug
from lifelog.commands.utils import feedback

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


import faulthandler
faulthandler.enable()

# Constants for file paths
TRACK_FILE = None
TIME_FILE = None
TASK_FILE = None
FC_FILE = None
FEEDBACK_FILE = None
DAILY_QUOTE_FILE = None
ENV_DATA_FILE = None


# Initialize the config manager and ensure the files exist
app = typer.Typer(help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")
console = Console()

# Ensure the app is initialized
sync_app = typer.Typer(help="Pull external data sources into lifelog.")
sync_app.command()(environmental_sync.weather)
sync_app.command()(environmental_sync.air)
sync_app.command()(environmental_sync.moon)
sync_app.command()(environmental_sync.satellite)
app.add_typer(sync_app, name="sync", help="Fetch external environmental data")

# Register all modules
app.add_typer(track.app, name="track", help="Track recurring self-measurements like mood, energy, pain, as well as habits and goals.", invoke_without_command=True,)
app.add_typer(time.app, name="time", help="Track time in categories like resting, working, socializing.")
app.add_typer(task.app, name="task", help="Create, track, and complete actionable tasks.")
app.add_typer(report.app, name="report", help="View detailed reports and insights.")
app.add_typer(environmental_sync.app, name="env", help="Sync and view environmental data.")
app.add_typer(debug.app, name="debug", help="Debugging and development tools.")

@app.callback(invoke_without_command=True)
def _ensure(ctx: typer.Context):
    """
    This runs before *any* command.
    """
    ensure_initialized()
    # if they typed nothing at all, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("help")
def help_command():
    """
    llog help - Show help information for the CLI.  
    """

    table = Table(title="🧠 Lifelog CLI – Command Guide", show_lines=True, expand=True)
    table.add_column("Command Examples", style="cyan")

    # Add actual rows
    table.add_row(
    "[bold purple]Trackers[/bold purple] 📊",
    "[bold green]Add[/bold green]: Define a new thing you want to track (like steps, mood, or water intake). You need to give it a [italic]title[/italic] and specify the [italic]type[/italic] of data it will store ([mono]int[/mono], [mono]float[/mono], [mono]bool[/mono], or [mono]str[/mono]). You can also add a category (e.g., [mono]llog track add Steps --type int --category Health[/mono])\n"
    "[bold blue]Record[/bold blue]: (Use without a subcommand) Log a new value for an existing tracker. Just type the tracker's [italic]title[/italic] followed by the [italic]value[/italic] (e.g., [mono]llog track Water 2.5[/mono] or [mono]llog track Mood Happy[/mono]). If the title matches a command, use that command instead.\n"
    "[bold yellow]Modify[/bold yellow]: Change the [italic]title[/italic], [italic]category[/italic], [italic]tags[/italic], or [italic]notes[/italic] of an existing tracker using its [italic]ID[/italic] (find the ID with 'list'). (e.g., [mono]llog track modify 3 New Mood --category Wellbeing +positive[/mono])\n"
    "[bold magenta]List[/bold magenta]: Show all the trackers you have defined, along with their details, type, category, and any goals you've set (e.g., [mono]llog track list[/mono])\n"
)
    table.add_row(
    "[bold blue]Time Tracking[/bold blue] ⏱️",
    "[bold green]Start[/bold green]: Begin tracking time for an activity. You need to give it a [italic]title[/italic] (use quotes for spaces!). You can also add a category, project, or even a time in the past to start from (e.g., [mono]llog time start \"Working on report\" --project Office[/mono] or [mono]llog time start Reading --past \"30 minutes ago\"[/mono])\n"
    "[bold red]Stop[/bold red]: End the current time tracking session. You can optionally add tags or notes when you stop (e.g., [mono]llog time stop +interruption Note: Had a coffee break[/mono])\n"
    "[bold cyan]Status[/bold cyan]: See what activity you are currently tracking and since when (e.g., [mono]llog time status[/mono])\n"
    "[bold magenta]Summary[/bold magenta]: Get a summary of the time you've tracked, grouped by activity title, category, or project. You can also filter by day, week, or month (e.g., [mono]llog time summary[/mono] or [mono]llog time summary --by category --period week[/mono])\n"
)
    table.add_row(
    "[bold green]Tasks[/bold green] ✅",
    "[bold blue]Info[/bold blue]: See details for a task using its [italic]ID[/italic] (e.g., [mono]llog task info 3[/mono])\n"
    "[bold green]Add[/bold green]: Create a new task (e.g., [mono]llog task add Buy groceries[/mono])\n"
    "[bold cyan]Start[/bold cyan]: Begin working on a task using its [italic]ID[/italic] (e.g., [mono]llog task start 5[/mono])\n"
    "[bold magenta]List[/bold magenta]: Show all your current tasks (try adding [mono]--help[/mono] for sorting and filtering!)\n"
    "[bold yellow]Modify[/bold yellow]: Change details of a task using its [italic]ID[/italic] (e.g., [mono]llog task modify 2 --due tomorrow[/mono])\n"
    "[bold red]Delete[/bold red]: Remove a task using its [italic]ID[/italic] (e.g., [mono]llog task delete 1[/mono])\n"
    "[bold orange]Stop[/bold orange]: Pause the task you are currently working on\n"
    "[bold purple]Done[/bold purple]: Mark a task as finished using its [italic]ID[/italic] (e.g., [mono]llog task done 4[/mono])\n"
)

    console.print(table)
    console.print(
        Panel.fit(
            "[italic green]Tip:[/] Use [bold]--help[/bold] after any command to see available options.\n\nExample: [bold yellow]llog task --help[/bold yellow]",
            title="💡 Usage Tip",
            title_align="left"
        )
    )


def ensure_initialized():
    global TRACK_FILE, TIME_FILE, TASK_FILE, FC_FILE, FEEDBACK_FILE, DAILY_QUOTE_FILE, ENV_DATA_FILE
    TRACK_FILE = cf.get_track_file()
    TIME_FILE = cf.get_time_file()
    TASK_FILE = cf.get_task_file()
    FC_FILE = cf.get_fc_file()
    FEEDBACK_FILE = cf.get_feedback_file()
    DAILY_QUOTE_FILE = cf.get_motivational_quote_file()
    ENV_DATA_FILE = cf.get_env_data_file()

    doc = cf.load_config()
    if not doc.get("meta", {}).get("initialized", False):
        init()
    else:
        if check_first_command_of_day():
            greet_user()
            save_first_command_flag(str(datetime.now().date()))


def init():
    """
    Initialize default data files and starter entries.
    """
    console.print("[bold green]🛠 Initializing Lifelog...[/bold green]")
    
    global TRACK_FILE, TIME_FILE, TASK_FILE, FC_FILE, FC_FILE, FEEDBACK_FILE, DAILY_QUOTE_FILE, ENV_DATA_FILE
    TRACK_FILE = cf.get_track_file()
    TIME_FILE = cf.get_time_file()
    TASK_FILE = cf.get_task_file()
    FC_FILE = cf.get_fc_file()
    FEEDBACK_FILE = cf.get_feedback_file()
    DAILY_QUOTE_FILE = cf.get_motivational_quote_file()
    ENV_DATA_FILE = cf.get_env_data_file()

    files_to_create = {
        TRACK_FILE: {
            "trackers": [],
        },
        TIME_FILE: {
            "history": []
        },
        TASK_FILE: [],
        FC_FILE: {
            "last_executed": None
        },
        FEEDBACK_FILE: {
            "sayings": {}
        },
        DAILY_QUOTE_FILE: {
            "quotes": []
        },
        ENV_DATA_FILE: {
            "weather": {},
            "air_quality": {},
            "moon": {},
            "satellite": {}
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
    FEEDBACK_FILE = cf.get_feedback_file()

    sayings = feedback.default_feedback_sayings()
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(sayings, f, indent=2)
    console.print("[green]✅ Created default feedback sayings![/green]")

    doc = cf.load_config()
    cron_section = doc.get("cron", table())
    if "recur_auto" not in cron_section:
        cron_section["recur_auto"] = {
            "schedule": "0 0 * * *",
            "command": "llog task auto_recur"
        }
        doc["cron"] = cron_section
        cf.save_config(doc)
        doc = cf.load_config() 
        apply_scheduled_jobs()
        console.print("[green]✅ Recurrence system initialized. Auto-recur will run nightly.[/green]")
    else:
        console.print("[yellow]⚡ Auto-recur schedule already exists.[/yellow]")

    get_user_location()

    # mark it done
    doc = cf.load_config()
    doc.setdefault("meta", {})
    doc["meta"]["initialized"] = True
    cf.save_config(doc)


def check_first_command_of_day():
    today = datetime.now().date()
    flag_data = {}

    if FC_FILE.exists():
        try:
            with open(FC_FILE, "r") as f:
                flag_data = json.load(f)
        except json.JSONDecodeError:
            console.print("[yellow]⚠️ Warning[/yellow]: Could not read first command flag.")

    last_executed_date = flag_data.get("last_executed")

    if last_executed_date != str(today):
        save_first_command_flag(str(today))
        return True
    return False


def save_first_command_flag(date_str):
    '''Saves the date of the first command executed today.'''
    FC_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(FC_FILE, "w") as f:
            json.dump({"last_executed": date_str}, f)
    except IOError:
        console.print(f"[yellow]⚠️ Warning[/yellow]: Could not save first command flag.")

# Example integration:
@app.command("hello")
def greet_user():
    '''Greets the user with a daily quote if available.'''
    daily_quote = get_quotes.get_motivational_quote()
    if daily_quote:
        console.print(f"[bold green]☀️ Good day![/bold green] Here's your daily inspiration: [italic]{daily_quote}[/italic]")
        
    else:
        console.print("[bold green]☀️ Good day![/bold green]")


def get_user_location():
    '''
    Attempts to get the user's location using IP geolocation.   
    If successful, it prompts the user to confirm the detected ZIP code.
    If the user declines, it falls back to manual entry.
    '''
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
                cfg = cf.load_config()
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
            cfg = cf.load_config()
            cfg["location"] = {"zip": zip_code}
            cf.save_config(cfg) 
            break
        else:
            print("Please enter a valid 5-digit ZIP code.")

# TODO: Add a command to list different config options and their current values, such as categories, projects, etc.
# TODO: Add a command to configure user preferences, such as default categories, projects, location, etc. 


lifelog_app = app

if __name__ == "__main__":
    ensure_initialized()
    lifelog_app()