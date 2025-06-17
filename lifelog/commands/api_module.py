# lifelog/commands/api_module.py

import os
from pathlib import Path
import sys
import subprocess
from typing import Annotated
import requests
import logging

import typer
from rich.console import Console

import lifelog.config.config_manager as cf
from lifelog.utils import log_utils

from lifelog.utils.db import should_sync, auto_sync

app = typer.Typer(help="🖥️  API server & pairing commands")
console = Console()
logger = logging.getLogger(__name__)


@app.command("start")
def start_api(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(5000, help="Port to listen on"),
    debug: bool = typer.Option(False, help="Enable debug mode"),
    prod: bool = typer.Option(False, "--prod", help="Use production server")
):
    """
    Start the REST API server.
    - In server mode → Gunicorn
    - Otherwise → flask run (with FLASK_APP set)
    """
    from lifelog.llog import initialize_application
    log_utils.setup_logging()

    # 1️⃣ Initialize (DB, config, hooks, scheduled jobs,…)
    initialize_application()

    # 2️⃣ Don’t start if already up
    if is_server_up(host, port):
        console.print(
            f"[yellow]Already running at http://{host}:{port}[/yellow]")
        raise typer.Exit()

    # 3️⃣ Auto-sync any pending data (optional)
    if should_sync():
        try:
            auto_sync()
        except Exception as e:
            logger.warning(f"Auto-sync failed: {e}", exc_info=True)

    # 4️⃣ Decide Gunicorn vs Flask-run
    config = cf.load_config()
    mode = config.get("deployment", {}).get("mode", "local")
    use_gunicorn = prod or (mode == "server")

    if use_gunicorn:
        console.print("[cyan]Starting production server (Gunicorn)…[/cyan]")
        cmd = [
            "gunicorn", "-b", f"{host}:{port}",
            "-w", "4", "--timeout", "120",
            "lifelog.app:app"
        ]
        subprocess.Popen(cmd)
    else:
        console.print("[cyan]Starting Flask development server…[/cyan]")
        env = os.environ.copy()
        env["FLASK_APP"] = "lifelog.app:app"
        if debug:
            env["FLASK_ENV"] = "development"
        subprocess.Popen([sys.executable, "-m", "flask", "run",
                          "--host", host, "--port", str(port)], env=env)

    console.print(f"[green]🚀 Server launch command issued.[/green]")


@app.command("pair-new")
def api_pair_new():
    """
    Pair this device with a running Lifelog server.
    - Server mode → issues a code to display
    - Client mode → prompts for code and saves token
    """
    log_utils.setup_logging()
    config = cf.load_config()
    mode = config.get("deployment", {}).get("mode")

    if mode == "server":
        device_name = typer.prompt("Name this server device")
        r = requests.post("http://localhost:5000/api/pair/start",
                          json={"device_name": device_name}, timeout=5)
        r.raise_for_status()
        data = r.json()
        console.print(f"[green]Pairing code:[/green] {data['pairing_code']}")
        console.print(f"[yellow]Expires in {data['expires_in']}s[/yellow]")
        console.print(
            "Give this code to your client device to complete pairing.")

    elif mode == "client":
        server_url = config.get("deployment", {}).get("server_url")
        device_name = typer.prompt("Name this client device")
        code = typer.prompt("Enter the pairing code")
        r = requests.post(f"{server_url}/api/pair/complete",
                          json={"pairing_code": code, "device_name": device_name}, timeout=5)
        r.raise_for_status()
        token = r.json().get("device_token")
        if token:
            config["api"] = {"device_token": token}
            cf.save_config(config)
            console.print("[green]✓ Device paired successfully![/green]")
        else:
            console.print("[red]Pairing failed—no token received.[/red]")

    else:
        console.print("[red]Unknown mode—cannot pair[/red]")


@app.command("get-server-url")
def get_server_url():
    """
    Show the correct URL to use for pairing client devices.
    """
    log_utils.setup_logging()
    config = cf.load_config()
    server_url = config.get("deployment", {}).get(
        "server_url") or "http://localhost:5000"
    console.print(f"[cyan]Server URL:[/cyan] {server_url}")


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
    DOCKER_DIR = Path.home() / ".lifelog" / "docker"
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
