# lifelog.utils/reporting/analytics/prescriptive.py
'''
Lifelog CLI - Prescriptive Reporting Module
This module provides functionality to generate prescriptive reports based on user data patterns.
It includes functions to analyze user data, identify patterns, and provide actionable insights for self-improvement.
It is designed to help users make informed decisions about their habits and lifestyle choices based on their data.
'''

import csv
import json
from rich.console import Console
from lifelog.utils.reporting.analytics.report_utils import render_pie_chart
from lifelog.utils.db.track_repository import get_all_trackers, get_entries_for_tracker
console = Console()


def report_prescriptive(scenario: str = "sleep_food", export: str = None):
    """
    💡 Prescriptive actions based on user data patterns.
    """

    console.print(f"[bold]Prescriptive Report:[/] scenario={scenario}\n")

    # 1. Load daily averages for trackers
    trackers = get_all_trackers()
    tracker_daily = {}
    for tracker in trackers:
        entries = get_entries_for_tracker(tracker.id)
        day_map = {}
        for e in entries:
            date_str = e.timestamp.date().isoformat()
            day_map.setdefault(date_str, []).append(e.value)
        tracker_daily[tracker.title] = {
            d: sum(vals)/len(vals) for d, vals in day_map.items()}

    if scenario == "sleep_food":
        sleep_map = tracker_daily.get("sleepq", {})
        mood_map = tracker_daily.get("mood", {})
        good_days = [d for d, v in sleep_map.items() if v >= 6]
        poor_days = [d for d, v in sleep_map.items() if v < 6]

        def avg(map_data, days):
            vals = [map_data[d] for d in days if d in map_data]
            return sum(vals) / len(vals) if vals else 0
        good_mood = avg(mood_map, good_days)
        poor_mood = avg(mood_map, poor_days)
        console.print(
            f"[green]Avg mood on good-sleep days (≥6):[/green] {good_mood:.1f}")
        console.print(
            f"[yellow]Avg mood on poor-sleep days (<6):[/yellow] {poor_mood:.1f}\n")
        console.print(
            "👉 Aim for ≥6 quality sleep hours to improve your average mood.")
        series = {"Good Sleep": good_mood, "Poor Sleep": poor_mood}
        render_pie_chart(series)
        results = {
            "scenario": scenario,
            "good_sleep_avg_mood": good_mood,
            "poor_sleep_avg_mood": poor_mood
        }
    else:
        console.print(
            f"[red]Unknown scenario '{scenario}'. Available: sleep_food[/red]")
        return

    if export:
        _export_prescriptive(results, export)


def _export_prescriptive(data: dict, filepath: str):
    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['key', 'value'])
            for k, v in data.items():
                writer.writerow([k, v])
    elif ext == 'json':
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    console.print(f"[green]Exported prescriptive report to {filepath}[/green]")
