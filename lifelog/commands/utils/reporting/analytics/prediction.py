from datetime import datetime, timedelta
import csv, json
import numpy as np
from rich.console import Console
from lifelog.commands.utils.reporting.insight_engine import load_metric_data, daily_averages
from lifelog.commands.utils.reporting.analytics.report_utils import render_line_chart

console = Console()

def report_prediction(model: str = "simple", days: int = 7, export: str = None):
    """
    📈 Forecast future trends for each tracker.

    model: "simple" (flat last value) or "regression" (linear trend)
    days: number of days ahead to forecast
    export: optional CSV or JSON filepath to export results
    """
    # 1. Load daily averages for all trackers
    entries = load_metric_data()
    tracker_daily = daily_averages(entries)  # {tracker: {date: avg}}

    # 2. Process each tracker
    for tracker, day_map in tracker_daily.items():
        # Sort by date
        dates = sorted(day_map.keys())
        values = [day_map[d] for d in dates]
        console.print(f"\n[bold]Forecast for '{tracker}':[/bold]")

        if not dates:
            console.print("[yellow]No data available to forecast.[/yellow]")
            continue

        # 3. Generate forecast
        if model == "simple":
            last_val = values[-1]
            forecast_vals = [last_val] * days
        elif model == "regression":
            # Fit linear trend
            x = np.arange(len(values))
            coeffs = np.polyfit(x, values, 1)
            slope, intercept = coeffs[0], coeffs[1]
            future_x = np.arange(len(values), len(values) + days)
            forecast_vals = (intercept + slope * future_x).tolist()
        else:
            console.print(f"[red]Unknown model '{model}'. Skipping.\n")
            continue

        # 4. Build future dates
        last_date = datetime.fromisoformat(dates[-1]).date()
        future_dates = [(last_date + timedelta(days=i + 1)).isoformat() for i in range(days)]

        # 5. Render line chart combining history + forecast
        combined_dates = dates + future_dates
        combined_vals = values + forecast_vals
        render_line_chart(combined_dates, combined_vals, label="Value & Forecast")

        # 6. Export if requested
        if export:
            _export_forecast(
                tracker, dates, values, future_dates, forecast_vals, export
            )


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
    console.print(f"[green]Exported forecast for '{tracker}' to {filepath}[/green]")
