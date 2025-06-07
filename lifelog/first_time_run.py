import curses
import os
from pathlib import Path
import platform
import shutil
import sys
from typing import Optional
import requests
from rich.console import Console
from rich.panel import Panel
from tomlkit import table
import typer
import secrets
import string

from lifelog.config import schedule_manager as sm
from lifelog.utils.encrypt import encrypt_data, setup_encryption
import lifelog.config.config_manager as cf

console = Console()


LOGO_LARGE = [
    "██╗     ██╗███████╗███████╗██╗      ██████╗  ██████╗ ",
    "██║     ██║██╔════╝██╔════╝██║     ██╔═══██╗██╔════╝ ",
    "██║     ██║█████╗  █████╗  ██║     ██║   ██║██║  ███╗",
    "██║     ██║██╔══╝  ██╔══╝  ██║     ██║   ██║██║   ██║",
    "███████╗██║██║     ███████╗███████╗╚██████╔╝╚██████╔╝",
    "╚══════╝╚═╝╚═╝     ╚══════╝╚══════╝ ╚═════╝  ╚═════╝ "
]

# Medium logo for medium terminals
LOGO_MEDIUM = [
    "╦  ╦╔═╗╔═╗╦  ╔═╗╔═╗",
    "║  ║╠╣ ║╣ ║  ║ ║║ ╦",
    "╚═╝╩╚  ╚═╝╩═╝╚═╝╚═╝"
]

# Minimal text for small terminals
LOGO_SMALL = ["L I F E L O G"]


def run_wizard(config):
    """Main wizard sequence"""
    show_welcome()
    setup_location(config)
    setup_deployment(config)
    setup_ai(config)
    if config["deployment"].get("host_server", False):
        setup_api(config)
    show_tutorial()

    # Add first-run marker
    config["meta"]["first_run_complete"] = True
    return config


def show_welcome(stdscr=None):
    """Universal welcome screen that works for both CLI and TUI"""
    if stdscr:  # TUI mode (curses)
        h, w = stdscr.getmaxyx()
        min_widths = [50, 30, 10]

        # Select appropriate logo
        if w >= min_widths[0]:
            logo = LOGO_LARGE
        elif w >= min_widths[1]:
            logo = LOGO_MEDIUM
        else:
            logo = LOGO_SMALL

        logo_height = len(logo)
        start_y = max(1, h//2 - logo_height//2 - 1)

        # Display logo
        for i, line in enumerate(logo):
            y = start_y + i
            if y >= h - 1:
                break
            x = max(1, w//2 - len(line)//2)
            # Truncate if necessary
            if x + len(line) > w:
                line = line[:w - x - 1]
            try:
                stdscr.addstr(y, x, line, curses.A_BOLD)
            except curses.error:
                pass

        # Display message
        message = "Press any key to begin"
        msg_y = min(h-2, start_y + logo_height + 2)
        msg_x = max(1, w//2 - len(message)//2)
        try:
            stdscr.addstr(msg_y, msg_x, message)
        except curses.error:
            pass

        stdscr.refresh()
        stdscr.getch()

    else:  # CLI mode (Rich)
        from rich.console import Console
        console = Console()

        # Get terminal width
        width = console.width

        # Select appropriate logo
        if width >= 50:
            logo = "\n".join(LOGO_LARGE)
        elif width >= 30:
            logo = "\n".join(LOGO_MEDIUM)
        else:
            logo = " ".join(LOGO_SMALL)

        console.print(Panel(
            logo,
            style="bold cyan",
            expand=False,
            title="LIFELOG",
            title_align="center",
            subtitle="v1.0",
            subtitle_align="center"
        ))
        console.print(Panel(
            "[bold]Welcome to Lifelog![/bold]\n"
            "Your personal life tracking companion\n\n"
            "Let's get started with a quick setup",
            style="green"
        ))
        typer.confirm("Press Enter to continue", default=True)


def setup_scheduled_tasks(config: dict):
    """
    Prompt user for times (recur_auto and env_sync), then write absolute paths
    into config.toml under [cron.recur_auto] and [cron.env_sync], and install jobs.
    """
    # 1. Find the absolute path to the `llog` executable/script:
    llog_cmd = shutil.which("llog")
    if not llog_cmd:
        llog_cmd = os.path.abspath(sys.argv[0])

    # 2. Load or create the [cron] section of config.toml
    doc = cf.load_config()
    cron_section = doc.get("cron", table())

    # 3. If recur_auto isn’t defined yet, ask the user and write it:
    if "recur_auto" not in cron_section:
        console.print(
            "[bold blue]⏰ When do you want recurring tasks to run? (HH:MM)[/bold blue]")
        while True:
            user_time = typer.prompt("Recur‐auto time", default="04:00")
            try:
                h, m = user_time.split(":")
                hour = int(h)
                minute = int(m)
                if 0 <= hour < 24 and 0 <= minute < 60:
                    break
            except:
                pass
            console.print(
                "[red]Invalid time. Enter in 24h format, e.g. 04:00.[/red]")

        cron_expr_recur = f"{minute} {hour} * * *"
        cron_section["recur_auto"] = {
            "schedule": cron_expr_recur,
            "command": f"{llog_cmd} task auto_recur"
        }
        console.print(
            f"[green]✅ recur_auto scheduled at {hour:02d}:{minute:02d} daily[/green]")
    else:
        console.print(
            "[yellow]⚡ recur_auto already set—skipping creation[/yellow]")

    # 4. If env_sync isn’t defined yet, ask the user and write it:
    if "env_sync" not in cron_section:
        console.print(
            "[bold blue]⏰ When do you want env sync to run? (HH:MM every N hours)[/bold blue]")
        console.print(
            "[dim]Example: 02:00 to start at 2 AM, then every 4 hours[/dim]")
        while True:
            sync_time = typer.prompt("Env-sync start time", default="02:00")
            try:
                h, m = sync_time.split(":")
                shour = int(h)
                sminute = int(m)
                if 0 <= shour < 24 and 0 <= sminute < 60:
                    break
            except:
                pass
            console.print("[red]Invalid time. Enter HH:MM, e.g. 02:00.[/red]")

        # Let’s assume env_sync should run every 4 hours starting at `sync_time`.
        # Cron expression: “minute hour/4 * * *”
        cron_expr_env = f"{sminute} */4 * * *"
        cron_section["env_sync"] = {
            "schedule": cron_expr_env,
            "command": f"{llog_cmd} env sync-all"
        }
        console.print(
            f"[green]✅ env_sync scheduled at {shour:02d}:{sminute:02d}, every 4 hours[/green]")
    else:
        console.print(
            "[yellow]⚡ env_sync already set—skipping creation[/yellow]")

    # 5. Save the updated config.toml
    doc["cron"] = cron_section
    cf.save_config(doc)

    # 6. Finally, install into the OS scheduler (cron or Windows Task Scheduler)
    system = platform.system()
    if system == "Windows":
        console.print("[cyan]Setting up Windows Scheduled Tasks...[/cyan]")
    else:
        console.print("[cyan]Updating root crontab...[/cyan]")

    try:
        sm.apply_scheduled_jobs()
        console.print("[green]✅ Scheduled jobs applied.[/green]")
        return doc
    except Exception as e:
        console.print(f"[red]❌ Failed to apply scheduled jobs: {e}[/red]")


def setup_location(config):
    """Guide user through location setup"""
    console.print(Panel(
        "[bold]📍 Location Setup[/bold]\n"
        "We'll use this for weather and environmental data",
        style="blue"
    ))

    # Existing detection logic
    try:
        response = requests.get('https://ipinfo.io/json', timeout=3)
        data = response.json()
        if zip_code := data.get('postal'):
            loc = data.get("loc", "0,0").split(",")
            lat, lon = float(loc[0]), float(loc[1])

            console.print(f"[dim]• Detected ZIP code: {zip_code}[/dim]")
            if typer.confirm("Use detected location?", default=True):
                config["location"] = {
                    "zip": zip_code,
                    "latitude": lat,
                    "longitude": lon
                }
                return
    except (requests.RequestException, ValueError) as e:
        console.print(
            "[yellow]Unable to detect your location automatically.[/yellow]")
        console.print(
            "[dim]Reason: Could not connect or parse location info.[/dim]")
        console.print(f"[dim]Details: {str(e)}[/dim]")
        console.print(
            "[yellow]You'll need to enter your ZIP code manually.[/yellow]")

    # Manual entry
    zip_code = typer.prompt("Please enter your 5-digit ZIP code")
    while not (zip_code.isdigit() and len(zip_code) == 5):
        zip_code = typer.prompt(
            "Invalid format. Please enter 5-digit ZIP code")

    config["location"] = {"zip": zip_code}


def setup_ai(config):
    """Guide user through AI setup with encrypted credentials"""
    console.print(Panel(
        "[bold]🤖 AI Enhancement[/bold]\n"
        "Enable smart features like insights and suggestions",
        style="magenta"
    ))

    if typer.confirm("Would you like to enable AI features?", default=True):
        # Ensure encryption is set up
        setup_encryption(config)

        console.print("\n[bold]Available AI Providers:[/bold]")
        console.print("1. [cyan]OpenAI[/cyan] (ChatGPT)")
        console.print("2. [yellow]Google[/yellow] (Gemini)")
        console.print("3. [green]Anthropic[/green] (Claude)")

        choice = typer.prompt("Select provider (1-3)", type=int)
        api_key = typer.prompt("Enter your API key", hide_input=True)

        providers = {1: "openai", 2: "google", 3: "anthropic"}
        provider_name = providers.get(choice, "openai")

        # Encrypt the API key before storing
        encrypted_key = encrypt_data(config, api_key)

        config["ai"] = {
            "provider": provider_name,
            "api_key": encrypted_key,
            "enabled": True
        }

        console.print(
            f"\n[green]✓ AI credentials for {provider_name} encrypted and stored[/green]")


def setup_api(config):
    """Generate REST API credentials and Docker setup"""
    console.print(Panel(
        "[bold]🔑 REST API Access[/bold]\n"
        "Generate credentials for external integrations",
        style="yellow"
    ))

    if typer.confirm("Enable REST API access?", default=True):
        # Generate secure credentials
        key = ''.join(secrets.choice(string.ascii_letters + string.digits)
                      for _ in range(32))
        secret = ''.join(secrets.choice(string.ascii_letters +
                         string.digits + string.punctuation) for _ in range(64))

        # Ensure encryption is set up
        setup_encryption(config)

        # Store encrypted credentials
        config["api"] = {
            "enabled": True,
            "key": encrypt_data(config, key),
            "secret": encrypt_data(config, secret)
        }

        # Show the plaintext credentials to the user
        console.print(f"\n[bold]Your API Credentials:[/bold]")
        console.print(f"Key: [cyan]{key}[/cyan]")
        console.print(f"Secret: [red]{secret}[/red]")
        console.print(
            "\n[bold yellow]⚠️ Save these securely! They won't be shown again.[/bold yellow]")

        # Create Docker files
        if typer.confirm("\nCreate Docker deployment files?", default=True):
            # Use the actual config base directory for the docker folder
            from lifelog.config.config_manager import BASE_DIR
            generate_docker_files(BASE_DIR)
            console.print(
                f"[green]Docker deployment files created at {BASE_DIR / 'docker'}[/green]")
            console.print(
                f"To build and run:\n  cd {BASE_DIR / 'docker'} && docker-compose up -d --build\n")

        console.print("\n[bold]Usage:[/bold]")
        console.print("Start API: [cyan]llog api-start[/cyan]")
        console.print(
            "Docker: [cyan]cd ~/.lifelog/docker && docker-compose up -d[/cyan]")


def generate_docker_files(base_path: Optional[Path] = None) -> None:
    """
    Create ~/.lifelog/docker/{Dockerfile,docker-compose.yml}

    • Works on Python 3.9 (no PEP-604 unions, no 3.10-only syntax)
    • Build context is the parent ~/.lifelog directory so COPY .lifelog … works.
    • docker-compose mounts ~/.lifelog, preserving the SQLite DB & config.
    """
    # Resolve target directory
    base_path = (base_path or Path.home() / ".lifelog").expanduser().resolve()
    docker_dir = base_path / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)

    # Abort if files exist and user says “no”
    if any((docker_dir / f).exists() for f in ("Dockerfile", "docker-compose.yml")):
        if not typer.confirm("Docker files already exist here. Overwrite?", default=False):
            print("Skipped Docker file generation.")
            return

    # ── Dockerfile ──────────────────────────────────────────────────────────
    dockerfile_content = (
        "FROM python:3.9-slim\n\n"
        "# Install the lifelog wheel and runtime deps\n"
        "RUN pip install --no-cache-dir lifelog flask gunicorn\n\n"
        "WORKDIR /app\n"
        "EXPOSE 5000\n\n"
        'CMD ["llog", "api-start", "--host", "0.0.0.0", "--port", "5000"]\n'
    )

    # ── docker-compose.yml ──────────────────────────────────────────────────
    compose_content = (
        "services:\n"
        "  lifelog-api:\n"
        "    build:\n"
        "      context: \"..\"\n"
        "      dockerfile: \"docker/Dockerfile\"\n"
        "    image: docker-lifelog-api\n"
        "    ports:\n"
        "      - \"5000:5000\"\n"
        "    volumes:\n"
        "      - ~/.lifelog:/root/.lifelog \n"
        "    restart: unless-stopped\n"
    )

    # Write files (UTF-8)
    (docker_dir / "Dockerfile").write_text(dockerfile_content, encoding="utf-8")
    (docker_dir / "docker-compose.yml").write_text(compose_content, encoding="utf-8")

    print("\n[green]Docker deployment files created.[/green]")
    print(f"Dockerfile:          {docker_dir / 'Dockerfile'}")
    print(f"docker-compose.yml:  {docker_dir / 'docker-compose.yml'}")
    print("\nRun:\n  cd ~/.lifelog/docker && docker compose up -d --build\n")


def setup_deployment(config):
    """Guide user through deployment mode selection"""
    console.print(Panel(
        "[bold]🏢 Deployment Setup[/bold]\n"
        "Choose how you want to run Lifelog",
        style="blue"
    ))

    console.print(
        "1. [green]Local-only[/green]: All data stays on this device")
    console.print(
        "2. [cyan]Server/Host[/cyan]: This device will host the API server")
    console.print("3. [yellow]Client[/yellow]: Connect to an existing server")

    choice = typer.prompt("Select deployment mode (1-3)", type=int)

    if choice == 1:
        config["deployment"] = {
            "mode": "local",
            "server_url": None,
            "host_server": False
        }
        console.print("[green]✓ Local-only mode selected[/green]")

    elif choice == 2:
        config["deployment"] = {
            "mode": "server",
            "server_url": "http://localhost:5000",
            "host_server": True
        }
        console.print("[cyan]✓ Server/Host mode selected[/cyan]")

    elif choice == 3:
        server_url = typer.prompt(
            "Enter server URL (e.g., http://192.168.1.100:5000)")
        config["deployment"] = {
            "mode": "client",
            "server_url": server_url,
            "host_server": False
        }
        console.print(
            f"[yellow]✓ Client mode selected. Server: {server_url}[/yellow]")

    else:
        console.print(
            "[red]Invalid choice. Defaulting to Local-only mode.[/red]")
        config["deployment"] = {
            "mode": "local",
            "server_url": None,
            "host_server": False
        }

    # If hosting the server, proceed with API setup
    if config["deployment"]["host_server"]:
        setup_api(config)


def show_tutorial():
    """Show quick start tutorial"""
    console.print(Panel(
        "[bold]🚀 Quick Start Guide[/bold]",
        style="green"
    ))

    console.print("\n[bold]Key Features:[/bold]")
    console.print("• [cyan]llog track[/cyan] - Log health metrics & habits")
    console.print("• [cyan]llog time[/cyan] - Track time spent on activities")
    console.print("• [cyan]llog task[/cyan] - Manage your to-do list")
    console.print(
        "• [cyan]llog ui[/cyan] - Launch the full-screen interface\n")

    console.print("[bold]Next Steps:[/bold]")
    console.print(
        "1. Add your first tracker: [cyan]llog track add 'Mood'[/cyan]")
    console.print(
        "2. Start time tracking: [cyan]llog time start 'Work'[/cyan]")
    console.print("3. Add a task: [cyan]llog task add 'Write report'[/cyan]")

    typer.confirm("\nPress Enter to finish setup", default=True)
