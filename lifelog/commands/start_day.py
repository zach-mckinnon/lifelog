import typer
from rich.console import Console
from rich.panel import Panel
from datetime import datetime, timedelta
from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, time_repository
from lifelog.commands.time_module import app as time_app
from lifelog.commands.track_module import app as track_app

console = Console()
app = typer.Typer(help="Guided, gamified start-of-day focus assistant.")

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

    # Step 2: Show tasks & let user pick today's tasks
    all_tasks = get_today_tasks()
    if not all_tasks:
        console.print(
            "[yellow]No tasks found. Add tasks with 'llog task add'![/yellow]")
        return

    console.print(
        "\n[bold]Which tasks do you want to focus on today? (Separate numbers by commas, e.g., 1,3,5)[/bold]")
    for i, t in enumerate(all_tasks, 1):
        due_str = f"(due: {t.due.split('T')[0]})" if t.due else ""
        console.print(f"{i}. [cyan]{t.title}[/cyan] {due_str}")

    selection = typer.prompt("Enter task numbers")
    try:
        selected_idx = [
            int(x.strip()) - 1 for x in selection.split(",") if x.strip()]
        today_tasks = [all_tasks[i] for i in selected_idx]
    except Exception:
        console.print("[red]Invalid selection. Exiting.[/red]")
        return

    # Step 3: Ask time allocation per task
    focus_plan = []
    total_minutes = 0
    for task in today_tasks:
        mins = typer.prompt(
            f"How many minutes do you want to spend on [bold]{task.title}[/bold]?",
            default="25"
        )
        try:
            mins = int(mins)
            focus_plan.append({"task": task, "minutes": mins})
            total_minutes += mins
        except Exception:
            console.print("[red]Invalid input, using 25 minutes.[/red]")
            focus_plan.append({"task": task, "minutes": 25})
            total_minutes += 25

    if total_minutes > 480:
        console.print(
            "[bold yellow]⚠️ You planned more than 8 hours! Consider narrowing your focus to prevent burnout. You can always do more after your day plan is over![/bold yellow]")

    # Step 4: Prompt for tracker log at start
    trackers = get_all_trackers()
    if trackers:
        console.print("\n[bold]Would you like to log any trackers now?[/bold]")
        for i, tr in enumerate(trackers, 1):
            log_now = typer.confirm(
                f"Log [bold]{tr.title}[/bold]?", default=False)
            if log_now:
                # Reuse existing command
                value = typer.prompt(f"Enter value for {tr.title}")
                track_repository.add_entry(
                    tracker_id=tr.id, timestamp=datetime.now().isoformat(), value=value)
                console.print(f"[green]Logged {tr.title} ➡️ {value}[/green]")

    # Step 5: Begin guided Pomodoro focus for each task
    for i, plan in enumerate(focus_plan, 1):
        task = plan["task"]
        minutes = plan["minutes"]
        console.rule(
            f"[bold magenta]Task {i}/{len(focus_plan)}: {task.title}[/bold magenta]")
        console.print(
            f"Total focus time: [bold]{minutes}[/bold] minutes. Press Enter to start.")
        typer.prompt("Ready?")

        # Decide Pomodoro pattern:
        if minutes <= 120:
            focus_length = 25
            break_length = 5
        else:
            focus_length = 45
            break_length = 10
        console.print(
            f"[blue]We'll use {focus_length} min focus, {break_length} min break cycles.[/blue]")

        # Calculate sessions:
        sessions_needed = (minutes + focus_length - 1) // focus_length
        minutes_left = minutes
        distracted_total = 0

        for session in range(sessions_needed):
            session_time = min(focus_length, minutes_left)
            console.print(
                f"[blue]Pomodoro {session+1}/{sessions_needed} for {session_time} min[/blue]")
            pomodoro_timer(session_time)

            distracted = typer.prompt(
                "Were you distracted? Enter distracted minutes (or 0)", default="0")
            try:
                distracted = int(distracted)
                distracted_total += distracted
            except Exception:
                distracted = 0

            if session < sessions_needed - 1:
                console.print(Panel(get_feedback_saying(
                    "transition_break"), style="yellow"))
                console.print(
                    f"Take a {break_length}-min break! Press Enter to continue when ready.")
                typer.prompt(f"Press Enter after your break.")

            minutes_left -= session_time

        # If distracted time > 0, run makeup Pomodoro(s)
        if distracted_total > 0:
            # Always use same session length as above
            extra_sessions = (distracted_total +
                              focus_length - 1) // focus_length
            console.print(
                f"[red]You were distracted for {distracted_total} minutes. Let's make up for it![/red]")
            for es in range(extra_sessions):
                # Last session may be shorter than full
                session_time = min(focus_length, distracted_total)
                pomodoro_timer(session_time)
                distracted_total -= session_time
                typer.prompt(
                    "Pomodoro done! Take a break and press Enter to continue.")

        # Prompt for notes at end
        notes = typer.prompt("Any notes about this session?", default="")
        if notes.strip():
            now = datetime.now()
            time_repository.start_time_entry({
                "title": task.title,
                "start": now.isoformat(),
                "category": task.category,
                "project": task.project,
                "notes": notes,
            })
            time_repository.stop_active_time_entry(
                end_time=now + timedelta(minutes=minutes))
            console.print(f"[green]Session for '{task.title}' logged.[/green]")

        # Prompt for tracker logs between tasks
        if trackers:
            console.print("\n[bold]Log trackers between tasks?[/bold]")
            for tr in trackers:
                log_now = typer.confirm(
                    f"Log [bold]{tr.title}[/bold]?", default=False)
                if log_now:
                    value = typer.prompt(f"Enter value for {tr.title}")
                    track_repository.add_entry(
                        tracker_id=tr.id, timestamp=datetime.now().isoformat(), value=value)
                    console.print(
                        f"[green]Logged {tr.title} ➡️ {value}[/green]")

        if i < len(focus_plan):
            console.print(
                f"[yellow]Transition: Next up is [bold]{focus_plan[i]['task'].title}[/bold].[/yellow]")
            typer.prompt(
                "Take 5 minutes to transition. Press Enter when ready for next task.")

    # End-of-day celebration
    console.rule("[bold green]🎉 Day Complete! 🎉[/bold green]")
    console.print(get_feedback_saying("end_of_day"))
    console.print(
        "[bold cyan]See 'llog report summary-time' and 'llog report summary-trackers' for your stats![/bold cyan]")


# If you want this command available via CLI, add this line for Typer to find:
if __name__ == "__main__":
    app()
