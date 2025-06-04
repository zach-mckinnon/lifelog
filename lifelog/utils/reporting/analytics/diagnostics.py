# lifelog.utils/reporting/analytics/diagnostics.py
'''
Lifelog CLI - Diagnostic Reporting Module
This module provides functionality to generate diagnostic reports based on user data patterns.
It includes functions to analyze user data, identify low wellness days, and compute correlations between different metrics.
It is designed to help users identify patterns and relationships in their data, providing valuable feedback for self-improvement and habit tracking.'''

from datetime import datetime, timedelta
import json
import csv
from rich.console import Console
from lifelog.utils.reporting.insight_engine import load_metric_data, daily_averages, compute_correlation
from lifelog.config.config_manager import get_time_file
from lifelog.utils.reporting.analytics.report_utils import render_line_chart, render_calendar_heatmap

console = Console()


def report_diagnostics(since: str = "30d", export: str = None):
    """
    🔍 Diagnostic report: identify days of low wellness and potential root causes.

    since: time window (e.g. "30d").
    export: optional CSV/JSON filepath.
    """
    cutoff = _parse_since(since)
    console.print(
        f"[bold]Diagnostic Report:[/] since {cutoff.date().isoformat()}\n")

    # 1. Load data
    metric_entries = load_metric_data()
    tracker_daily = daily_averages(metric_entries)
    time_data = json.load(open(get_time_file(), 'r')).get('history', [])

    # 2. Identify low-mood days (< threshold)
    mood_map = tracker_daily.get('mood', {})
    low_days = [d for d, v in mood_map.items(
    ) if v <= 3 and datetime.fromisoformat(d) >= cutoff]
    console.print(f"[red]Low mood days:[/] {len(low_days)} days since {since}")

    # 3. Check sleep & energy correlations on those days
    sleep_map = tracker_daily.get('sleepq', {})
    energy_map = tracker_daily.get('energy', {})
    sleep_vals = [sleep_map.get(d, 0) for d in low_days]
    energy_vals = [energy_map.get(d, 0) for d in low_days]

    # 4. Compute correlations
    corr_sleep = compute_correlation(
        sleep_vals, [mood_map[d] for d in low_days])
    corr_energy = compute_correlation(
        energy_vals, [mood_map[d] for d in low_days])
    console.print(f"Correlation (sleep vs mood): {corr_sleep['pearson']}")
    console.print(f"Correlation (energy vs mood): {corr_energy['pearson']}\n")

    # 5. Visualize mood trend
    dates = sorted(mood_map.keys())[-len(low_days):]
    values = [mood_map[d] for d in dates]
    render_line_chart(dates, values, label="Mood Values")

    # 6. Weekly heatmap of activity (time tracked)
    # aggregate minutes per weekday
    weekday_totals = {}
    for rec in time_data:
        ts = datetime.fromisoformat(rec['start'])
        if ts >= cutoff:
            wd = ts.strftime('%a')
            weekday_totals[wd] = weekday_totals.get(
                wd, 0) + rec.get('duration_minutes', 0)
    render_calendar_heatmap(weekday_totals)

    # 7. Export if requested
    if export:
        _export_diagnostics(low_days, corr_sleep,
                            corr_energy, weekday_totals, export)


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
        return now - timedelta(days=30*amt)
    return now - timedelta(days=amt)


def _export_diagnostics(low_days, corr_sleep, corr_energy, weekday_totals, filepath):
    ext = filepath.split('.')[-1].lower()
    data = {
        'low_mood_days': low_days,
        'correlation_sleep_mood': corr_sleep,
        'correlation_energy_mood': corr_energy,
        'weekday_time_totals': weekday_totals
    }
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['metric', 'value'])
            writer.writerow(['low_mood_days_count', len(low_days)])
            writer.writerow(['corr_sleep_mood', corr_sleep['pearson']])
            writer.writerow(['corr_energy_mood', corr_energy['pearson']])
            for wd, v in weekday_totals.items():
                writer.writerow([wd, v])
    elif ext == 'json':
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    console.print(f"[green]Exported diagnostics report to {filepath}[/green]")
