from datetime import datetime, timedelta
import csv, json
from rich.console import Console
from lifelog.commands.utils.reporting.insight_engine import daily_averages, load_metric_data, load_time_data
import lifelog.config.config_manager as cf
from lifelog.commands.utils.tracker_utils import sum_entries
from lifelog.commands.utils.reporting.analytics.report_utils import render_line_chart, render_pie_chart
from rich.table import Table

console = Console()
cfg = cf.load_cron_config()

# Summary of tracker totals
def summary_metric(since: str = "7d", export: str = None):
    """
    ✏️  Summary of all trackers logged in the period.
    """
    cutoff = _parse_since(since)
    console.print(f"[bold]Trackers ({since} since {cutoff.date().isoformat()}):[/bold]")

    # Aggregate
    trackers = _load_trackers()
    data = {t: sum_entries(t, since) for t in trackers}

    # Coverage
    days = (datetime.now().date() - cutoff.date()).days + 1
    nonzero = sum(1 for v in data.values() if v > 0)
    coverage = (nonzero / days * 100) if days else 0
    console.print(f"[dim]Data coverage: {coverage:.0f}%[/dim]")

    # Chart
    series = _daily_series(data)
    dates, vals = zip(*sorted(series.items()))
    render_line_chart(dates, vals, label="Total per tracker")

    if export:
        _export(data, since, export)

# Summary of time tracking
def summary_time(since: str = "7d", export: str = None):
    """
    ⏱  Summary of time tracked per category.
    """
    from lifelog.config.config_manager import get_time_file
    cutoff = _parse_since(since)
    console.print(f"[bold]Time ({since} since {cutoff.date().isoformat()}):[/bold]")

    tf = get_time_file()
    time_data = json.load(open(tf, 'r'))
    history = time_data.get('history', [])
    recent = [h for h in history if datetime.fromisoformat(h['start']) >= cutoff]

    totals = {}
    for rec in recent:
        cat = rec.get('category', 'unknown')
        totals[cat] = totals.get(cat, 0) + rec.get('duration_minutes', 0)

    render_pie_chart(totals)
    if export:
        _export(totals, since, export)


def summary_daily(since: str = "7d", export: str = None):
    """
    📅  Daily summary: tasks completed, average mood, total time.
    """
    cutoff = _parse_since(since)
    today = datetime.now().date()
    
    # Load data
    time_data = load_time_data()
    metric_data = load_metric_data()
    daily_moods = daily_averages(metric_data).get("mood", {})  # {day: mood avg}

    # Placeholder for task completion (if available)
    # Assuming you have a method or file to load task completion logs per day
    try:
        with open("/path/to/your/task_log.json", "r") as f:
            task_logs = json.load(f)
    except:
        task_logs = []

    # Aggregate data per day
    days = (today - cutoff.date()).days + 1
    summary = []

    for i in range(days):
        day = (cutoff.date() + timedelta(days=i)).isoformat()

        # Count completed tasks
        tasks_done = sum(1 for t in task_logs if t.get("completed") and t.get("completed_date", "").startswith(day))

        # Average mood
        mood = daily_moods.get(day, "-")

        # Total minutes tracked
        minutes = sum(
            rec.get('duration_minutes', 0)
            for rec in time_data
            if datetime.fromisoformat(rec['start']).date().isoformat() == day
        )

        summary.append({
            "day": day,
            "tasks_done": tasks_done,
            "mood": mood if mood != "-" else "-",
            "minutes": round(minutes, 1)
        })

    # Render table
    table = Table(title=f"📅 Daily Summary (since {cutoff.date().isoformat()})", show_lines=True)
    table.add_column("Date", style="cyan")
    table.add_column("Tasks Done", style="green")
    table.add_column("Mood", style="magenta")
    table.add_column("Minutes Tracked", style="yellow")

    for row in summary:
        table.add_row(
            row["day"],
            str(row["tasks_done"]),
            str(row["mood"]),
            str(row["minutes"])
        )

    console.print(table)

    # Optional export
    if export:
        _export({r["day"]: r for r in summary}, since, export)

# Helpers

def _parse_since(s: str) -> datetime:
    now = datetime.now()
    unit = s[-1]
    try:
        amt = int(s[:-1])
    except ValueError:
        amt = int(s)
        unit = 'd'
    if unit == 'd': return now - timedelta(days=amt)
    if unit == 'w': return now - timedelta(weeks=amt)
    if unit == 'm': return now - timedelta(days=30*amt)
    return now - timedelta(days=amt)


def _load_trackers() -> list[str]:
    return list(cfg.get('tracker', {}).keys())


def _daily_series(data: dict[str, float]) -> dict[str, float]:
    days = len(data)
    start = datetime.now().date() - timedelta(days=days)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    return dict(zip(dates, data.values()))


def _export(data: dict, since: str, filepath: str):
    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['key','value'])
            for k,v in data.items(): w.writerow([k,v])
    else:
        json.dump({'since': since, 'data': data}, open(filepath, 'w'), indent=2)
    console.print(f"[green]Exported summary to {filepath}[/green]")
