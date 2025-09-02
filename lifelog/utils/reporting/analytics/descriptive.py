# lifelog.utils/reporting/analytics/descriptive.py
'''
Lifelog CLI - Descriptive Analytics Module
This module provides functionality to generate descriptive analytics reports for user data.
It includes functions to compute mean, median, and standard deviation of tracker data, time usage statistics, and task summaries.
It is designed to help users understand their data patterns and make informed decisions based on their usage statistics.
It also provides options to export the reports in JSON or CSV format.   
'''

from lifelog.utils.shared_utils import parse_date_string, now_utc
from lifelog.utils.db.time_repository import get_all_time_logs
from lifelog.utils.db.track_repository import get_all_trackers, get_entries_for_tracker
from datetime import datetime, timedelta
import statistics
import json
import csv
from rich.console import Console
from lifelog.utils.reporting.analytics.report_utils import render_radar_chart
console = Console()

console = Console()


def report_descriptive(since: str = "30d", export: str = None):
    """
    📊 Descriptive analytics: overview of tracker stats, time usage, and tasks.
    """
    cutoff = parse_date_string(since, future=False)
    console.print(
        f"[bold]Descriptive Analytics:[/] since {cutoff.date().isoformat()}\n")

    # 1. Tracker statistics (mean, median, stdev)
    trackers = get_all_trackers()
    stats = {}
    for tracker in trackers:
        entries = get_entries_for_tracker(tracker.id)
        # Only use values after cutoff
        values = [e.value for e in entries if e.timestamp >= cutoff]
        if not values:
            continue
        stats[tracker.title] = {
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        }
    console.print("[blue]Tracker Statistics (Mean):[/blue]")
    render_radar_chart({k: v["mean"] for k, v in stats.items()})

    # 2. Time usage stats (SQL-based)
    time_logs = get_all_time_logs(since=cutoff)
    total_time = sum(
        t.duration_minutes for t in time_logs if t.start >= cutoff)
    days = (now_utc().date() - cutoff.date()).days + 1
    avg_time = round(total_time / days, 2) if days > 0 else 0.0
    console.print(
        f"\n[blue]Time Usage:[/] total {total_time} min — avg/day {avg_time} min")

    # 3. Task summary — replace with your new SQL summary logic if needed

    # 4. Export if requested
    if export:
        _export(stats, total_time, avg_time, export)


def _export(stats: dict, total_time: float, avg_time: float, filepath: str):
    ext = filepath.split('.')[-1].lower()
    out = {
        'tracker_stats': stats,
        'total_time_min': total_time,
        'avg_time_per_day_min': avg_time,
    }
    if ext == 'json':
        with open(filepath, 'w') as f:
            json.dump(out, f, indent=2)
    elif ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['category', 'stat', 'value'])
            for tr, s in stats.items():
                for stat, val in s.items():
                    writer.writerow([tr, stat, val])
            writer.writerow(['time', 'total', total_time])
            writer.writerow(['time', 'avg_per_day', avg_time])
    console.print(f"[green]Exported descriptive report to {filepath}[/green]")
