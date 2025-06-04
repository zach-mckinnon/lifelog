import os
from pathlib import Path
import requests
from rich.console import Console
from rich.panel import Panel
import typer
import secrets
import string

from lifelog.utils.encrypt import encrypt_data, setup_encryption


console = Console()
LOGO = r"""
██╗     ██╗███████╗███████╗██╗      ██████╗  ██████╗ 
██║     ██║██╔════╝██╔════╝██║     ██╔═══██╗██╔════╝ 
██║     ██║█████╗  █████╗  ██║     ██║   ██║██║  ████╗
██║     ██║██╔══╝  ██╔══╝  ██║     ██║   ██║██║   ██╔╝
███████╗██║██║     ███████╗███████╗╚██████╔╝╚██████╔╝
╚══════╝╚═╝╚═╝     ╚══════╝╚══════╝ ╚═════╝  ╚═════╝ 
"""


def show_welcome():
    """Display welcome banner and introduction"""
    console.clear()
    console.print(Panel(LOGO, style="bold cyan", expand=False))
    console.print(Panel(
        "[bold]Welcome to Lifelog![/bold]\n"
        "Your personal life tracking companion\n\n"
        "Let's get started with a quick setup",
        style="green"
    ))
    typer.confirm("Press Enter to continue", default=True)


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


def generate_docker_files(base_path=None):
    # Use the current directory as base if not given
    base_path = Path(base_path or os.getcwd())
    docker_dir = base_path / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)

    # Now check for existing files
    if (docker_dir / "Dockerfile").exists() or (docker_dir / "docker-compose.yml").exists():
        if not typer.confirm("Docker files already exist. Overwrite?", default=False):
            print("Skipped Docker file generation.")
            return

    dockerfile_content = """\
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install lifelog flask gunicorn

# Copy configuration
COPY ./.lifelog /root/.lifelog

# Expose API port
EXPOSE 5000

# Start the API server
CMD ["llog", "api-start", "--host", "0.0.0.0", "--port", "5000"]
"""

    compose_content = """\
version: '3.8'

services:
  lifelog-api:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ~/.lifelog:/root/.lifelog
    environment:
      - FLASK_ENV=production
    restart: unless-stopped
"""

    # Write Dockerfile
    with open(docker_dir / "Dockerfile", "w") as f:
        f.write(dockerfile_content)
    # Write docker-compose.yml
    with open(docker_dir / "docker-compose.yml", "w") as f:
        f.write(compose_content)

    print("\n[green]Docker deployment files created.[/green]")
    print(f"Dockerfile: {docker_dir / 'Dockerfile'}")
    print(f"docker-compose.yml: {docker_dir / 'docker-compose.yml'}")
    print("\nTo build and run:\n  cd docker && docker-compose up -d --build\n")


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


def run_wizard(config):
    """Main wizard sequence"""
    show_welcome()
    setup_location(config)
    setup_ai(config)
    setup_api(config)
    show_tutorial()

    # Add first-run marker
    config["meta"]["first_run_complete"] = True
    return config
