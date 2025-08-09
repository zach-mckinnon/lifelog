# lifelog/commands/start_day.py

import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

import typer
from rich.console import Console
from rich.panel import Panel

from lifelog.utils.db import (
    task_repository,
    track_repository,
    environment_repository,
)
from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.commands.environmental_sync import fetch_today_forecast
from lifelog.utils.shared_utils import (
    now_local, format_datetime_for_user,
    utc_iso_to_local, now_utc,
)
from lifelog.utils.db.gamify_repository import modify_pomodoro_lengths
from lifelog.utils.hooks import run_hooks

console = Console()
app = typer.Typer(help="Guided, gamified start-of-day focus assistant (CLI).")

logger = logging.getLogger(__name__)


def prompt_continue(label: str = "Press Enter to continue...") -> None:
    try:
        typer.prompt(label, default="")
    except (KeyboardInterrupt, EOFError):
        console.print("[red]Interrupted—exiting start-day.[/red]")
        raise typer.Exit()


def prompt_for_int(prompt: str, default: int) -> int:
    val = typer.prompt(prompt, default=str(default))
    try:
        return int(val)
    except ValueError:
        console.print(
            f"[yellow]Invalid number, using default {default}[/yellow]")
        return default


def pomodoro_timer(minutes: int):
    import time
    for remaining in range(minutes, 0, -1):
        console.print(
            f"[bold green]⏳ {remaining} min left...[/bold green]", end="\r")
        time.sleep(60)
    console.print("[bold yellow]\nPomodoro session complete![/bold yellow]")


def show_today_weather_cli():
    try:
        env = environment_repository.get_latest_environment_data("weather")
    except Exception:
        logger.exception("Failed loading environment data")
        env = None

    if not env:
        console.print(
            "[yellow]No weather data. Run 'llog sync' first.[/yellow]")
        return

    lat, lon = env.get("latitude"), env.get("longitude")
    if lat is None or lon is None:
        console.print("[yellow]Incomplete location data.[/yellow]")
        return

    try:
        forecast = fetch_today_forecast(lat, lon)
    except Exception as e:
        logger.exception("Weather fetch error")
        console.print(f"[red]Failed fetching weather: {e}[/red]")
        return

    lines = []
    today_hdr = format_datetime_for_user(now_local()).split(" ")[0]
    lines.append(f"Forecast for {today_hdr} (4h intervals):")
    for ent in forecast:
        dt = utc_iso_to_local(ent["time"])
        lines.append(
            f"{format_datetime_for_user(dt)} — "
            f"{ent['temperature']}°C, Precip {ent['precip_prob']}%, {ent['description']}"
        )
    console.print(
        Panel("\n".join(lines), title="🌤️ Today's Forecast", style="cyan"))


def select_tasks_cli():
    tasks = task_repository.get_all_tasks()
    if not tasks:
        console.print(
            "[yellow]No tasks found. Add some with `llog task add`.[/yellow]")
        return []

    console.print("[bold]Select tasks for today (e.g. 1,3):[/bold]")
    for i, t in enumerate(tasks, 1):
        due = "-"
        if t.due:
            try:
                due = format_datetime_for_user(utc_iso_to_local(t.due))
            except Exception:
                due = str(t.due)
        console.print(f"{i}. [cyan]{t.title}[/cyan] (due: {due})")

    choice = typer.prompt("Enter comma-separated numbers", default="")
    if not choice.strip():
        return []

    selected = []
    for part in choice.split(","):
        if not part.strip().isdigit():
            console.print("[red]Invalid input—please use numbers only.[/red]")
            return []
        idx = int(part.strip()) - 1
        if idx < 0 or idx >= len(tasks):
            console.print(f"[red]Index {idx+1} is out of range.[/red]")
            return []
        selected.append(tasks[idx])
    return selected


def ask_time_for_tasks_cli(tasks):
    plan, total = [], 0
    for t in tasks:
        mins = prompt_for_int(f"Minutes for '{t.title}'?", 25)
        plan.append({"task": t, "minutes": mins})
        total += mins
    return plan, total


def log_trackers_cli():
    trackers = track_repository.get_all_trackers()
    for tr in trackers:
        if typer.confirm(f"Log tracker '{tr.title}' now?", default=False):
            val = typer.prompt(f"Value for {tr.title}", default="")
            if val:
                entry = track_repository.add_tracker_entry(
                    tracker_id=tr.id,
                    timestamp=now_utc(),
                    value=val,
                    notes=None  # Start day command doesn't support notes
                )
                run_hooks("tracker", "logged", entry)
                console.print(f"[green]Logged {tr.title} → {val}[/green]")


def hydrate_and_lunch_reminder(start_time, asked):
    now = datetime.now(timezone.utc)
    elapsed = now - start_time
    if elapsed >= timedelta(hours=2) and not asked["water"]:
        if typer.confirm("🚰 Two hours in—grab some water or stretch?"):
            asked["water"] = True
    if elapsed >= timedelta(hours=4) and not asked["lunch"]:
        if typer.confirm("🍱 Four hours in—time for a lunch break?"):
            asked["lunch"] = True


@app.command("start-day")
def start_day(overload_threshold: int = 480):
    console.rule("[bold blue]🌞 Start Your Day 🌞[/bold blue]")

    # 1) Motivation & Weather
    console.print("Let's get this day going!")
    console.print(Panel(get_motivational_quote(),
                  title="Motivation", style="green"))
    show_today_weather_cli()

    # 2) Choose tasks
    tasks = select_tasks_cli()
    if not tasks:
        console.print("[yellow]No tasks selected—bye![/yellow]")
        return

    # 3) Allocate time
    plan, total = ask_time_for_tasks_cli(tasks)
    if total > overload_threshold:
        console.print(
            f"[bold yellow]⚠ You planned {total}min (> {overload_threshold})—reduce to avoid burnout.[/bold yellow]")

    # 4) Initial trackers
    console.rule("[bold]Log Initial Trackers[/bold]")
    log_trackers_cli()

    # 5) Begin Guided Pomodoro for each task
    session_start = datetime.now(timezone.utc)
    reminders = {"water": False, "lunch": False}

    for idx, item in enumerate(plan, 1):
        task, minutes = item["task"], item["minutes"]
        console.rule(
            f"[magenta]Task {idx}/{len(plan)}: {task.title}[/magenta]")

        # Prep checklist
        console.print(
            "[bold]📝 Take 5 min to make a checklist of what you want to complete this session.[/bold]")
        prompt_continue(
            "Press Enter when your checklist is done (or after 5 min)…")
        # Optionally you could call pomodoro_timer(5) here.

        # Confirm start
        console.print(
            f"[bold blue]Ready to start {minutes} min of focused work on '{task.title}'?[/bold blue]")
        prompt_continue("Press Enter to begin…")

        # Run Pomodoro sessions
        focus, brk = modify_pomodoro_lengths(
            25 if minutes <= 120 else 45, 5 if minutes <= 120 else 10)
        sessions = (minutes + focus - 1) // focus
        distracted = 0

        for s in range(sessions):
            console.print(
                f"▶️ [bold]Session {s+1}/{sessions}: Focus {focus} min[/bold]")
            pomodoro_timer(focus)
            run_hooks("task", "pomodoro_done", task)

            extra = prompt_for_int("Distracted minutes?", 0)
            distracted += extra

            if s < sessions - 1:
                console.print(f"☕ [bold]Break {brk} min[/bold]")
                pomodoro_timer(brk)

        # Makeup
        if distracted:
            console.print(f"[red]🔄 Need {distracted} min makeup focus[/red]")
            makeups = (distracted + focus - 1) // focus
            for m in range(makeups):
                length = min(focus, distracted)
                console.print(f"▶️ Makeup {m+1}/{makeups}: {length} min")
                pomodoro_timer(length)
                run_hooks("task", "pomodoro_done", task)
                distracted -= length

        # Mark complete & record notes
        run_hooks("task", "completed", task)
        console.print(f"[green]✔️ Completed '{task.title}'[/green]")

        # Log trackers & feelings
        console.rule("[bold]Log Trackers & Mood[/bold]")
        log_trackers_cli()
        feeling = typer.prompt(
            "How did you feel? (e.g. great, tired)", default="")
        if feeling:
            # Try to find a "mood" tracker, skip if not found
            mood_tracker = track_repository.get_tracker_by_title("mood")
            if mood_tracker:
                entry = track_repository.add_tracker_entry(
                    tracker_id=mood_tracker.id,
                    timestamp=now_utc(),
                    value=feeling,
                    notes=None  # Start day mood doesn't support notes
                )
                run_hooks("tracker", "logged", entry)

        # Periodic reminders
        hydrate_and_lunch_reminder(session_start, reminders)

        if idx < len(plan):
            console.print(f"[cyan]Next up: {plan[idx]['task'].title}[/cyan]")
            prompt_continue()

    # 6) End-of-day report
    console.rule("[bold green]🎉 Day Complete![/bold green]")
    report = get_feedback_saying("end_of_day")
    console.print(Panel(report, title="Congratulations!", style="green"))
