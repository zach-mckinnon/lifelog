from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
import json
import csv

from lifelog.utils.db import track_repository, time_repository
from lifelog.utils.reporting.insight_engine import generate_insights


def get_tracker_summary(since_days: int = 7) -> pd.DataFrame:
    """
    Build a DataFrame of tracker entries in the last `since_days` days.
    """
    since = datetime.now() - timedelta(days=since_days)
    # List[Tracker]
    trackers = track_repository.get_all_trackers_with_entries()
    rows = []

    for tracker in trackers:
        for entry in tracker.entries or []:  # TrackerEntry instance
            timestamp = entry.timestamp
           # Normalize to ISO string for comparison and output
            if isinstance(timestamp, datetime):
                ts_iso = timestamp.isoformat()
            else:
                ts_iso = timestamp
            if datetime.fromisoformat(ts_iso) >= since:
                rows.append({
                    "tracker": tracker.title,
                    "timestamp": ts_iso,
                    "value": entry.value
                })
    return pd.DataFrame(rows)


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

    for entry in track_repository.get_entries_for_tracker(tracker.id):
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
