from typing import Optional
import typer

# Core summaries
from commands.utils.reporting.analytics.descriptive import report_descriptive
from commands.utils.reporting.analytics.diagnostics import report_diagnostics
from lifelog.commands.utils.reporting.analytics.correlation import report_correlation
from lifelog.commands.utils.reporting.analytics.prediction import report_prediction
from lifelog.commands.utils.reporting.analytics.prescriptive import report_prescriptive
from lifelog.commands.utils.reporting.summary import (
    summary_metric,
    summary_time,
    summary_daily, 
)


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

if __name__ == "__main__":
    app()