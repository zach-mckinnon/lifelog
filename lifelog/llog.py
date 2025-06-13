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
import subprocess
import sys
from typing import Annotated
import requests
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

from lifelog.utils.db.db_helper import auto_sync, get_connection, should_sync
from lifelog.utils import hooks as hooks_util
from lifelog.utils import log_utils
from lifelog.commands import start_day

# Initialize the config manager and ensure the files exist
app = typer.Typer(
    help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")

console = Console()
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Core Initialization System
# -------------------------------------------------------------------
DOCKER_DIR = Path.home() / ".lifelog" / "docker"

# Ensure the app is initialized
sync_app = typer.Typer(help="Pull external data sources into lifelog.")
app.add_typer(start_day.app, name="start-day",
              help="Guided, motivational start-of-day routine")
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


@app.command("ui")
def ui(
    no_help: Annotated[bool, typer.Option(
        "--no-help", is_flag=True, help="Disable the help bar.")] = False
):
    """
    Launch the full-screen Lifelog TUI.
    - Ensures initialization.
    - Runs auto-sync if needed (logs warnings on failure).
    - Wraps the curses UI; logs and prints any errors launching TUI.
    """
    # → Ensure logging is set up before any logs
    log_utils.setup_logging()

    try:
        ensure_app_initialized()
    except Exception as e:
        logger.error(
            f"Initialization failed before launching UI: {e}", exc_info=True)
        console.print(f"[red]Initialization error: {e}[/red]")
        raise typer.Exit(1)

    show_status = not no_help

    # Auto-sync before launching UI
    if should_sync():
        try:
            auto_sync()
        except Exception as e:
            # Log the full stack; show a brief warning to user
            logger.warning("Auto-sync failed before TUI launch", exc_info=True)
            console.print(f"[yellow]⚠️ Auto-sync failed: {e}[/yellow]")
            # Pause briefly so user sees the message before full-screen UI
            time.sleep(1.5)

    # Launch the curses-based UI
    try:
        curses.wrapper(ui_main, show_status)
    except Exception as e:
        logger.error(f"Error in TUI main: {e}", exc_info=True)
        console.print(f"[red]TUI failed to launch: {e}[/red]")
        raise typer.Exit(1)


@app.command("setup")
def setup_command():
    """Run initial setup wizard"""
    log_utils.setup_logging()
    try:
        ensure_app_initialized()
    except Exception as e:
        logger.error(
            f"Initialization failed before launching UI: {e}", exc_info=True)
        console.print(f"[red]Initialization error: {e}[/red]")
        raise typer.Exit(1)
    try:
        cf.BASE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(
            f"Failed to create base directory {cf.BASE_DIR}: {e}", exc_info=True)
        console.print(f"[red]Failed to create base directory: {e}[/red]")
        raise typer.Exit(1)

    try:
        config = cf.load_config()
    except Exception as e:
        logger.error(f"Failed to load config in setup: {e}", exc_info=True)
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)

    try:
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
                    logger.error(
                        "Failed to save config after re-running wizard")
                    console.print(
                        "[red]⚠️ Configuration save failed after setup.[/red]")
                console.print("[green]✓ Setup re-configured![/green]")
            else:
                console.print("[yellow]Setup aborted[/yellow]")
    except Exception as e:
        logger.error(f"Setup wizard failed: {e}", exc_info=True)
        console.print(f"[red]⚠️ Setup failed: {e}[/red]")
        raise typer.Exit(1)


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


@app.command("get-server-url")
def get_server_url():
    """
    Print the correct API server URL for pairing client devices.
    - Checks Docker Compose setup first, then falls back to config or localhost.
    """
    log_utils.setup_logging()

    try:
        import socket
        import yaml
    except ImportError as e:
        logger.warning(
            f"Optional modules for get-server-url missing: {e}", exc_info=True)
        console.print(
            "[yellow]Warning: missing optional modules for Docker detection.[/yellow]")

    try:
        config = cf.load_config()
    except Exception as e:
        logger.error(
            f"Failed to load config in get-server-url: {e}", exc_info=True)
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)

    docker_dir = cf.BASE_DIR / "docker"
    compose_file = docker_dir / "docker-compose.yml"
    docker_used = False

    # 1. Check for Docker Compose and a running container
    if compose_file.exists():
        try:
            result = subprocess.run(
                ["docker", "compose", "-f",
                    str(compose_file), "ps", "-q", "lifelog-api"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
            )
            if result.stdout.strip():
                docker_used = True
        except Exception as e:
            logger.warning(
                f"Error checking Docker Compose status: {e}", exc_info=True)

    if docker_used:
        host_port = "5000"
        host_ip = "127.0.0.1"
        try:
            import yaml  # ensure yaml is available
            with open(compose_file, "r") as f:
                compose = yaml.safe_load(f)
            ports = compose.get("services", {}).get(
                "lifelog-api", {}).get("ports", [])
            if ports:
                # assume format "host:container"
                mapping = ports[0]
                if isinstance(mapping, str) and ":" in mapping:
                    host_port = mapping.split(":")[0]
        except Exception as e:
            logger.warning(
                f"Failed to parse docker-compose.yml: {e}", exc_info=True)
            # fallback host_port remains "5000"

        # Determine LAN IP
        try:
            hostname = socket.gethostname()
            host_ip = socket.gethostbyname(hostname)
            if host_ip.startswith("127."):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    host_ip = s.getsockname()[0]
                except Exception:
                    host_ip = "127.0.0.1"
                finally:
                    s.close()
        except Exception as e:
            logger.warning(f"Failed to detect LAN IP: {e}", exc_info=True)
            host_ip = "127.0.0.1"

        url = f"http://{host_ip}:{host_port}"
        console.print("[bold green]API server running in Docker.[/bold green]")
        console.print(f"[cyan]URL for client devices: {url}[/cyan]")
        return

    # 3. Fallback: Use config value or localhost
    server_url = config.get("deployment", {}).get(
        "server_url") or "http://localhost:5000"
    console.print("[bold green]API server running locally.[/bold green]")
    console.print(f"[cyan]URL for client devices: {server_url}[/cyan]")


@app.command("docker")
def docker_cmd(
    action: Annotated[str, typer.Argument(
        help="Action: up, down, restart, logs, status")] = "up"
):
    """
    Manage Lifelog Docker deployment. Actions: up, down, restart, logs, status.
    - Verifies docker-compose is available and Docker daemon is running.
    """
    log_utils.setup_logging()

    compose_file = DOCKER_DIR / "docker-compose.yml"
    docker_cmd = cf.find_docker_compose_cmd()
    if not docker_cmd:
        console.print(
            "[red]Neither 'docker compose' nor 'docker-compose' is available on your PATH.[/red]\n"
            "Please install Docker and Docker Compose first."
        )
        raise typer.Exit(1)
    if not compose_file.exists():
        console.print(
            f"[red]No docker-compose.yml found at {compose_file}.[/red]")
        console.print(
            "[yellow]You must run setup and create Docker files first.[/yellow]")
        raise typer.Exit(1)
    if not cf.is_docker_running():
        console.print(
            "[red]Docker engine is not running.[/red]\n"
            "Please start Docker Desktop (or your Docker daemon) before using this command."
        )
        raise typer.Exit(1)

    # Build docker command
    docker_args = docker_cmd + ["--project-directory", str(DOCKER_DIR)]
    if action == "up":
        docker_args += ["up", "-d", "--build"]
    elif action == "down":
        docker_args += ["down"]
    elif action == "restart":
        docker_args += ["restart"]
    elif action == "logs":
        docker_args += ["logs", "-f"]
    elif action == "status":
        docker_args += ["ps", "-a", "--filter", "name=lifelog-api"]
    else:
        console.print(
            "[red]Unknown action. Use up, down, restart, logs, status.[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Running: {' '.join(docker_args)}[/blue]")
    try:
        subprocess.run(docker_args, cwd=str(DOCKER_DIR), check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Docker command failed: {e}", exc_info=True)
        console.print(f"[red]Docker command failed: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(
            f"Unexpected error running Docker command: {e}", exc_info=True)
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("api-start")
def start_api(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(5000, help="Port to listen on"),
    debug: bool = typer.Option(False, help="Enable debug mode"),
    prod: bool = typer.Option(False, "--prod", help="Use production server")
):
    """
    Start the REST API server.
    - Checks if already running.
    - If running in Docker deployment, warns user.
    - Starts via gunicorn in prod or flask run in dev.
    - Waits briefly for startup, then prints URL or error.
    """
    log_utils.setup_logging()

    from lifelog.app import app as flask_app  # renamed to avoid name conflict

    # Ensure initialization
    try:
        initialize_application()
    except Exception as e:
        logger.error(
            f"Initialization failed before starting API: {e}", exc_info=True)
        console.print(f"[red]Initialization error: {e}[/red]")
        raise typer.Exit(1)

    # Check if already running
    try:
        if is_server_up(host, port):
            console.print(
                f"[yellow]Server already running at http://{host}:{port}[/yellow]")
            return
    except Exception as e:
        logger.warning(f"Error checking server status: {e}", exc_info=True)

    # Docker hints
    try:
        if is_running_in_docker():
            console.print("[cyan]Detected Docker environment.[/cyan]")
        elif docker_deployment_exists():
            console.print("[yellow]Docker deployment files detected.[/yellow]")
            console.print(
                "It's recommended to start your server using Docker:")
            console.print(
                f"  Use llog docker or:\n  cd {cf.BASE_DIR / 'docker'} && docker compose up -d --build")
            if not typer.confirm("Continue starting server directly anyway?", default=False):
                return
    except Exception as e:
        logger.warning(
            f"Error detecting Docker environment: {e}", exc_info=True)

    # Build command
    try:
        if prod or os.getenv("FLASK_ENV") == "production":
            cmd = [
                "gunicorn",
                "-b", f"{host}:{port}",
                "-w", "4",
                "--timeout", "120",
                "lifelog.app:app"
            ]
        else:
            cmd = [sys.executable, "-m", "flask", "run",
                   "--host", host, "--port", str(port)]
            if debug:
                os.environ["FLASK_ENV"] = "development"
    except Exception as e:
        logger.error(f"Error building start command: {e}", exc_info=True)
        console.print(f"[red]Error building start command: {e}[/red]")
        raise typer.Exit(1)

    # Start in background
    try:
        proc = subprocess.Popen(cmd)
    except FileNotFoundError as e:
        logger.error(f"Start command not found: {e}", exc_info=True)
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"Failed to start server process: {e}", exc_info=True)
        console.print(f"[red]Error starting server: {e}[/red]")
        raise typer.Exit(1)

    # Wait for server to start
    started = False
    for _ in range(10):  # up to ~5 seconds
        if is_server_up(host, port):
            started = True
            break
        time.sleep(0.5)
    if not started:
        logger.error("Server failed to start within timeout")
        console.print("[red]Server failed to start within timeout.[/red]")
        return

    console.print(f"[green]🚀 Server started at http://{host}:{port}[/green]")
    console.print(
        "To stop the server, use your OS process manager or Docker (if running in Docker).")


@app.command("sync")
def sync_command():
    """
    Sync pending changes with the server (client mode only).
    """
    log_utils.setup_logging()
    try:
        from lifelog.utils.db.db_helper import process_sync_queue
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
    log_utils.setup_logging()
    try:
        db_path = cf.BASE_DIR / "lifelog.db"
        if not db_path.exists():
            console.print("[red]Database file not found![/red]")
            raise typer.Exit(1)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output or f"lifelog_backup_{timestamp}.db"
        import shutil
        shutil.copy2(db_path, output_path)
        console.print(f"[green]✓ Backup created at: {output_path}[/green]")
    except Exception as e:
        logger.error(f"Backup command failed: {e}", exc_info=True)
        console.print(f"[red]Backup failed: {e}[/red]")
        raise typer.Exit(1)


@app.command("api-pair-new")
def api_pair_new():
    """
    Pair this device with the server.
    - On server mode: generates and shows pairing code.
    - On client mode: prompts for code and posts to server.
    """
    log_utils.setup_logging()
    try:
        config = cf.load_config()
    except Exception as e:
        logger.error(
            f"Failed to load config in api-pair-new: {e}", exc_info=True)
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)

    mode = config.get("deployment", {}).get("mode")
    try:
        if mode == "server":
            device_name = typer.prompt("Name this device (e.g. 'Office PC')")
            try:
                r = requests.post("http://localhost:5000/api/pair/start",
                                  json={"device_name": device_name}, timeout=5)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.error(
                    f"Error contacting API for pairing: {e}", exc_info=True)
                console.print(f"[red]Error contacting API: {e}[/red]")
                return

            code = data.get("pairing_code")
            expires_in = data.get("expires_in")
            if not code or not expires_in:
                console.print(
                    "[red]No pairing code returned. Check server logs.[/red]")
                console.print(f"[dim]Raw server response: {data}[/dim]")
                return
            console.print(f"[green]Pairing code:[/green] {code}")
            console.print(f"[yellow]Expires in {expires_in} seconds[/yellow]")
            console.print(
                "Enter this code on the client device to complete pairing.")

        elif mode == "client":
            server_url = config.get("deployment", {}).get("server_url")
            if not server_url:
                console.print("[red]Server URL not configured.[/red]")
                return
            device_name = typer.prompt("Name this device (e.g. 'Laptop')")
            code = typer.prompt("Enter the pairing code shown on the server")
            try:
                r = requests.post(f"{server_url}/api/pair/complete",
                                  json={"pairing_code": code, "device_name": device_name}, timeout=5)
                r.raise_for_status()
                resp = r.json()
            except Exception as e:
                logger.error(
                    f"Error during pairing request: {e}", exc_info=True)
                console.print(f"[red]Error during pairing: {e}[/red]")
                console.print(
                    f"[dim]Server response: {getattr(e, 'response', '')}[/dim]")
                return

            if "device_token" in resp:
                token = resp["device_token"]
                config["api"] = {"device_token": token}
                saved = cf.save_config(config)
                if not saved:
                    console.print(
                        "[red]⚠️ Failed to save pairing token to config.[/red]")
                    logger.error("Failed to save pairing token to config")
                else:
                    console.print(
                        "[green]✓ Device paired successfully![/green]")
            else:
                console.print(f"[red]Pairing failed: {resp}[/red]")
                logger.warning(
                    f"Pairing response did not include device_token: {resp}")
        else:
            console.print(
                "[yellow]This command is only for server or client mode devices.[/yellow]")
    except Exception as e:
        logger.error(f"Unexpected error in api-pair-new: {e}", exc_info=True)
        console.print(f"[red]Error in pairing command: {e}[/red]")
        raise typer.Exit(1)


def initialize_application():
    """
    Full application initialization sequence.
    - Ensures base directory exists.
    - Initializes DB schema if needed.
    - Loads config and ensures hooks directory.
    - For non-UI commands: checks first-run and prompts if needed.
    Returns True if initialization passes; exits on critical failure.
    """
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
        hooks_util.ensure_hooks_dir()

        # 5. Run first-time wizard if needed
        if not config.get("meta", {}).get("first_run_complete", False):
            console.print(Panel(
                "[bold yellow]Initial Setup Required[/bold yellow]\n"
                "Please run: [bold cyan]llog setup[/bold cyan] to configure Lifelog",
                style="yellow"
            ))
            sys.exit(1)

        # 6. Check for first command of the day
        if check_first_command_of_day():
            greet_user()
            save_first_command_flag(str(datetime.now().date()))

        return True
    except Exception as e:
        console.print(f"[red]⚠️ Critical initialization error: {e}[/red]")
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
        if not database_manager.is_initialized():
            database_manager.initialize_schema()

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
    try:
        hour = datetime.now().hour
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
    try:
        today = datetime.now().date()
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
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to save first command flag: {e}", exc_info=True)
        console.print(f"[red]⚠️ Failed to save command flag: {e}[/red]")
    except Exception as e:
        logger.error(
            f"Unexpected error saving first command flag: {e}", exc_info=True)
        console.print(f"[red]Error saving command flag: {e}[/red]")


def is_server_up(host: str, port: int) -> bool:
    """
    Check if API server is up by GET /api/status.
    Returns True if status_code==200, False otherwise.
    """
    try:
        resp = requests.get(f"http://{host}:{port}/api/status", timeout=1)
        return resp.status_code == 200
    except Exception as e:
        logger.info(f"is_server_up check failed: {e}", exc_info=True)
        return False


def is_running_in_docker() -> bool:
    """
    Return True if running inside a Docker container.
    """
    try:
        if Path("/.dockerenv").exists():
            return True
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            content = cgroup.read_text(errors="ignore")
            if "docker" in content:
                return True
    except Exception as e:
        logger.warning(
            f"Error detecting Docker environment: {e}", exc_info=True)
    return False


def docker_deployment_exists() -> bool:
    """
    Return True if Docker deployment files are present under BASE_DIR/docker.
    """
    try:
        docker_dir = cf.BASE_DIR / "docker"
        if (docker_dir / "Dockerfile").exists() and (docker_dir / "docker-compose.yml").exists():
            return True
    except Exception as e:
        logger.warning(
            f"Error checking docker deployment existence: {e}", exc_info=True)
    return False


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """
    Main callback invoked before any command.
    - Ensures app initialization and logging setup.
    - Performs auto-sync if needed.
    """
    # Set up logging early
    log_utils.setup_logging()

    try:
        ensure_app_initialized()
    except typer.Exit:
        # Let Typer handle exit
        raise
    except Exception as e:
        logger.error(
            f"Error in main_callback initialization: {e}", exc_info=True)
        console.print(f"[red]Initialization error: {e}[/red]")
        raise typer.Exit(1)

    # Auto-sync for commands that need fresh data
    if should_sync():
        try:
            auto_sync()
        except Exception as e:
            logger.warning(
                f"Auto-sync failed in main_callback: {e}", exc_info=True)
            console.print(f"[yellow]⚠️ Auto-sync failed: {e}[/yellow]")


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
