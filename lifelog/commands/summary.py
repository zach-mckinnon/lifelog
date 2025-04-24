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
TIME_FILE = Path.home() / ".lifelog_time_tracking.json"
HABIT_FILE = Path.home() / ".lifelog_habits.json"


def load_entries():
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return []


def load_time_log():
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            return json.load(f).get("history", [])
    return []


def load_habit_log():
    if HABIT_FILE.exists():
        with open(HABIT_FILE, "r") as f:
            return json.load(f).get("log", [])
    return []


def render_trend_chart(metric_name, entries):
    daily_values = defaultdict(list)
    for entry in entries:
        if entry.get("metric") == metric_name:
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


@app.command()
def time(period: str = typer.Option("week", help="Time range: day, week, month")):
    """
    Show time tracking totals by category.
    """
    entries = load_time_log()
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

    totals = defaultdict(float)
    for entry in entries:
        ts = datetime.fromisoformat(entry["start"])
        if ts > since:
            totals[entry["category"]] += entry["duration_minutes"]

    for cat, total in totals.items():
        typer.echo(f"🕒 {cat}: {round(total, 2)} minutes")


@app.command()
def habits(period: str = typer.Option("week", help="Time range: day, week, month")):
    """
    Show number of completions per habit.
    """
    logs = load_habit_log()
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

    counts = defaultdict(int)
    for entry in logs:
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts > since:
            counts[entry["name"]] += 1

    for name, count in counts.items():
        typer.echo(f"✅ {name}: {count} times")


@app.command()
def daily():
    """
    Show a summary report of today's metric, time tracking, and habit completions.
    """
    now = datetime.now()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # metric
    entries = [e for e in load_entries() if datetime.fromisoformat(e["timestamp"]) >= since]
    metric_data = defaultdict(list)
    for e in entries:
        try:
            metric_data[e["metric"]].append(float(e["value"]))
        except:
            continue

    typer.echo("\n📊 metric (Today)")
    if metric_data:
        for name, values in metric_data.items():
            typer.echo(f"- {name}: {round(statistics.mean(values), 2)}")
    else:
        typer.echo("No metric data logged today.")

    # Time
    time_entries = [e for e in load_time_log() if datetime.fromisoformat(e["start"]) >= since]
    time_totals = defaultdict(float)
    for e in time_entries:
        time_totals[e["category"]] += e["duration_minutes"]

    typer.echo("\n🕒 Time Tracking (Today)")
    if time_totals:
        for cat, total in time_totals.items():
            typer.echo(f"- {cat}: {round(total, 2)} minutes")
    else:
        typer.echo("No time tracked today.")

    # Habits
    habits = [h for h in load_habit_log() if datetime.fromisoformat(h["timestamp"]) >= since]
    habit_counts = defaultdict(int)
    for h in habits:
        habit_counts[h["name"]] += 1

    typer.echo("\n✅ Habits Completed (Today)")
    if habit_counts:
        for name, count in habit_counts.items():
            typer.echo(f"- {name}: {count} times")
    else:
        typer.echo("No habits completed today.")
