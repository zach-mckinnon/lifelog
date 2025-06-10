import typer
from rich.console import Console
from rich.panel import Panel
from datetime import datetime, timedelta, date
import requests

from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, time_repository, environment_repository
from lifelog.commands.environmental_sync import fetch_today_forecast

console = Console()
app = typer.Typer(help="Guided, gamified start-of-day focus assistant (CLI).")
# Helper: Get today's tasks (non-completed)


def get_today_tasks():
    return task_repository.get_all_tasks()

# Helper: Get all trackers


def get_all_trackers():
    return track_repository.get_all_trackers()

# Helper: Pomodoro timer (simplified: blocking, prints time)


def pomodoro_timer(minutes):
    import time as t
    for min_left in range(minutes, 0, -1):
        console.print(
            f"[bold green]⏳ {min_left} min left...[/bold green]", end='\r')
        t.sleep(60)
    console.print("[bold yellow]Pomodoro session complete![/bold yellow]")


@app.command("start-day")
def start_day():
    """Start a guided, motivational, structured focus day!"""
    console.rule("[bold blue]🌞 Start Your Day 🌞[/bold blue]")

    # Step 1: Greet & motivate
    quote = get_motivational_quote()
    console.print(Panel(quote, style="bold green",
                  title="Motivation for Today"))

    # Step 1.a: Show today's weather forecast
    show_today_weather_cli()

    # Step 2: Select tasks
    today_tasks = select_tasks_cli()
    if not today_tasks:
        return

    # Step 3: Ask time allocation
    focus_plan, total_minutes = ask_time_for_tasks_cli(today_tasks)

    # Step 4: Warn if overload
    warn_overload_cli(total_minutes)

    # Step 5: Initial tracker logs
    trackers = track_repository.get_all_trackers()
    log_initial_trackers_cli()

    # Step 6: Guided Pomodoro for each task
    for idx, item in enumerate(focus_plan, start=1):
        task = item["task"]
        minutes = item["minutes"]

        console.rule(
            f"[bold magenta]Task {idx}/{len(focus_plan)}: {task.title}[/bold magenta]")
        console.print(
            f"Total focus time: [bold]{minutes}[/bold] minutes. Press Enter to start.")
        typer.prompt("Ready?")

        # Pomodoro sessions
        distracted = run_pomodoro_sessions_cli(task, minutes)

        # Makeup Pomodoros if needed
        run_makeup_sessions_cli(distracted)

        # End-of-task notes
        record_task_notes_cli(task, minutes)

        # Tracker logs between tasks
        log_between_tasks_cli(trackers)

        # Transition to next task
        if idx < len(focus_plan):
            next_task = focus_plan[idx]["task"]
            console.print(
                f"[yellow]Transition: Next is [bold]{next_task.title}[/bold]. Take a short break. Press Enter when ready.[/yellow]")
            typer.prompt("Press Enter to continue.")

    # Step 7: End-of-day feedback
    show_end_of_day_cli()


def show_today_weather_cli():
    """
    Retrieve saved location from environment data, fetch today's forecast,
    and display in the CLI via Rich.
    """
    env = environment_repository.get_latest_environment_data("weather")
    if not env:
        console.print(
            "[yellow]No weather/location data available. Please sync environment first.[/yellow]")
        return
    lat = env.get("latitude")
    lon = env.get("longitude")
    if lat is None or lon is None:
        console.print(
            "[yellow]Location (latitude/longitude) missing in environment data.[/yellow]")
        return

    try:
        # fetch_today_forecast returns list of dicts: time, temperature, precip_prob, description
        forecast_entries = fetch_today_forecast(lat, lon)
    except Exception as e:
        console.print(f"[red]Weather fetch error: {e}[/red]")
        return

    if not forecast_entries:
        console.print("[yellow]No forecast available for today.[/yellow]")
        return

    # Build lines for display
    lines = []
    today_str = date.today().isoformat()
    lines.append(f"Today's forecast ({today_str}), every 4 hours:")
    for entry in forecast_entries:
        # entry["time"] is "YYYY-MM-DDThh:MM"
        t_local = entry["time"][11:]  # "hh:MM"
        temp = entry["temperature"]
        precip = entry["precip_prob"]
        desc = entry["description"]
        # Format temperature
        if temp is None:
            temp_str = "-"
        else:
            temp_str = f"{temp:.1f}°C" if isinstance(
                temp, float) else f"{temp}°C"
        precip_str = f"{precip}%" if precip is not None else "-"
        lines.append(f"{t_local} — {temp_str}, Precip {precip_str}, {desc}")

    # Display in a Rich Panel for clarity
    panel_content = "\n".join(lines)
    console.print(
        Panel(panel_content, title="🌤️ Today's Forecast", style="cyan"))


def select_tasks_cli():
    """
    Show all non-completed tasks, let user pick via comma-separated indices.
    Returns list of Task instances or None if cancelled/invalid.
    """
    all_tasks = task_repository.get_all_tasks()
    if not all_tasks:
        console.print(
            "[yellow]No tasks found. Add tasks with 'llog task add'![/yellow]")
        return None

    console.print(
        "\n[bold]Which tasks do you want to focus on today? (Separate numbers by commas, e.g., 1,3,5)[/bold]")
    for i, t in enumerate(all_tasks, 1):
        due_str = ""
        if getattr(t, "due", None):
            # original code splits on 'T' to get date
            try:
                due_date = t.due.split('T')[0]
            except Exception:
                due_date = str(t.due)
            due_str = f"(due: {due_date})"
        console.print(f"{i}. [cyan]{t.title}[/cyan] {due_str}")

    selection = typer.prompt("Enter task numbers", default="")
    if not selection.strip():
        console.print("[yellow]No tasks selected. Exiting start-day.[/yellow]")
        return None

    idx_list = []
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            console.print(f"[red]Invalid selection: '{part}'. Exiting.[/red]")
            return None
        ii = int(part) - 1
        if ii < 0 or ii >= len(all_tasks):
            console.print(
                f"[red]Selection out of range: {part}. Exiting.[/red]")
            return None
        idx_list.append(ii)
    if not idx_list:
        console.print("[yellow]No valid selections made. Exiting.[/yellow]")
        return None

    today_tasks = [all_tasks[i] for i in idx_list]
    return today_tasks


def ask_time_for_tasks_cli(tasks):
    """
    For each Task in tasks, prompt “How many minutes?” with default 25.
    Returns list of dicts {"task": Task, "minutes": int}.
    """
    plan = []
    total = 0
    for task in tasks:
        prompt_text = f"How many minutes do you want to spend on [bold]{task.title}[/bold]? "
        mins_str = typer.prompt(prompt_text, default="25")
        try:
            mins = int(mins_str)
        except Exception:
            console.print("[red]Invalid input, using 25 minutes.[/red]")
            mins = 25
        plan.append({"task": task, "minutes": mins})
        total += mins
    return plan, total


def warn_overload_cli(total_minutes, threshold=480):
    """
    Warn if total planned minutes exceed threshold (default 480 = 8 hours).
    """
    if total_minutes > threshold:
        console.print(
            "[bold yellow]⚠️ You planned more than 8 hours! Consider narrowing your focus to prevent burnout. You can always do more after your day plan is over![/bold yellow]"
        )


def log_initial_trackers_cli():
    """
    Prompt for tracker logs at start of day.
    """
    trackers = track_repository.get_all_trackers()
    if not trackers:
        return
    console.print("\n[bold]Would you like to log any trackers now?[/bold]")
    for tr in trackers:
        log_now = typer.confirm(f"Log [bold]{tr.title}[/bold]?", default=False)
        if log_now:
            value = typer.prompt(f"Enter value for {tr.title}")
            # Use repository to add entry
            track_repository.add_tracker_entry(
                tracker_id=tr.id,
                timestamp=datetime.now().isoformat(),
                value=value
            )
            console.print(f"[green]Logged {tr.title} ➡️ {value}[/green]")


def pomodoro_timer(minutes):
    import time as _t
    for min_left in range(minutes, 0, -1):
        console.print(
            f"[bold green]⏳ {min_left} min left...[/bold green]", end='\r')
        _t.sleep(60)
    console.print("[bold yellow]\nPomodoro session complete![/bold yellow]")


def run_pomodoro_sessions_cli(task, total_minutes):
    """
    Run Pomodoro focus/break cycles for a single task.
    Returns total distracted minutes.
    """
    # Decide Pomodoro pattern
    if total_minutes <= 120:
        focus_length = 25
        break_length = 5
    else:
        focus_length = 45
        break_length = 10
    console.print(
        f"[blue]We'll use {focus_length} min focus, {break_length} min break cycles.[/blue]")

    sessions_needed = (total_minutes + focus_length - 1) // focus_length
    minutes_left = total_minutes
    distracted_total = 0

    for session in range(sessions_needed):
        session_time = min(focus_length, minutes_left)
        console.print(
            f"[blue]Pomodoro {session+1}/{sessions_needed} for {session_time} min[/blue]")
        typer.prompt("Press Enter to start this session...")
        pomodoro_timer(session_time)

        distracted_str = typer.prompt(
            "Were you distracted? Enter distracted minutes (or 0)", default="0")
        try:
            distracted = int(distracted_str)
        except Exception:
            distracted = 0
        distracted_total += distracted

        minutes_left -= session_time
        if session < sessions_needed - 1:
            # Transition break feedback
            console.print(Panel(get_feedback_saying(
                "transition_break"), style="yellow"))
            console.print(
                f"Take a {break_length}-min break! Press Enter to continue when ready.")
            typer.prompt("Press Enter after your break.")
    return distracted_total


def run_makeup_sessions_cli(distracted_total):
    """
    If distracted_total > 0, run makeup Pomodoro sessions equal to distracted minutes.
    """
    if distracted_total <= 0:
        return
    # Choose same focus length? For simplicity, use 25 min (or you could pass focus_length)
    console.print(
        f"[red]You were distracted for {distracted_total} minutes. Let's make up for it![/red]")
    # For makeup, assume same focus_length=25
    focus_length = 25
    extra_sessions = (distracted_total + focus_length - 1) // focus_length
    for es in range(extra_sessions):
        session_time = min(focus_length, distracted_total)
        console.print(
            f"[magenta]Makeup Pomodoro: {session_time} min[/magenta]")
        typer.prompt("Press Enter to start makeup session...")
        pomodoro_timer(session_time)
        distracted_total -= session_time
        if distracted_total > 0:
            console.print(
                f"[blue]Take a short break. Press Enter when ready for next makeup session.[/blue]")
            typer.prompt("Press Enter to continue.")


def record_task_notes_cli(task, total_minutes):
    """
    Prompt for notes at end of task; if provided, record a separate time entry scaled by total_minutes.
    """
    notes = typer.prompt(
        "Any notes about this session? (leave blank to skip)", default="")
    if notes.strip():
        now = datetime.now()
        # Start a new time entry for notes (similar to UI)
        time_repository.start_time_entry(
            title=task.title,
            task_id=task.id,
            start_time=now.isoformat(),
            category=task.category,
            project=task.project,
            notes=notes,
        )
        end_time = now + timedelta(minutes=total_minutes)
        # Use ISO format string
        time_repository.stop_active_time_entry(end_time=end_time.isoformat())
        console.print(f"[green]Session for '{task.title}' logged.[/green]")


def log_between_tasks_cli(trackers):
    """
    Prompt for tracker logs between tasks.
    """
    if not trackers:
        return
    console.print("\n[bold]Log trackers between tasks?[/bold]")
    for tr in trackers:
        log_now = typer.confirm(f"Log [bold]{tr.title}[/bold]?", default=False)
        if log_now:
            value = typer.prompt(f"Enter value for {tr.title}")
            track_repository.add_tracker_entry(
                tracker_id=tr.id,
                timestamp=datetime.now().isoformat(),
                value=value
            )
            console.print(f"[green]Logged {tr.title} ➡️ {value}[/green]")


def show_end_of_day_cli():
    feedback = get_feedback_saying("end_of_day")
    console.print(Panel(feedback, title="🎉 Day Complete!", style="green"))
