# lifelog/commands/summary.py
import typer
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import statistics
import termplotlib as tpl

app = typer.Typer(help="Generate reports and visual summaries of logged data.")

LOG_FILE = Path.home() / ".lifelog.json"


def load_entries():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return []


def group_by_day(entries):
    grouped = defaultdict(list)
    for entry in entries:
        ts = datetime.fromisoformat(entry["timestamp"])
        day = ts.strftime("%Y-%m-%d")
        grouped[day].append(entry)
    return dict(grouped)


def render_trend_chart(metric_name, entries):
    try:
        import termplotlib as tpl
    except ImportError:
        typer.echo("Install termplotlib to use charting: pip install termplotlib")
        raise typer.Exit()

    daily_values = defaultdict(list)
    for entry in entries:
        if entry["metric"] == metric_name:
            ts = datetime.fromisoformat(entry["timestamp"])
            day = ts.strftime("%Y-%m-%d")
            try:
                daily_values[day].append(float(entry["value"]))
            except:
                continue

    dates = sorted(daily_values.keys())
    avg_values = [round(statistics.mean(daily_values[day]), 2) for day in dates]

    fig = tpl.figure()
    fig.plot(list(range(len(avg_values))), avg_values, xlabel="Day", ylabel=metric_name, xticks=[(i, d[-5:]) for i, d in enumerate(dates)])
    fig.show()


@app.command()
def metric(metric_name: str, period: str = typer.Option("week", help="Time range: day, week, month")):
    """
    Show a trend chart for a specific metric.
    """
    entries = load_entries()
    now = datetime.now()
    
    if period == "day":
        since = now - timedelta(days=1)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        typer.echo("Invalid period. Choose from: day, week, month")
        raise typer.Exit()

    filtered = [e for e in entries if datetime.fromisoformat(e["timestamp"]) > since and e["metric"] == metric_name]
    if not filtered:
        typer.echo("No data found for that metric and period.")
        return

    render_trend_chart(metric_name, filtered)
