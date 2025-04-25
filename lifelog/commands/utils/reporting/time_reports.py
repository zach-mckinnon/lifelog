from datetime import datetime, timedelta
import json, csv
from rich.console import Console
from lifelog.config.config_manager import get_time_file
from lifelog.commands.utils.reporting.analytics.report_utils import (
    render_line_chart,
    render_pie_chart,
    render_calendar_heatmap
)

console = Console()


def report_time_trend(since: str = "7d", export: str = None):
    """
    📈 Plot time spent per day over the period.
    """
    cutoff = _parse_since(since)
    console.print(f"[bold]Time Trend:[/] {since} since {cutoff.date().isoformat()}")

    # Load and filter
    tf = get_time_file()
    data = json.load(open(tf, 'r'))
    history = data.get('history', [])
    filtered = [h for h in history if datetime.fromisoformat(h['start']) >= cutoff]

    # Aggregate per day
    day_totals: dict[str, float] = {}
    for rec in filtered:
        day = datetime.fromisoformat(rec['start']).date().isoformat()
        day_totals[day] = day_totals.get(day, 0) + rec.get('duration_minutes', 0)

    # Prepare series
    dates = sorted(day_totals.keys())
    values = [day_totals[d] for d in dates]

    render_line_chart(dates, values, label="Minutes")
    if export:
        _export(day_totals, since, export)


def report_time_distribution(since: str = "7d", export: str = None):
    """
    🥧 Show pie chart of total time per category.
    """
    cutoff = _parse_since(since)
    console.print(f"[bold]Time Distribution:[/] {since} since {cutoff.date().isoformat()}")

    tf = get_time_file()
    data = json.load(open(tf, 'r'))
    history = [h for h in data.get('history', []) if datetime.fromisoformat(h['start']) >= cutoff]

    # Aggregate per category
    totals: dict[str, float] = {}
    for rec in history:
        cat = rec.get('category', 'unknown')
        totals[cat] = totals.get(cat, 0) + rec.get('duration_minutes', 0)

    render_pie_chart(totals)
    if export:
        _export(totals, since, export)


def report_time_calendar(since: str = "30d", export: str = None):
    """
    📅 Calendar heatmap of minutes per weekday.
    """
    cutoff = _parse_since(since)
    console.print(f"[bold]Time Calendar:[/] {since} since {cutoff.date().isoformat()}")

    tf = get_time_file()
    data = json.load(open(tf, 'r'))
    history = [h for h in data.get('history', []) if datetime.fromisoformat(h['start']) >= cutoff]

    # Aggregate per weekday
    weekday_totals: dict[str, float] = {}
    for rec in history:
        wd = datetime.fromisoformat(rec['start']).strftime("%a")
        weekday_totals[wd] = weekday_totals.get(wd, 0) + rec.get('duration_minutes', 0)

    render_calendar_heatmap(weekday_totals)
    if export:
        _export(weekday_totals, since, export)


def _parse_since(s: str) -> datetime:
    now = datetime.now()
    unit = s[-1]
    try:
        amt = int(s[:-1])
    except ValueError:
        amt = int(s)
        unit = 'd'
    if unit == 'd':
        return now - timedelta(days=amt)
    if unit == 'w':
        return now - timedelta(weeks=amt)
    if unit == 'm':
        return now - timedelta(days=30 * amt)
    return now - timedelta(days=amt)


def _export(data: dict[str, float], since: str, filepath: str):
    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['key', 'value'])
            for k, v in data.items():
                writer.writerow([k, v])
    elif ext == 'json':
        with open(filepath, 'w') as f:
            json.dump({'since': since, 'data': data}, f, indent=2)
    console.print(f"[green]Exported report to {filepath}[/green]")
