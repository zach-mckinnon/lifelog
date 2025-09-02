# lifelog.utils/reporting/analytics/diagnostics.py
'''
Lifelog CLI - Diagnostic Reporting Module
This module provides functionality to generate diagnostic reports based on user data patterns.
It includes functions to analyze user data, identify low wellness days, and compute correlations between different metrics.
It is designed to help users identify patterns and relationships in their data, providing valuable feedback for self-improvement and habit tracking.'''

from datetime import datetime
import json
import csv
from rich.console import Console
# Insight engine functionality removed
from lifelog.config.config_manager import get_time_file
from lifelog.utils.reporting.analytics.report_utils import render_line_chart, render_calendar_heatmap
from lifelog.utils.db.track_repository import get_all_trackers, get_entries_for_tracker
from lifelog.utils.shared_utils import parse_date_string
from lifelog.utils.reporting.insight_engine import compute_correlation

console = Console()


def report_diagnostics(since: str = "30d", export: str = None):
    """
    🔍 Diagnostic report: identify days of low wellness and potential root causes.
    """
    cutoff = parse_date_string(since, future=False)
    console.print(
        f"[bold]Diagnostic Report:[/] since {cutoff.date().isoformat()}\n")

    # 1. Load all trackers' daily averages
    trackers = get_all_trackers()
    # Build daily averages per tracker
    tracker_daily = {}
    for tracker in trackers:
        entries = get_entries_for_tracker(tracker.id)
        # Map by date string
        day_map = {}
        for e in entries:
            if e.timestamp >= cutoff:
                date_str = e.timestamp.date().isoformat()
                day_map.setdefault(date_str, []).append(e.value)
        # Average per day
        tracker_daily[tracker.title] = {
            d: sum(vals)/len(vals) for d, vals in day_map.items()}

    # 2. Identify low-mood days
    mood_map = tracker_daily.get('mood', {})
    low_days = [d for d, v in mood_map.items(
    ) if v <= 3 and datetime.fromisoformat(d) >= cutoff]
    console.print(f"[red]Low mood days:[/] {len(low_days)} days since {since}")

    # 3. Sleep/Energy on those days
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

    # 6. Weekly heatmap (time logs)
    from lifelog.utils.db.time_repository import get_all_time_logs
    time_logs = get_all_time_logs(since=cutoff)
    weekday_totals = {}
    for t in time_logs:
        ts = t.start
        if ts >= cutoff:
            wd = ts.strftime('%a')
            weekday_totals[wd] = weekday_totals.get(wd, 0) + t.duration_minutes
    render_calendar_heatmap(weekday_totals)

    # 7. Export if requested
    if export:
        _export_diagnostics(low_days, corr_sleep,
                            corr_energy, weekday_totals, export)


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
