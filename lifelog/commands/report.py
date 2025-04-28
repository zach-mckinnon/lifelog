# # lifelog/commands/report.py
''' 
Lifelog Reporting Module
This module provides functionality to generate various reports and analytics for the Lifelog application.
It includes features for generating quick summaries, advanced analytics, and exporting reports in different formats.
The module uses the Typer library for command-line interface (CLI) management and integrates with various analytics functions for detailed reporting.
'''
from datetime import datetime, timedelta
import json
from typing import Optional
import typer

# Core summaries
import lifelog.config.config_manager as cf
from lifelog.commands.utils.shared_utils import parse_args

from lifelog.commands.utils.reporting.analytics.descriptive import report_descriptive
from lifelog.commands.utils.reporting.analytics.diagnostics import report_diagnostics
from lifelog.commands.utils.reporting.analytics.correlation import report_correlation
from lifelog.commands.utils.reporting.analytics.prediction import report_prediction
from lifelog.commands.utils.reporting.analytics.prescriptive import report_prescriptive
from lifelog.commands.utils.reporting.summary import (
    summary_metric,
    summary_time,
    summary_daily, 
)

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

app = typer.Typer(help="📊 Generate data reports and dashboards")

# --- Summary command group ---
summary_app = typer.Typer(name="summary", help="Quick summaries for each module")
app.add_typer(summary_app, name="summary")

@summary_app.callback(invoke_without_command=True)
def summary_all(
    since: str = typer.Option("7d", "--since", help="Time window: d=days, w=weeks, m=months"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """
    📋 Combined summary across all modules: trackers, time, tasks, environment.
    """
    # 1. Trackers
    summary_metric(since=since, export=export)
    # 2. Time
    summary_time(since=since, export=export)
    # # 3. Tasks
    # summary_tasks(since=since, export=export)
    # # 4. Environment snapshot
    # summary_environment(export=export)

@summary_app.command("time")
def summary_time_cmd(
    since: str = typer.Option("7d", "--since", help="Time window for time summary"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """⏱  Quick time summary."""
    summary_time(since=since, export=export)

@summary_app.command("daily")
def summary_daily_cmd(
    since: str = typer.Option("7d", "--since", help="Time window for daily summary"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """
    📅  Quick daily summary.
    """
    summary_daily(since=since, export=export)
    
# @summary_app.command("tasks")
# def summary_tasks_cmd(
#     since: str = typer.Option("7d", "--since", help="Time window for task summary"),
#     export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
# ):
#     """📋 Quick task summary."""
#     summary_tasks(since=since, export=export)

@summary_app.command("track")
def summary_track_cmd(
    since: str = typer.Option("7d", "--since", help="Time window for tracker summary"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """✏️  Quick tracker summary."""
    summary_metric(since=since, export=export)

# --- Advanced analytics commands ---
@app.command("diagnostics")
def diagnostics_cmd(
    since: str = typer.Option("30d", "--since", help="Time window for diagnostics"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """🧐 Diagnostic analytics."""
    report_diagnostics(since=since, export=export)

@app.command("correlations")
def correlations_cmd(
    since: str = typer.Option("30d", "--since", help="Time window for correlations"),
    top_n: int = typer.Option(5, help="Number of top correlations"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """🔍 Correlation analysis."""
    report_correlation(since=since, top_n=top_n, export=export)

@app.command("predict")
def predict_cmd(
    model: str = typer.Option("simple", help="simple|regression"),
    days: int = typer.Option(7, help="Days to forecast ahead"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """📈 Forecast future trends."""
    report_prediction(model=model, days=days, export=export)

@app.command("prescribe")
def prescribe_cmd(
    scenario: str = typer.Option("sleep_food", help="Preset scenario"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """💡 Prescriptive analytics."""
    report_prescriptive(scenario=scenario, export=export)

@app.command("describe")
def describe_cmd(
    since: str = typer.Option("30d", "--since", help="Time window for descriptive analytics"),
    export: Optional[str] = typer.Option(None, "--export", help="Optional json|csv filepath"),
):
    """📊 Descriptive analytics."""
    report_descriptive(since=since, export=export)


@app.command("agenda")
def agenda_cmd():
    """
    📅 Show a calendar-style agenda for tasks.
    """

    TASK_FILE = cf.get_task_file()

    if not TASK_FILE.exists():
        console.print("[red]No tasks found.[/red]")
        return

    with open(TASK_FILE, "r") as f:
        tasks = json.load(f)

    # Filter only upcoming and pending/active tasks
    now = datetime.now()
    upcoming_tasks = [
        task for task in tasks
        if task.get("status") in ["backlog", "active"] and task.get("due")
    ]

    if not upcoming_tasks:
        console.print("[green]No upcoming tasks! 🎉[/green]")
        return

    # Sort by due date
    upcoming_tasks.sort(key=lambda t: t["due"])

    today = now.date()
    tomorrow = (now + timedelta(days=1)).date()

    console.rule("[bold green]📅 Agenda View[/bold green]")

    # Today
    today_tasks = [t for t in upcoming_tasks if datetime.fromisoformat(t["due"]).date() == today]
    if today_tasks:
        console.print("[bold underline]Today:[/bold underline]")
        for task in today_tasks:
            due = datetime.fromisoformat(task["due"]).strftime("%H:%M")
            line = Text()
            line.append(f"{due}", style="yellow")
            line.append(" → ")
            line.append(f"{task['title']}", style="bold")
            console.print(line)

    # Tomorrow
    tomorrow_tasks = [t for t in upcoming_tasks if datetime.fromisoformat(t["due"]).date() == tomorrow]
    if tomorrow_tasks:
        console.print("\n[bold underline]Tomorrow:[/bold underline]")
        for task in tomorrow_tasks:
            due = datetime.fromisoformat(task["due"]).strftime("%H:%M")
            line = Text()
            line.append(f"{due}", style="cyan")
            line.append(" → ")
            line.append(f"{task['title']}", style="bold")
            console.print(line)

    # Later
    later_tasks = [t for t in upcoming_tasks if datetime.fromisoformat(t["due"]).date() > tomorrow]
    if later_tasks:
        console.print("\n[bold underline]Later:[/bold underline]")
        for task in later_tasks:
            due_dt = datetime.fromisoformat(task["due"])
            due_str = due_dt.strftime("%a %m-%d %H:%M")
            line = Text()
            line.append(f"{due_str}", style="dim")
            line.append(" → ")
            line.append(f"{task['title']}", style="bold")
            console.print(line)

    console.rule()

if __name__ == "__main__":
    app()