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

from lifelog.utils.db.db_helper import auto_sync, should_sync
from lifelog.utils import hooks as hooks_util
from lifelog.utils import log_utils
from lifelog.commands import start_day

# Initialize the config manager and ensure the files exist
app = typer.Typer(
    help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")

console = Console()

# -------------------------------------------------------------------
# Core Initialization System
# -------------------------------------------------------------------
DOCKER_DIR = Path.home() / ".lifelog" / "docker"

# Ensure the app is initialized
sync_app = typer.Typer(help="Pull external data sources into lifelog.")
sync_app.command()(environmental_sync.weather)
sync_app.command()(environmental_sync.air)
sync_app.command()(environmental_sync.moon)
sync_app.command()(environmental_sync.satellite)
app.add_typer(start_day.app, name="start-day",
              help="Guided, motivational start-of-day routine")

app.add_typer(sync_app, name="sync", help="Fetch external environmental data")

# Register all modules
app.add_typer(track_module.app, name="track",
              help="Track recurring self-measurements and goals."
              )
app.add_typer(time_module.app, name="time",
              help="Track time in categories like resting, working, socializing.")
app.add_typer(task_module.app, name="task",
              help="Create, track, and complete actionable tasks.")
app.add_typer(report.app, name="report",
              help="View detailed reports and insights.")
app.add_typer(sync_app, name="sync", help="Data synchronization commands")
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
        hooks_util.ensure_hooks_dir()
        # 4. Skip wizard for UI command - handled separately
        if "ui" in sys.argv:
            return True

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
    """Run setup wizard on first run, never block setup command itself."""
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


@app.command("ui")
def ui(
    no_help: Annotated[bool, typer.Option(
        "--no-help", is_flag=True, help="Disable the help bar.")] = False
):
    """
    Launch the full-screen Lifelog TUI
    """
    ensure_app_initialized()
    # By default, status bar is ON, unless user gives --no-help
    show_status = not no_help

    if should_sync():
        try:
            auto_sync()
        except Exception as e:
            # We print a non‐fatal warning in the TUI mode:
            console.addstr(0, 0, f"⚠️ Auto‐sync failed: {e}")
            console.refresh()
            curses.napms(1500)  # pause 1.5s so user can see it
            curses.endwin()

    curses.wrapper(ui_main, show_status)


@app.command("setup")
def setup_command():
    """Run initial setup wizard"""
    try:
        # Ensure base directory exists
        cf.BASE_DIR.mkdir(parents=True, exist_ok=True)

        # Load or create config
        config = cf.load_config()

        # Run wizard if not complete
        if not config.get("meta", {}).get("first_run_complete", False):
            config = run_wizard(config)
            cf.save_config(config)
            console.print("[green]✓ Setup completed successfully![/green]")
        else:
            if typer.confirm("Setup already completed. Run again?", default=False):
                config = run_wizard(config)
                cf.save_config(config)
                console.print("[green]✓ Setup re-configured![/green]")
            else:
                console.print("[yellow]Setup aborted[/yellow]")
    except Exception as e:
        console.print(f"[red]⚠️ Setup failed: {e}[/red]")
        sys.exit(1)


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
            "[italic green]Tip:[/] Use [bold]--help[/bold] after any command to see available options.",
            title="💡 Usage Tip",
            title_align="left"
        )
    )


@app.command("config-edit")
def config_edit():
    """
    Interactive config editor. Change aliases, categories, category importance, etc.
    """

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
    config = cf.load_config()

    # Skip banner in UI mode
    if "curses" in sys.modules:
        return

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


@app.command("get-server-url")
def get_server_url():
    """
    Print the correct API server URL for pairing client devices.
    """
    import socket
    import yaml

    config = cf.load_config()
    docker_dir = cf.BASE_DIR / "docker"
    compose_file = docker_dir / "docker-compose.yml"

    # 1. Check for Docker Compose and a running container
    docker_used = False
    if compose_file.exists():
        try:
            import subprocess
            # Is Docker running and container up?
            result = subprocess.run(
                ["docker", "compose", "-f",
                    str(compose_file), "ps", "-q", "lifelog-api"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.stdout.strip():
                docker_used = True
        except Exception as e:
            pass  # fallback

    # 2. If Docker is being used, parse docker-compose for port
    if docker_used:
        try:
            with open(compose_file, "r") as f:
                compose = yaml.safe_load(f)
            # Get the mapped port (default is 5000:5000)
            ports = compose["services"]["lifelog-api"]["ports"]
            port_mapping = ports[0] if ports else "5000:5000"
            host_port = port_mapping.split(":")[0]
        except Exception:
            host_port = "5000"

        # Try to determine host IP address on LAN
        try:
            # Get LAN IP, not localhost
            hostname = socket.gethostname()
            host_ip = socket.gethostbyname(hostname)
            # Avoid loopback
            if host_ip.startswith("127."):
                # Use another trick (works on Linux/Mac)
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    host_ip = s.getsockname()[0]
                except Exception:
                    host_ip = "127.0.0.1"
                finally:
                    s.close()
        except Exception:
            host_ip = "127.0.0.1"

        url = f"http://{host_ip}:{host_port}"
        console.print(
            f"[bold green]API server running in Docker.[/bold green]")
        console.print(f"[cyan]URL for client devices: {url}[/cyan]")
        return

    # 3. Fallback: Use config value or localhost
    server_url = (
        config.get("deployment", {}).get(
            "server_url") or "http://localhost:5000"
    )
    console.print(f"[bold green]API server running locally.[/bold green]")
    console.print(f"[cyan]URL for client devices: {server_url}[/cyan]")


@app.command("docker")
def docker_cmd(
    action: Annotated[str, typer.Argument(
        help="Action: up, down, restart, logs")] = "up"
):
    """
    Manage Lifelog Docker deployment. Actions: up, down, restart, logs.
    """

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
            "[red]Unknown action. Use up, down, restart, logs.[/red]")
        raise typer.Exit(1)

    # Run the docker command
    console.print(f"[blue]Running: {' '.join(docker_args)}[/blue]")
    subprocess.run(docker_args, cwd=str(DOCKER_DIR))


def is_server_up(host, port):
    try:
        resp = requests.get(f"http://{host}:{port}/api/status", timeout=1)
        return resp.status_code == 200
    except Exception:
        return False


def is_running_in_docker():
    # True if inside Docker container
    return (
        Path("/.dockerenv").exists() or
        (Path("/proc/1/cgroup").exists()
         and "docker" in Path("/proc/1/cgroup").read_text())
    )


def docker_deployment_exists():
    # True if docker deployment files are present
    from lifelog.config.config_manager import BASE_DIR
    docker_dir = BASE_DIR / "docker"
    return (docker_dir / "Dockerfile").exists() and (docker_dir / "docker-compose.yml").exists()


@app.command("api-start")
def start_api(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(5000, help="Port to listen on"),
    debug: bool = typer.Option(False, help="Enable debug mode"),
    prod: bool = typer.Option(False, "--prod", help="Use production server")
):
    import os
    from lifelog.app import app

    initialize_application()

    # ---- Check if already running ----
    if is_server_up(host, port):
        console.print(
            f"[yellow]Server already running at http://{host}:{port}[/yellow]")
        return
    if is_running_in_docker():
        console.print("[cyan]Detected Docker environment.[/cyan]")
        # You might want to behave differently or just print info
    elif docker_deployment_exists():
        console.print("[yellow]Docker deployment files detected.[/yellow]")
        console.print("It's recommended to start your server using Docker:")
        console.print(
            f"  Use llog docker or directly start the container with:")
        console.print(
            f"  cd {cf.BASE_DIR / 'docker'} && docker compose up -d --build")
        # Optionally: exit or prompt the user to continue
        if not typer.confirm("Continue starting server directly anyway?", default=False):
            return
    # ---- Build command ----
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

    # ---- Start in background ----
    try:
        subprocess.Popen(cmd)

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # ---- Wait for the server to start ----
    for _ in range(10):  # Try for up to ~5 seconds
        if is_server_up(host, port):
            break
        time.sleep(0.5)
    else:
        console.print("[red]Server failed to start.[/red]")
        return

    # ---- Show server info ----
    console.print(f"[green]🚀 Server started at http://{host}:{port}[/green]")
    console.print(
        "To stop the server, use your OS process manager or Docker (if running in Docker).")


@app.command("sync")
def sync_command():
    """Sync pending changes with the server (client mode only)"""
    from lifelog.utils.db import process_sync_queue
    process_sync_queue()
    console.print("[green]Sync completed![/green]")


@app.command("backup")
def backup_command(
    output: Annotated[str, typer.Argument(help="Output file path")] = None
):
    """Create a backup of the lifelog database"""
    from datetime import datetime
    import shutil

    db_path = cf.BASE_DIR / "lifelog.db"
    if not db_path.exists():
        console.print("[red]Database file not found![/red]")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output or f"lifelog_backup_{timestamp}.db"

    try:
        shutil.copy2(db_path, output)
        console.print(f"[green]✓ Backup created at: {output}[/green]")
    except Exception as e:
        console.print(f"[red]Backup failed: {e}[/red]")


@app.command("api-pair-new")
def api_pair_new():
    """Pair this device with the server."""
    config = cf.load_config()
    mode = config.get("deployment", {}).get("mode")
    if mode == "server":
        # Host: generate and show a pairing code
        import requests
        device_name = typer.prompt("Name this device (e.g. 'Office PC')")
        r = requests.post("http://localhost:5000/api/pair/start",
                          json={"device_name": device_name})
        code = r.json().get("pairing_code")
        print(
            f"Pairing code: {code}\nExpires in {r.json().get('expires_in')} seconds")
        print("Enter this code on the client device to complete pairing.")
    elif mode == "client":
        # Client: complete pairing using code and server URL
        server_url = config["deployment"]["server_url"]
        device_name = typer.prompt("Name this device (e.g. 'Laptop')")
        code = typer.prompt("Enter the pairing code shown on the server")
        r = requests.post(f"{server_url}/api/pair/complete",
                          json={"pairing_code": code, "device_name": device_name})
        if "device_token" in r.json():
            token = r.json()["device_token"]
            config["api"] = {"device_token": token}
            cf.save_config(config)
            print("[green]✓ Device paired successfully![/green]")
        else:
            print("[red]Pairing failed: " + str(r.json()) + "[/red]")
    else:
        print("This command is only for server/host or client devices.")


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    ensure_app_initialized()
    log_utils.setup_logging()
    if should_sync():
        try:
            auto_sync()
        except Exception as e:
            console.print(f"[yellow]⚠️ Auto‐sync failed: {e}[/yellow]")
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
