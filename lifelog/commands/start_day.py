import logging
from lifelog.utils.db import (
    task_repository,
    track_repository,
    time_repository,
    environment_repository,
)
from rich.progress import Progress, BarColumn, TimeRemainingColumn, TextColumn
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone, date
import typer
from rich.console import Console
from rich.panel import Panel
from datetime import datetime, timedelta, date

from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, time_repository, environment_repository
from lifelog.commands.environmental_sync import fetch_today_forecast
from lifelog.utils.shared_utils import (
    format_datetime_for_user,
    now_utc,
    now_local,
    utc_iso_to_local,
    format_datetime_for_user
)
from lifelog.utils.db.gamify_repository import modify_pomodoro_lengths

console = Console()
app = typer.Typer(help="Guided, gamified start-of-day focus assistant (CLI).")


def pomodoro_timer(minutes):
    import time as t
    for min_left in range(minutes, 0, -1):
        console.print(
            f"[bold green]⏳ {min_left} min left...[/bold green]", end='\r')
        t.sleep(60)
    console.print("[bold yellow]Pomodoro session complete![/bold yellow]")


# ─── Setup ─────────────────────────────────────────────────────────────────────
logger = logging.getLogger("start_day_cli")
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler("start_day.log")
handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

console = Console()
app = typer.Typer(help="Guided, gamified start-of-day focus assistant (CLI).")

# ─── Helpers ───────────────────────────────────────────────────────────────────


def prompt_for_int(prompt: str, default: int) -> int:
    """Prompt the user for an integer, falling back to default on bad input."""
    val = typer.prompt(prompt, default=str(default))
    try:
        return int(val)
    except ValueError:
        console.print(
            f"[yellow]Invalid number, using default {default}[/yellow]")
        return default


def prompt_continue(label: str = "Press Enter to continue...") -> None:
    """Wait for the user to press Enter or exit if interrupted."""
    try:
        typer.prompt(label, default="")
    except (KeyboardInterrupt, EOFError):
        console.print("[red]Interrupted—exiting start-day.[/red]")
        raise typer.Exit()


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """Yes/No prompt wrapper."""
    try:
        return typer.confirm(prompt, default=default)
    except (KeyboardInterrupt, EOFError):
        return False


def now_iso_utc() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def get_weather_service():
    """Abstracted weather fetch—change implementation here if needed."""
    return fetch_today_forecast

# ─── Core Steps ────────────────────────────────────────────────────────────────


@app.command("start-day")
def start_day(
    overload_threshold: int = typer.Option(
        480, help="Max planned minutes before warning")
) -> None:
    """
    Start a guided, motivational, structured focus day!
    """
    console.rule("[bold blue]🌞 Start Your Day 🌞[/bold blue]")

    # Step 1: Motivation
    quote = get_motivational_quote()
    console.print(Panel(quote, title="Motivation for Today", style="green"))

    # Step 1a: Weather
    show_today_weather_cli()

    # Step 2: Task selection
    today_tasks = select_tasks_cli()
    if not today_tasks:
        return

    # Step 3: Time allocation
    focus_plan, total = ask_time_for_tasks_cli(today_tasks)

    # Step 4: Overload warning
    if total > overload_threshold:
        console.print(
            f"[bold yellow]⚠️ You planned {total} minutes (> {overload_threshold}). "
            "Consider reducing to avoid burnout.[/]"
        )

    # Step 5: Initial trackers
    log_initial_trackers_cli()

    # Step 6: Pomodoro loop
    for idx, item in enumerate(focus_plan, start=1):
        task = item["task"]
        minutes = item["minutes"]

        console.rule(f"[magenta]Task {idx}/{len(focus_plan)}: {task.title}[/]")
        console.print(f"Total focus time: [bold]{minutes}[/] minutes.")
        prompt_continue("Ready? (Press Enter)")

        distracted = run_pomodoro_sessions_cli(task, minutes)
        run_makeup_sessions_cli(distracted)
        record_task_notes_cli(task, minutes)
        log_between_tasks_cli()
        if idx < len(focus_plan):
            console.print(f"[cyan]Next up: {focus_plan[idx]['task'].title}[/]")
            prompt_continue()

    # Step 7: End-of-day feedback
    feedback = get_feedback_saying("end_of_day")
    console.print(Panel(feedback, title="🎉 Day Complete!", style="green"))

# ─── Subroutines ──────────────────────────────────────────────────────────────


def show_today_weather_cli() -> None:
    """
    Fetch today’s forecast, convert each timestamp to local time,
    format as MM/DD/YY HH:MM, and display.
    """
    env = None
    try:
        env = environment_repository.get_latest_environment_data("weather")
    except Exception:
        logger.exception("Failed loading environment data")

    if not env:
        console.print("[yellow]No weather data. Run 'llog sync' first.[/]")
        return

    lat, lon = env.get("latitude"), env.get("longitude")
    if lat is None or lon is None:
        console.print("[yellow]Incomplete location data.[/]")
        return

    try:
        forecast = fetch_today_forecast(lat, lon)
    except Exception as e:
        logger.exception("Weather fetch error")
        console.print(f"[red]Failed fetching weather: {e}[/]")
        return

    if not forecast:
        console.print("[yellow]No forecast for today.[/]")
        return

    # Use now_local() for “today” header, then format date-only
    today_header = format_datetime_for_user(now_local()).split(" ")[0]
    lines = [f"Forecast for {today_header} (4h intervals):"]
    for entry in forecast:
        # Convert the full UTC ISO timestamp to user-local datetime, then format
        local_dt = utc_iso_to_local(entry["time"])
        time_str = format_datetime_for_user(local_dt)
        temp = (
            f"{entry['temperature']:.1f}°C"
            if isinstance(entry["temperature"], float)
            else f"{entry['temperature']}°C"
        )
        pop = f"{entry['precip_prob']}%" if entry["precip_prob"] is not None else "-"
        lines.append(
            f"{time_str} — {temp}, Precip {pop}, {entry['description']}")

    console.print(
        Panel("\n".join(lines), title="🌤️ Today's Forecast", style="cyan"))


def select_tasks_cli() -> Optional[List]:
    """
    Show the user all their open tasks with due-dates in local time,
    then prompt them to pick a subset.
    """
    try:
        all_tasks = task_repository.get_all_tasks()
    except Exception:
        logger.exception("Failed querying tasks")
        console.print("[red]Could not load tasks. Check logs.[/]")
        return None

    if not all_tasks:
        console.print("[yellow]No tasks. Add with 'llog task add'.[/]")
        return None

    console.print("[bold]Select tasks for today (e.g. 1,3):[/]")
    for i, t in enumerate(all_tasks, 1):
        due_str = "-"
        if t.due:
            try:
                # t.due is ISO UTC string or naive; format via our helper
                dt = utc_iso_to_local(t.due)
                due_str = format_datetime_for_user(dt)
            except Exception:
                due_str = str(t.due)
        console.print(f"{i}. [cyan]{t.title}[/] (due: {due_str})")

    sel = typer.prompt("Enter numbers", default="")
    if not sel.strip():
        console.print("[yellow]No tasks selected—aborting.[/]")
        return None

    chosen, invalid = [], False
    for part in sel.split(","):
        part = part.strip()
        if not part.isdigit():
            invalid = True
            break
        idx = int(part) - 1
        if idx < 0 or idx >= len(all_tasks):
            invalid = True
            break
        chosen.append(all_tasks[idx])

    if invalid or not chosen:
        console.print("[red]Invalid selection—aborting.[/]")
        return None

    return chosen


def ask_time_for_tasks_cli(tasks: List) -> (Tuple[List[Dict], int]):
    plan, total = [], 0
    for t in tasks:
        mins = prompt_for_int(f"Minutes for '{t.title}'?", 25)
        plan.append({"task": t, "minutes": mins})
        total += mins
    return plan, total


def log_initial_trackers_cli() -> None:
    """
    Offer to log each tracker now; record each entry with a UTC timestamp.
    """
    try:
        trackers = track_repository.get_all_trackers()
    except Exception:
        logger.exception("Failed loading trackers")
        return

    for tr in trackers:
        if typer.confirm(f"Log '{tr.title}' now?", default=False):
            val = typer.prompt(f"Value for {tr.title}", default="")
            if val:
                try:
                    track_repository.add_tracker_entry(
                        tracker_id=tr.id,
                        timestamp=now_utc().isoformat(),
                        value=val,
                    )
                    console.print(f"[green]Logged {tr.title} → {val}[/]")
                except Exception:
                    logger.exception("Failed logging tracker")


def run_pomodoro_sessions_cli(task, total_minutes: int) -> int:
    """Runs focus/break cycles, returns total distracted minutes."""
    base_focus, base_break = (25, 5) if total_minutes <= 120 else (45, 10)
    focus, brk = modify_pomodoro_lengths(base_focus, base_break)
    console.print(f"[blue]Using {focus}min focus / {brk}min break.[/]")
    sessions = (total_minutes + focus - 1) // focus
    left, distracted = total_minutes, 0

    for i in range(sessions):
        length = min(focus, left)
        console.print(f"[bold]Pomodoro {i+1}/{sessions}: {length}min[/]")
        prompt_continue("Start session (Enter)...")

        # Rich Progress bar countdown
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as prog:
            task_id = prog.add_task("⏳ Focus", total=length * 60)
            for _ in range(length * 60):
                prog.update(task_id, advance=1)
                typer.sleep(1)

        console.print("[green]Session complete![/]")
        extra = prompt_for_int("Distracted minutes?", 0)
        distracted += extra
        left -= length

        if i < sessions - 1:
            console.print(Panel(get_feedback_saying(
                "transition_break"), style="yellow"))
            prompt_continue(f"Break {brk}min (Enter when ready)")

    return distracted


def run_makeup_sessions_cli(distracted: int) -> None:
    if distracted <= 0:
        return
    console.print(f"[red]Need {distracted}min makeup focus![/]")
    focus = 25
    sessions = (distracted + focus - 1) // focus
    rem = distracted

    for i in range(sessions):
        length = min(focus, rem)
        console.print(f"[magenta]Makeup {i+1}/{sessions}: {length}min[/]")
        prompt_continue("Press Enter to start...")
        pomodoro_timer(length)
        rem -= length
        if rem > 0:
            prompt_continue("Enter after short break...")


def record_task_notes_cli(task, minutes: int) -> None:
    """
    Prompt the user for notes, then start+stop a time entry in UTC
    covering exactly `minutes` minutes.
    """
    notes = typer.prompt("Any notes? (blank to skip)", default="").strip()
    if not notes:
        return

    try:
        # 1) record start in UTC
        start_dt = now_utc()
        time_repository.start_time_entry(
            title=task.title,
            task_id=task.id,
            start_time=start_dt.isoformat(),
            category=task.category,
            project=task.project,
            notes=notes,
        )
        # 2) record stop = start + minutes (also UTC)
        end_dt = start_dt + timedelta(minutes=minutes)
        time_repository.stop_active_time_entry(end_time=end_dt.isoformat())
        console.print("[green]Notes logged.[/]")
    except Exception:
        logger.exception("Failed logging task notes")


def log_between_tasks_cli() -> None:
    """
    Between focus sessions, offer to log any tracker now,
    stamping each entry in UTC.
    """
    try:
        trackers = track_repository.get_all_trackers()
    except Exception:
        return

    for tr in trackers:
        if typer.confirm(f"Log '{tr.title}' now?", default=False):
            val = typer.prompt(f"Value for {tr.title}", default="")
            if val:
                try:
                    track_repository.add_tracker_entry(
                        tracker_id=tr.id,
                        timestamp=now_utc().isoformat(),
                        value=val,
                    )
                    console.print(f"[green]Logged {tr.title} → {val}[/]")
                except Exception:
                    logger.exception("Failed logging between tasks")


if __name__ == "__main__":
    app()
