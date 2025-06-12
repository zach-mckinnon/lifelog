# lifelog.utils/reporting/time_reports.py
'''
Lifelog Time Reporting Module
This module provides functionality to generate various time-related reports based on the user's data.
It includes features for generating time trends, time distribution, and calendar heatmaps.
The module uses JSON files for data storage and integrates with the Rich library for visualization.
It is designed to enhance the user experience by providing visual representations of time data directly in the terminal.
'''

# Use your unified period parser
from lifelog.utils.shared_utils import parse_date_string
# Make sure this is the correct path
from lifelog.utils.db import time_repository
from datetime import datetime
import json
import csv
from rich.console import Console
from lifelog.utils.reporting.analytics.report_utils import (
    render_line_chart,
    render_pie_chart,
    render_calendar_heatmap
)

console = Console()


def report_time_trend(since: str = "7d", export: str = None):
    """
    📈 Plot time spent per day over the period.
    """
    cutoff = parse_date_string(since, future=False)
    console.print(
        f"[bold]Time Trend:[/] {since} since {cutoff.date().isoformat()}")

    # Fetch from SQL
    history = time_repository.get_all_time_logs(since=cutoff)

    # Aggregate per day
    day_totals = {}
    for rec in history:
        # rec could be a model or dict: support both for now
        start = getattr(rec, "start", rec.get("start"))
        dur = getattr(rec, "duration_minutes", rec.get("duration_minutes", 0))
        if start and isinstance(start, str):
            day = datetime.fromisoformat(start).date().isoformat()
        elif start:
            day = start.date().isoformat()
        else:
            continue
        day_totals[day] = day_totals.get(day, 0) + dur

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
    cutoff = parse_date_string(since, future=False)
    console.print(
        f"[bold]Time Distribution:[/] {since} since {cutoff.date().isoformat()}")

    history = time_repository.get_all_time_logs(since=cutoff)

    # Aggregate per category
    totals = {}
    for rec in history:
        cat = getattr(rec, "category", rec.get("category", "unknown"))
        dur = getattr(rec, "duration_minutes", rec.get("duration_minutes", 0))
        totals[cat] = totals.get(cat, 0) + dur

    render_pie_chart(totals)
    if export:
        _export(totals, since, export)


def report_time_calendar(since: str = "30d", export: str = None):
    """
    📅 Calendar heatmap of minutes per weekday.
    """
    cutoff = parse_date_string(since, future=False)
    console.print(
        f"[bold]Time Calendar:[/] {since} since {cutoff.date().isoformat()}")

    history = time_repository.get_all_time_logs(since=cutoff)

    # Aggregate per weekday
    weekday_totals = {}
    for rec in history:
        start = getattr(rec, "start", rec.get("start"))
        dur = getattr(rec, "duration_minutes", rec.get("duration_minutes", 0))
        if start and isinstance(start, str):
            wd = datetime.fromisoformat(start).strftime("%a")
        elif start:
            wd = start.strftime("%a")
        else:
            continue
        weekday_totals[wd] = weekday_totals.get(wd, 0) + dur

    render_calendar_heatmap(weekday_totals)
    if export:
        _export(weekday_totals, since, export)


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
