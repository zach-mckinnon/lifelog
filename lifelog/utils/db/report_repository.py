from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
import json
import csv

from lifelog.utils.db import track_repository, time_repository
from lifelog.utils.reporting.insight_engine import generate_insights


def get_tracker_summary(since_days: int = 7) -> pd.DataFrame:
    """Summarize all trackers with their total values since N days."""
    since = datetime.now() - timedelta(days=since_days)
    trackers = track_repository.get_all_trackers_with_entries()
    rows = []

    for tracker in trackers:
        for entry in tracker.get("entries", []):
            if datetime.fromisoformat(entry["timestamp"]) >= since:
                rows.append({
                    "tracker": tracker["title"],
                    "timestamp": entry["timestamp"],
                    "value": entry["value"]
                })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df.groupby('tracker')['value'].sum().reset_index()


def get_time_summary(since_days: int = 7) -> pd.DataFrame:
    """Summarize time logs by category in the given period."""
    since = datetime.now() - timedelta(days=since_days)
    logs = time_repository.get_all_time_logs(since)
    df = pd.DataFrame(logs)
    if df.empty:
        return df

    df['start'] = pd.to_datetime(df['start'])
    df = df[df['start'] >= since]

    return df.groupby('category')['duration_minutes'].sum().reset_index()


def get_daily_tracker_averages(metric_name: str, since_days: int = 7) -> pd.DataFrame:
    """Daily average values for a single tracker."""
    since = datetime.now() - timedelta(days=since_days)
    entries = []

    tracker = track_repository.get_tracker_by_title(metric_name)
    if not tracker:
        return pd.DataFrame()

    for entry in track_repository.get_entries_for_tracker(tracker["id"]):
        if datetime.fromisoformat(entry["timestamp"]) >= since:
            entries.append({
                "timestamp": entry["timestamp"],
                "value": entry["value"]
            })

    df = pd.DataFrame(entries)
    if df.empty:
        return df

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    return df.groupby('date')['value'].mean().reset_index()


def get_correlation_insights() -> List[Dict[str, Any]]:
    """Generate top correlations using the Insight Engine."""
    return generate_insights()


def export_data(df: pd.DataFrame, filepath: str):
    if df.empty:
        print("[yellow]⚠️ No data to export.[/yellow]")
        return

    ext = filepath.split('.')[-1].lower()
    if ext == 'csv':
        df.to_csv(filepath, index=False)
    else:
        df.to_json(filepath, orient='records', indent=2)
    print(f"[green]✅ Exported report to {filepath}[/green]")
