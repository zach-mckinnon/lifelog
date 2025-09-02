#!/usr/bin/env python3
# Lifelog - A terminal-based health/life tracker
# Copyright (C) 2024 Zach McKinnon
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
''' 
Lifelog CLI
A command-line interface for tracking habits, time, tasks, and environmental data.
This CLI allows users to log their daily activities, manage tasks, and sync environmental data.
'''
import logging
import curses
from datetime import datetime
import os
import time
from pathlib import Path
import sqlite3
import sys
from typing import Annotated
import requests
import typer

from lifelog.config.schedule_manager import apply_scheduled_jobs
from lifelog.first_time_run import LOGO_SMALL, run_wizard
from lifelog.utils.db import database_manager
import lifelog.config.config_manager as cf
from lifelog.commands import api_module, task_module, time_module, track_module, report, environmental_sync, hero
from lifelog.ui import main as ui_main
from lifelog.utils import get_quotes

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lifelog.utils.db import auto_sync, get_connection, should_sync
from lifelog.utils import hooks as hooks_util
from lifelog.utils import log_utils
from lifelog.commands import start_day
from lifelog.utils.gamification_seed import run_seed
from lifelog.utils.db.gamify_repository import _ensure_profile, get_unread_notifications


# Initialize the config manager and ensure the files exist
app = typer.Typer(
    help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")

console = Console()
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Core Initialization System
# -------------------------------------------------------------------


# Ensure the app is initialized
sync_app = typer.Typer(help="Pull external data sources into lifelog.")
app.add_typer(start_day.app, name="start-day",
              help="Guided, motivational start-of-day routine")

# TODO: Implement the gamification module later as optional.
# app.add_typer(hero.app, name="hero",
#               help="🏰 Hero: profile, badges, skills & shop")
app.add_typer(track_module.app, name="track",
              help="Track recurring self-measurements and goals.")
app.add_typer(time_module.app, name="time",
              help="Track time in categories like resting, working, socializing.")
app.add_typer(task_module.app, name="task",
              help="Create, track, and complete actionable tasks.")
app.add_typer(report.app, name="report",
              help="View detailed reports and insights.")
app.add_typer(environmental_sync.app, name="environment sync",
              help="Sync data about your local weather.")
app.add_typer(api_module.app, name="api",
              help="API server control & device pairing")

# TODO: Fix UI for small screens and implement later.
# @app.command("ui")
# def ui(
#     no_help: Annotated[bool, typer.Option(
#         "--no-help", is_flag=True, help="Disable the help bar.")] = False
# ):
#     """
#     Launch the full-screen Lifelog TUI.
#     - Ensures initialization.
#     - Runs auto-sync if needed (logs warnings on failure).
#     - Wraps the curses UI; logs and prints any errors launching TUI.
#     """
#     # → Ensure logging is set up before any logs
#     log_utils.setup_logging()

#     try:
#         ensure_app_initialized()
#     except Exception as e:
#         logger.error(
#             f"Initialization failed before launching UI: {e}", exc_info=True)
#         console.print(f"[red]Initialization error: {e}[/red]")
#         raise typer.Exit(1)

#     show_status = not no_help

#     # Auto-sync before launching UI
#     if should_sync():
#         try:
#             auto_sync()
#         except Exception as e:
#             # Log the full stack; show a brief warning to user
#             logger.warning("Auto-sync failed before TUI launch", exc_info=True)
#             console.print(f"[yellow]⚠️ Auto-sync failed: {e}[/yellow]")
#             # Pause briefly so user sees the message before full-screen UI
#             time.sleep(1.5)

#     # Launch the curses-based UI
#     try:
#         curses.wrapper(ui_main, show_status)
#     except Exception as e:
#         logger.error(f"Error in TUI main: {e}", exc_info=True)
#         console.print(f"[red]TUI failed to launch: {e}[/red]")
#         raise typer.Exit(1)


@app.command("setup")
def setup_command():
    """Run initial setup wizard"""
    # 1️⃣ Set up logging and ensure base dir
    log_utils.setup_logging()
    cf.BASE_DIR.mkdir(parents=True, exist_ok=True)

    # 2️⃣ Initialize DB schema + seed badges/skills if this is the first time
    from lifelog.utils.db.database_manager import is_initialized, initialize_schema
    from lifelog.utils.gamification_seed import run_seed

    if not is_initialized():
        initialize_schema()
        console.print("[dim]• Database schema initialized[/dim]")
        run_seed()
        console.print("[dim]• Initial data seeded[/dim]")

    # 3️⃣ Load (or create) the config file
    try:
        config = cf.load_config()
    except Exception as e:
        logger.error(f"Failed to load config in setup: {e}", exc_info=True)
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)

    # 4️⃣ Run the wizard if not already done
    first_done = config.get("meta", {}).get("first_run_complete", False)
    if not first_done:
        config = run_wizard(config)
        saved = cf.save_config(config)
        if not saved:
            logger.error("Failed to save config after wizard")
            console.print(
                "[red]⚠️ Configuration save failed after setup.[/red]")
        console.print("[green]✓ Setup completed successfully![/green]")
    else:
        if typer.confirm("Setup already completed. Run again?", default=False):
            config = run_wizard(config)
            saved = cf.save_config(config)
            if not saved:
                logger.error("Failed to save config after re-running wizard")
                console.print(
                    "[red]⚠️ Configuration save failed after setup.[/red]")
            console.print("[green]✓ Setup re-configured![/green]")
        else:
            console.print("[yellow]Setup aborted[/yellow]")


@app.command("config-edit")
def config_edit():
    """
    Interactive config editor. Change aliases, categories, category importance, etc.
    Uses console.print for output and input(...) calls for user input.
    """

    def select_section() -> str:
        console.print("\nWhat config section would you like to edit?")
        console.print("1) Aliases")
        console.print("2) Category Importance")
        console.print("3) Categories")
        console.print("q) Quit")
        return input("> ").strip()

    def edit_aliases():
        while True:
            try:
                aliases = cf.list_config_section("aliases")
            except Exception as e:
                logger.error(f"Failed to list aliases: {e}", exc_info=True)
                console.print(f"[red]Error reading aliases: {e}[/red]")
                return
            console.print("\nCurrent Aliases:")
            for k, v in aliases.items():
                console.print(f"  {k}: {v}")
            console.print("a) Add/Edit alias")
            console.print("d) Delete alias")
            console.print("q) Back")
            choice = input("> ").strip()
            if choice == "a":
                alias = input("Alias key: ").strip()
                val = input("Alias value: ").strip()
                try:
                    success = cf.set_config_value("aliases", alias, val)
                    if not success:
                        console.print(
                            f"[red]Failed to save alias '{alias}'.[/red]")
                    else:
                        console.print(
                            f"[green]Set alias '{alias}' = '{val}'[/green]")
                except Exception as e:
                    logger.error(
                        f"Error setting alias '{alias}': {e}", exc_info=True)
                    console.print(f"[red]Error setting alias: {e}[/red]")
            elif choice == "d":
                alias = input("Alias key to delete: ").strip()
                try:
                    success = cf.delete_config_value("aliases", alias)
                    if not success:
                        console.print(
                            f"[red]Failed to delete alias '{alias}'.[/red]")
                    else:
                        console.print(
                            f"[green]Deleted alias '{alias}'[/green]")
                except Exception as e:
                    logger.error(
                        f"Error deleting alias '{alias}': {e}", exc_info=True)
                    console.print(f"[red]Error deleting alias: {e}[/red]")
            elif choice == "q":
                break
            else:
                console.print("[yellow]Invalid choice[/yellow]")

    def edit_category_importance():
        while True:
            try:
                catimps = cf.list_config_section("category_importance")
            except Exception as e:
                logger.error(
                    f"Failed to list category_importance: {e}", exc_info=True)
                console.print(
                    f"[red]Error reading category importance: {e}[/red]")
                return
            console.print("\nCurrent Category Importance:")
            for k, v in catimps.items():
                console.print(f"  {k}: {v}")
            console.print("a) Add/Edit importance")
            console.print("d) Delete importance")
            console.print("q) Back")
            choice = input("> ").strip()
            if choice == "a":
                cat = input("Category: ").strip()
                val = input("Importance value (e.g. 1.2): ").strip()
                try:
                    valf = float(val)
                    success = cf.set_config_value(
                        "category_importance", cat, valf)
                    if not success:
                        console.print(
                            f"[red]Failed to save importance for '{cat}'.[/red]")
                    else:
                        console.print(
                            f"[green]Set category importance '{cat}' = {valf}[/green]")
                except ValueError:
                    console.print("[red]Not a valid number![/red]")
                except Exception as e:
                    logger.error(
                        f"Error setting category importance '{cat}': {e}", exc_info=True)
                    console.print(f"[red]Error: {e}[/red]")
            elif choice == "d":
                cat = input("Category to remove: ").strip()
                try:
                    success = cf.delete_config_value(
                        "category_importance", cat)
                    if not success:
                        console.print(
                            f"[red]Failed to delete importance for '{cat}'.[/red]")
                    else:
                        console.print(
                            f"[green]Deleted importance for '{cat}'[/green]")
                except Exception as e:
                    logger.error(
                        f"Error deleting category importance '{cat}': {e}", exc_info=True)
                    console.print(f"[red]Error: {e}[/red]")
            elif choice == "q":
                break
            else:
                console.print("[yellow]Invalid choice[/yellow]")

    def edit_categories():
        while True:
            try:
                cats = cf.list_config_section("categories")
            except Exception as e:
                logger.error(f"Failed to list categories: {e}", exc_info=True)
                console.print(f"[red]Error reading categories: {e}[/red]")
                return
            console.print("\nCurrent Categories:")
            for k, v in cats.items():
                console.print(f"  {k}: {v}")
            console.print("a) Add/Edit category")
            console.print("d) Delete category")
            console.print("q) Back")
            choice = input("> ").strip()
            if choice == "a":
                cat = input("Category key: ").strip()
                desc = input("Description: ").strip()
                try:
                    success = cf.set_category_description(cat, desc)
                    if not success:
                        console.print(
                            f"[red]Failed to save category '{cat}'.[/red]")
                    else:
                        console.print(
                            f"[green]Set category '{cat}' = '{desc}'[/green]")
                except Exception as e:
                    logger.error(
                        f"Error setting category '{cat}': {e}", exc_info=True)
                    console.print(f"[red]Error: {e}[/red]")
            elif choice == "d":
                cat = input("Category key to delete: ").strip()
                try:
                    success = cf.delete_category(cat)
                    if not success:
                        console.print(
                            f"[red]Failed to delete category '{cat}'.[/red]")
                    else:
                        console.print(
                            f"[green]Deleted category '{cat}'[/green]")
                except Exception as e:
                    logger.error(
                        f"Error deleting category '{cat}': {e}", exc_info=True)
                    console.print(f"[red]Error: {e}[/red]")
            elif choice == "q":
                break
            else:
                console.print("[yellow]Invalid choice[/yellow]")

    # Main loop
    while True:
        section = select_section()
        if section == "1":
            edit_aliases()
        elif section == "2":
            edit_category_importance()
        elif section == "3":
            edit_categories()
        elif section == "q":
            console.print("[green]Config edit complete.[/green]")
            break
        else:
            console.print("[yellow]Invalid selection.[/yellow]")


@app.command("sync")
def sync_command():
    """
    Sync pending changes with the server (client mode only).
    """
    log_utils.setup_logging()
    try:
        from lifelog.utils.db import process_sync_queue
        process_sync_queue()
        console.print("[green]Sync completed![/green]")
    except Exception as e:
        logger.error(f"Sync command failed: {e}", exc_info=True)
        console.print(f"[red]Sync failed: {e}[/red]")
        raise typer.Exit(1)


@app.command("backup")
def backup_command(
    output: Annotated[str, typer.Argument(
        help="Output file path", show_default=False)] = None
):
    """
    Create a backup of the lifelog database.
    - Copies the SQLite DB file to the given output path or a timestamped default.
    """
    from lifelog.utils.shared_utils import now_utc
    log_utils.setup_logging()
    try:
        db_path = cf.BASE_DIR / "lifelog.db"
        if not db_path.exists():
            console.print("[red]Database file not found![/red]")
            raise typer.Exit(1)
        timestamp = now_utc()
        output_path = output or f"lifelog_backup_{timestamp}.db"
        import shutil
        shutil.copy2(db_path, output_path)
        console.print(f"[green]✓ Backup created at: {output_path}[/green]")
    except Exception as e:
        logger.error(f"Backup command failed: {e}", exc_info=True)
        console.print(f"[red]Backup failed: {e}[/red]")
        raise typer.Exit(1)


def initialize_application():
    """
    Full application initialization sequence.
    - Ensures base directory exists.
    - Initializes DB schema if needed.
    - Loads config and ensures hooks directory.
    - Exits (1) if first-run not complete.
    """
    from lifelog.utils.shared_utils import now_utc
    try:
        # 1. Ensure base directory exists
        cf.BASE_DIR.mkdir(parents=True, exist_ok=True)

        # 2. Initialize database schema if needed
        if not database_manager.is_initialized():
            database_manager.initialize_schema()
            run_seed()   # seed badges/skills

        # 3. Load or create config
        config = cf.load_config()
        hooks_util.ensure_hooks_dir()

        # 4. If first-run still not complete, tell the caller to invoke setup
        if not config.get("meta", {}).get("first_run_complete", False):
            # return False or sys.exit(1) so main_callback can handle it
            sys.exit(1)

        # All good
        return True

    except Exception as e:
        logger.error(f"Critical initialization error: {e}", exc_info=True)
        sys.exit(1)


def ensure_app_initialized():
    """
    Run setup wizard on first run, never block setup command itself.
    - Creates base directory, initializes DB if needed.
    - If first_run_complete is False and command isn't 'setup' or help, runs wizard.
    Returns loaded config dict.
    Exits on critical failure.
    """
    try:
        cf.BASE_DIR.mkdir(parents=True, exist_ok=True)
        # detect if we're running `llog setup`
        is_setup_cmd = any(arg in sys.argv for arg in (
            "setup", "--help", "-h", "help", "config-edit"))
        if not database_manager.is_initialized():
            # only auto-initialize for non-setup commands
            if not is_setup_cmd:
                initialize_application()
        try:
            apply_scheduled_jobs()

        except Exception as e:
            logger.warning(
                f"Failed to re-apply scheduled jobs on startup: {e}", exc_info=True)
        config = cf.load_config()
        if "meta" not in config:
            config["meta"] = {}
        if not config["meta"].get("first_run_complete", False):
            # Only auto-launch the wizard if the command isn't 'setup', 'help', or Typer built-ins
            is_setup_cmd = any(x in sys.argv for x in [
                               "setup", "--help", "-h", "help", "config-edit"])
            if not is_setup_cmd:
                # Interactive setup on first run for any user command
                console.print(Panel(
                    "[bold yellow]Welcome! Lifelog needs initial setup.[/bold yellow]\n"
                    "You'll only do this once.",
                    style="yellow"
                ))
                config = run_wizard(config)
                cf.save_config(config)
                console.print("[green]✓ Setup completed![/green]")
            elif "setup" in sys.argv:
                # Let setup command itself run as normal (don't block)
                pass
            else:
                # For help and others, just skip wizard
                pass
        return config
    except Exception as e:
        console.print(f"[red]⚠️ Initialization error: {e}[/red]")
        sys.exit(1)


def show_daily_banner():
    """
    Show daily welcome banner with logo.
    """
    log_utils.setup_logging()
    try:
        console.print(Panel(LOGO_SMALL, style="bold cyan", expand=False))
        console.print(Panel(
            f"[bold]Good {get_time_of_day()}![/bold] Ready for a productive day?",
            style="green"
        ))
    except Exception as e:
        logger.error(f"Error showing daily banner: {e}", exc_info=True)
        console.print(f"[red]Error showing banner: {e}[/red]")


def get_time_of_day() -> str:
    """
    Return time-appropriate greeting: morning, afternoon, evening, or night.
    """
    from lifelog.utils.shared_utils import now_local
    try:
        hour = now_local().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        return "night"
    except Exception as e:
        logger.warning(f"Error in get_time_of_day: {e}", exc_info=True)
        return ""


def greet_user():
    """
    Greet user with daily quote (if not in curses UI).
    """
    log_utils.setup_logging()
    # Skip banner in UI mode
    if "curses" in sys.modules:
        return
    try:
        console.print(Panel("L I F E L O G", style="bold cyan", expand=False))
        console.print(Panel(
            f"[bold]Good {get_time_of_day()}![/bold] Ready for a productive day?",
            style="green"
        ))
        try:
            if quote := get_quotes.get_motivational_quote():
                console.print(
                    f"\n[bold]Daily Inspiration:[/bold]\n[italic]{quote}[/italic]")
        except Exception as e:
            logger.warning(f"Couldn't load quote: {e}", exc_info=True)
            console.print(f"[dim]Couldn't load quote: {e}[/dim]")
    except Exception as e:
        logger.error(f"Error in greet_user: {e}", exc_info=True)
        console.print(f"[red]Error in greeting: {e}[/red]")


def check_first_command_of_day() -> bool:
    """
    Check if this is the first command execution today.
    - Returns True if first time today or on DB error.
    """
    from lifelog.utils.shared_utils import now_utc
    try:
        today = now_utc().date()
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT last_executed FROM first_command_flags WHERE id = 1")
            row = cur.fetchone()
            if not row or not row[0]:
                return True
            last = row[0]
            try:
                last_executed = datetime.strptime(last, "%Y-%m-%d").date()
            except ValueError:
                try:
                    last_executed = datetime.strptime(
                        last, "%Y-%m-%d %H:%M:%S").date()
                except ValueError:
                    return True
            return last_executed != today
    except sqlite3.Error as e:
        logger.warning(
            f"Database warning in check_first_command_of_day: {e}", exc_info=True)
        return True
    except Exception as e:
        logger.error(
            f"Unexpected error in check_first_command_of_day: {e}", exc_info=True)
        return True


def save_first_command_flag(date_str: str):
    """
    Save execution date to database for first-command-of-day logic.
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO first_command_flags (id, last_executed) "
                "VALUES (1, ?)",
                (date_str,)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to save first command flag: {e}", exc_info=True)
        console.print(f"[red]⚠️ Failed to save command flag: {e}[/red]")
    except Exception as e:
        logger.error(
            f"Unexpected error saving first command flag: {e}", exc_info=True)
        console.print(f"[red]Error saving command flag: {e}[/red]")


def main_callback(ctx: typer.Context):
    """
    Main callback before any command.
    - Sets up logging.
    - Runs a silent initialization (no console.print).
    - Then only prints notifications if present.
    """
    log_utils.setup_logging()
    try:
        initialize_application()
    except typer.Exit:
        # let typer handle exit cleanly (e.g. when first-run detects setup needed)
        raise
    except Exception as e:
        logger.error(
            f"Initialization error in main_callback: {e}", exc_info=True)
        console.print(f"[red]Initialization error: {e}[/red]")
        raise typer.Exit(1)

    # Optimize startup: only sync for commands that need data
    # Skip expensive sync operations for fast commands  
    if ctx.info_name and ctx.params.get("help") is not True and should_sync():
        try:
            auto_sync()
        except Exception as e:
            logger.warning(f"Auto-sync failed: {e}", exc_info=True)

    # Optimize startup: only check notifications for interactive commands
    # Skip notification check for fast commands like --help, --version
    if ctx.info_name and ctx.params.get("help") is not True:
        # Only do expensive database operations for actual commands
        try:
            profile = _ensure_profile()
            unread = get_unread_notifications(profile.id)
            if unread:
                console.print("[bold yellow]You have new notifications![/bold yellow]")
                console.print("Run `llog hero notify` to view them.")
        except Exception as e:
            # Don't let notification errors block the main command
            logger.warning(f"Notification check failed: {e}")


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
