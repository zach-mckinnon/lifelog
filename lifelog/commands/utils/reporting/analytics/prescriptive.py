from datetime import datetime
import csv, json
from rich.console import Console
from lifelog.commands.utils.reporting.insight_engine import load_metric_data, daily_averages
from lifelog.commands.utils.reporting.analytics.report_utils import render_pie_chart, render_line_chart

console = Console()

def report_prescriptive(scenario: str = "sleep_food", export: str = None):
    """
    💡 Prescriptive actions based on user data patterns.

    scenario: preset scenario key (e.g. "sleep_food").
    export: optional CSV or JSON filepath to export results.
    """
    console.print(f"[bold]Prescriptive Report:[/] scenario={scenario}\n")

    # 1. Load daily averages for trackers
    entries = load_metric_data()
    tracker_daily = daily_averages(entries)

    # 2. Handle scenarios
    if scenario == "sleep_food":
        # Compare average mood on good vs poor sleep days
        sleep_map = tracker_daily.get("sleepq", {})
        mood_map = tracker_daily.get("mood", {})
        # Define thresholds
        good_days = [d for d, v in sleep_map.items() if v >= 6]
        poor_days = [d for d, v in sleep_map.items() if v < 6]

        # Compute mood averages
        def avg(map_data, days):
            vals = [map_data[d] for d in days if d in map_data]
            return sum(vals) / len(vals) if vals else 0

        good_mood = avg(mood_map, good_days)
        poor_mood = avg(mood_map, poor_days)

        console.print(f"[green]Avg mood on good-sleep days (≥6):[/green] {good_mood:.1f}")
        console.print(f"[yellow]Avg mood on poor-sleep days (<6):[/yellow] {poor_mood:.1f}\n")
        console.print("👉 Aim for ≥6 quality sleep hours to improve your average mood.")

        # Visualize
        series = {"Good Sleep": good_mood, "Poor Sleep": poor_mood}
        render_pie_chart(series)

        results = {
            "scenario": scenario,
            "good_sleep_avg_mood": good_mood,
            "poor_sleep_avg_mood": poor_mood
        }
    else:
        console.print(f"[red]Unknown scenario '{scenario}'. Available: sleep_food[/red]")
        return

    # 3. Export if requested
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
