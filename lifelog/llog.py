#!/home/zach.mckinnon/lifelog/.venv/bin/python

from typing import Optional
import typer
from lifelog.commands import time, habit, metric, task
from lifelog.commands import report
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="🧠 Lifelog CLI: Track your habits, health, time, and tasks.")
console = Console()

# Register all modules
app.add_typer(metric.app, name="metric", help="Track recurring self-measurements like mood, energy, pain.")
app.add_typer(time.app, name="time", help="Track time in categories like resting, working, socializing.")
app.add_typer(habit.app, name="habit", help="Track recurring habits and completions.")
app.add_typer(task.app, name="task", help="Create, track, and complete actionable tasks.")
app.add_typer(report.app, name="report", help="View detailed reports and insights.")

@app.command("help")
def help_command():
    """Show a categorized list of available commands with Rich styling."""
    table = Table(title="🧠 Lifelog CLI – Command Guide", show_lines=True, expand=True)
    table.add_column("Category", style="bold magenta", no_wrap=True)
    table.add_column("Command Examples", style="cyan")

    table.add_row(
        "Metric Tracking",
        """\
llog metric add mood scale --min 1 --max 10
llog metric list
llog entry mood 7 "Feeling decent" +morning"""
    )

    table.add_row(
        "Low-Effort Logging",
        """\
llog entry energy 5 +afternoon
llog checkin"""
    )

    table.add_row(
        "Time Tracking",
        """\
llog time start work
llog time stop
llog time status"""
    )

    table.add_row(
        "Habit Tracking",
        """\
llog habit add "Take Vitamins"
llog habit done "Take Vitamins"
llog habit list"""
    )

    table.add_row(
        "Task Management",
        """\
llog task add "Clean desk" --project Home --due tomorrow
llog task list --project Home
llog task 42
llog task modify 42 --title "Tidy desk"
llog task done 42"""
    )

    table.add_row(
        "Reports",
        """\
llog report trend mood --period week
llog report compare mood --metric2 sleepq
llog report correlations
llog report outliers energy
llog report heatmap habit
llog report streaks --habit "Exercise"
llog report totals time
llog report wellness
llog report balance
llog report insights
llog report missed-data"""
    )

    console.print(table)
    console.print(Panel.fit("[italic green]Tip:[/] Use [bold]--help[/bold] on any command to see options.\nExample: [bold yellow]llog report --help[/bold yellow]"))

@app.command("entry")
def shortcut_entry(*args: str):
    """
    Shortcut alias for `metric.entry`. Allows quick logging like:
    llog entry mood 5 "Feeling meh" +evening
    """
    from commands.metric import log_entry
    if len(args) < 2:
        console.print("[bold red]Usage:[/bold red] llog entry <metric> <value> [notes] [+tags]")
        raise typer.Exit()
    name, value, *extras = args
    log_entry(name, value, extras)

@app.command("task")
def task_detail(task_id: Optional[int] = None):
    """
    Show details of a specific task by ID.
    """
    if task_id:
        from commands.task import info
        return info(task_id)

if __name__ == "__main__":
    app()