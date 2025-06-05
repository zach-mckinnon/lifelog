#!/usr/bin/env python3
# llog.py
''' 
Lifelog CLI
A command-line interface for tracking habits, time, tasks, and environmental data.
This CLI allows users to log their daily activities, manage tasks, and sync environmental data.
'''
import curses
from datetime import datetime
import sqlite3
import sys
from typing import Annotated
import typer

from lifelog.first_time_run import LOGO_SMALL, run_wizard
from lifelog.utils.db import database_manager
import lifelog.config.config_manager as cf
from lifelog.commands import task_module, time_module, track_module, report, environmental_sync
from lifelog.ui import main as ui_main
from lifelog.utils import get_quotes

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


# Initialize the config manager and ensure the files exist
app = typer.Typer(
    help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")
console = Console()

# -------------------------------------------------------------------
# Core Initialization System
# -------------------------------------------------------------------


# Ensure the app is initialized
sync_app = typer.Typer(help="Pull external data sources into lifelog.")
sync_app.command()(environmental_sync.weather)
sync_app.command()(environmental_sync.air)
sync_app.command()(environmental_sync.moon)
sync_app.command()(environmental_sync.satellite)
app.add_typer(sync_app, name="sync", help="Fetch external environmental data")

# Register all modules
app.add_typer(track_module.app, name="track",
              help="Track recurring self-measurements like mood, energy, pain, as well as habits and goals.")
app.add_typer(time_module.app, name="time",
              help="Track time in categories like resting, working, socializing.")
app.add_typer(task_module.app, name="task",
              help="Create, track, and complete actionable tasks.")
app.add_typer(report.app, name="report",
              help="View detailed reports and insights.")
# app.add_typer(environmental_sync.app, name="env",
#               help="Sync and view environmental data.")


def initialize_application():
    """Full application initialization sequence"""
    try:
        console.print(
            "[bold green]🚀 Starting Lifelog initialization...[/bold green]")

        # 1. Ensure base directory exists
        cf.BASE_DIR.mkdir(parents=True, exist_ok=True)
        console.print(f"[dim]• Created base directory: {cf.BASE_DIR}[/dim]")

        # 2. Initialize database schema
        if not database_manager.is_initialized():
            database_manager.initialize_schema()
            console.print("[dim]• Database schema initialized[/dim]")

        # 3. Load or create config
        config = cf.load_config()
        console.print("[dim]• Configuration loaded[/dim]")

        # 4. Run first-time wizard if needed
        if not config.get("meta", {}).get("first_run_complete", False):
            config = run_wizard(config)
            cf.save_config(config)

        # 5. Check for first command of the day
        if check_first_command_of_day():
            greet_user()
            save_first_command_flag(str(datetime.now().date()))

        return True
    except Exception as e:
        console.print(f"[red]⚠️ Critical initialization error: {e}[/red]")
        sys.exit(1)


@app.command("ui")
def ui(
    status_bar: Annotated[bool, typer.Option(
        "--no-help", help="Disable the help bar.")] = False
):
    """Launch the full-screen Lifelog TUI"""
    curses.wrapper(ui_main, status_bar)


@app.command("help")
def help_command():
    """
    llog help - Show help information for the CLI.  
    """

    table = Table(title="🧠 Lifelog CLI – Command Guide",
                  show_lines=True, expand=True)
    table.add_column("Command Examples", style="cyan")

    # Add actual rows
    table.add_row(
        "[bold purple]llog track[/bold purple] 📊",
        "Track habits, mood, health metrics\n"
        "Use --help for all options"
    )
    table.add_row(
        "[bold blue]llog time[/bold blue] ⏱️",
        "Track time spent on activities\n"
        "Use --help for all options"
    )
    table.add_row(
        "[bold green]llog task[/bold green] ✅",
        "Manage and complete tasks\n"
        "Use --help for all options"
    )
    table.add_row(
        "[bold cyan]llog report[/bold cyan] 📈",
        "View detailed reports and insights\n"
        "Use --help for all options"
    )
    table.add_row(
        "[bold magenta]llog ui[/bold magenta] 💻",
        "Launch full-screen interface\n"
        "Use --help for all options"
    )

    console.print(table)
    console.print(
        Panel.fit(
            "[italic green]Tip:[/] Use [bold]--help[/bold] after any command to see available options.\n\nExample: [bold yellow]llog task --help[/bold yellow]",
            title="💡 Usage Tip",
            title_align="left"
        )
    )


@app.command("config-edit")
def config_edit():
    """
    Interactive config editor. Change aliases, categories, category importance, etc.
    """
    import lifelog.config.config_manager as cf

    def select_section():
        print("\nWhat config section would you like to edit?")
        print("1) Aliases")
        print("2) Category Importance")
        print("3) Categories")
        print("q) Quit")
        return input("> ").strip()

    def edit_aliases():
        while True:
            aliases = cf.list_config_section("aliases")
            print("\nCurrent Aliases:")
            for k, v in aliases.items():
                print(f"  {k}: {v}")
            print("a) Add/Edit alias")
            print("d) Delete alias")
            print("q) Back")
            choice = input("> ").strip()
            if choice == "a":
                alias = input("Alias key: ").strip()
                val = input("Alias value: ").strip()
                cf.set_config_value("aliases", alias, val)
                print(f"Set alias '{alias}' = '{val}'")
            elif choice == "d":
                alias = input("Alias key to delete: ").strip()
                cf.delete_config_value("aliases", alias)
                print(f"Deleted alias '{alias}'")
            elif choice == "q":
                break

    def edit_category_importance():
        while True:
            catimps = cf.list_config_section("category_importance")
            print("\nCurrent Category Importance:")
            for k, v in catimps.items():
                print(f"  {k}: {v}")
            print("a) Add/Edit importance")
            print("d) Delete importance")
            print("q) Back")
            choice = input("> ").strip()
            if choice == "a":
                cat = input("Category: ").strip()
                val = input("Importance value (e.g. 1.2): ").strip()
                try:
                    valf = float(val)
                    cf.set_config_value("category_importance", cat, valf)
                    print(f"Set category importance '{cat}' = {valf}")
                except ValueError:
                    print("Not a valid number!")
            elif choice == "d":
                cat = input("Category to remove: ").strip()
                cf.delete_config_value("category_importance", cat)
                print(f"Deleted importance for '{cat}'")
            elif choice == "q":
                break

    def edit_categories():
        while True:
            cats = cf.list_config_section("categories")
            print("\nCurrent Categories:")
            for k, v in cats.items():
                print(f"  {k}: {v}")
            print("a) Add/Edit category")
            print("d) Delete category")
            print("q) Back")
            choice = input("> ").strip()
            if choice == "a":
                cat = input("Category key: ").strip()
                desc = input("Description: ").strip()
                cf.set_category_description(cat, desc)
                print(f"Set category '{cat}' = '{desc}'")
            elif choice == "d":
                cat = input("Category key to delete: ").strip()
                cf.delete_category(cat)
                print(f"Deleted category '{cat}'")
            elif choice == "q":
                break

    while True:
        section = select_section()
        if section == "1":
            edit_aliases()
        elif section == "2":
            edit_category_importance()
        elif section == "3":
            edit_categories()
        elif section == "q":
            print("Config edit complete.")
            break
        else:
            print("Invalid selection.")


def show_daily_banner():
    """Show daily welcome banner with logo"""
    console.print(Panel(LOGO_SMALL, style="bold cyan", expand=False))
    console.print(Panel(
        f"[bold]Good {get_time_of_day()}![/bold] "
        f"Ready for a productive day?",
        style="green"
    ))


def get_time_of_day():
    """Return time-appropriate greeting"""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"

# Update greet_user function


def greet_user():
    """Greet user with daily quote"""
    try:
        # Show daily banner
        console.print(Panel(
            "L I F E L O G",
            style="bold cyan",
            expand=False
        ))
        console.print(Panel(
            f"[bold]Good {get_time_of_day()}![/bold] Ready for a productive day?",
            style="green"
        ))

        # Show quote if available
        try:
            if quote := get_quotes.get_motivational_quote():
                console.print(
                    f"\n[bold]Daily Inspiration:[/bold]\n[italic]{quote}[/italic]"
                )
        except Exception as e:
            console.print(f"[dim]Couldn't load quote: {e}[/dim]")

    except Exception as e:
        console.print(f"[red]Error in greeting: {e}[/red]")
# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------


def check_first_command_of_day() -> bool:
    """Check if this is the first command execution today"""
    today = datetime.now().date()

    try:
        with database_manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT last_executed FROM first_command_flags WHERE id = 1"
            )
            row = cur.fetchone()

            if not row or not row[0]:
                return True

            # Handle different date formats
            try:
                last_executed = datetime.strptime(row[0], "%Y-%m-%d").date()
            except ValueError:
                try:
                    last_executed = datetime.strptime(
                        row[0], "%Y-%m-%d %H:%M:%S").date()
                except ValueError:
                    return True

            return last_executed != today

    except sqlite3.Error as e:
        console.print(f"[yellow]⚠️ Database warning: {e}[/yellow]")
        return True


def save_first_command_flag(date_str: str):
    """Save execution date to database"""
    try:
        with database_manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO first_command_flags (id, last_executed) "
                "VALUES (1, ?)",
                (date_str,)
            )
            conn.commit()
    except sqlite3.Error as e:
        console.print(f"[red]⚠️ Failed to save command flag: {e}[/red]")

# Add to llog.py


@app.command("api-start")
def start_api(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(5000, help="Port to listen on"),
    debug: bool = typer.Option(False, help="Enable debug mode")
):
    """Start the REST API server"""
    import os
    from lifelog.app import app

    # Ensure initialization
    initialize_application()

    console.print(
        f"[green]🚀 Starting API server at http://{host}:{port}[/green]")
    os.environ["FLASK_ENV"] = "development" if debug else "production"
    app.run(host=host, port=port, debug=debug)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """Global initialization and command routing"""
    initialize_application()

    if ctx.invoked_subcommand is None:
        help_command()


lifelog_app = app

if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]🚪 Exiting...[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]⚠️ Unhandled error: {e}[/red]")
        sys.exit(1)
