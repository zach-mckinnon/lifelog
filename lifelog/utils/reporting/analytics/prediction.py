# lifelog.utils/reporting/analytics/prediction.py
'''
Lifelog Prediction Module
This module provides functionality to forecast future trends for various trackers based on historical data.
It includes functions to generate forecasts using different models (simple or regression) and visualize the results.
It is designed to help users understand potential future trends in their data, enabling better planning and decision-making.
'''

from datetime import datetime, timedelta
import csv
import json
import numpy as np
from rich.console import Console
from lifelog.utils.reporting.analytics.report_utils import render_line_chart
from lifelog.utils.db.track_repository import get_all_trackers, get_entries_for_tracker

console = Console()


def report_prediction(model: str = "simple", days: int = 7, export: str = None):
    """
    📈 Forecast future trends for each tracker.
    """

    trackers = get_all_trackers()
    for tracker in trackers:
        entries = get_entries_for_tracker(tracker.id)
        if not entries:
            continue
        # Build daily avg map for this tracker
        day_map = {}
        for e in entries:
            date_str = e.timestamp.date().isoformat()
            day_map.setdefault(date_str, []).append(e.value)
        day_avg = {d: sum(vals)/len(vals) for d, vals in day_map.items()}
        dates = sorted(day_avg.keys())
        values = [day_avg[d] for d in dates]
        console.print(f"\n[bold]Forecast for '{tracker.title}':[/bold]")

        if not dates:
            console.print("[yellow]No data available to forecast.[/yellow]")
            continue

        # Forecast logic
        if model == "simple":
            last_val = values[-1]
            forecast_vals = [last_val] * days
        elif model == "regression":
            x = np.arange(len(values))
            coeffs = np.polyfit(x, values, 1)
            slope, intercept = coeffs[0], coeffs[1]
            future_x = np.arange(len(values), len(values) + days)
            forecast_vals = (intercept + slope * future_x).tolist()
        else:
            console.print(f"[red]Unknown model '{model}'. Skipping.\n")
            continue

        # Future dates
        last_date = datetime.fromisoformat(dates[-1]).date()
        future_dates = [(last_date + timedelta(days=i + 1)).isoformat()
                        for i in range(days)]

        # Render chart
        combined_dates = dates + future_dates
        combined_vals = values + forecast_vals
        render_line_chart(combined_dates, combined_vals,
                          label="Value & Forecast")

        # Export if requested
        if export:
            _export_forecast(tracker.title, dates, values,
                             future_dates, forecast_vals, export)


def _export_forecast(
    tracker: str,
    hist_dates: list[str],
    hist_vals: list[float],
    fut_dates: list[str],
    fut_vals: list[float],
    filepath: str,
):
    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['tracker', 'date', 'type', 'value'])
            for d, v in zip(hist_dates, hist_vals):
                writer.writerow([tracker, d, 'history', v])
            for d, v in zip(fut_dates, fut_vals):
                writer.writerow([tracker, d, 'forecast', v])
    elif ext == 'json':
        out = {
            'tracker': tracker,
            'history': dict(zip(hist_dates, hist_vals)),
            'forecast': dict(zip(fut_dates, fut_vals)),
        }
        with open(filepath, 'w') as f:
            json.dump(out, f, indent=2)
    console.print(
        f"[green]Exported forecast for '{tracker}' to {filepath}[/green]")
