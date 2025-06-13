from datetime import datetime, timedelta
from typing import Dict, Any, List

import pandas as pd

from lifelog.utils.db import track_repository, time_repository
from lifelog.utils.reporting.insight_engine import generate_insights
import logging

logger = logging.getLogger(__name__)


def get_tracker_summary(since_days: int = 7) -> pd.DataFrame:
    since = datetime.now() - timedelta(days=since_days)
    try:
        trackers = track_repository.get_all_trackers_with_entries()
    except Exception as e:
        logger.error(
            "get_tracker_summary: failed to load trackers: %s", e, exc_info=True)
        return pd.DataFrame()

    rows = []
    for tracker in trackers:
        for entry in tracker.entries or []:
            ts = entry.timestamp
            ts_iso = ts.isoformat() if isinstance(ts, datetime) else ts
            try:
                if datetime.fromisoformat(ts_iso) >= since:
                    rows.append({
                        "tracker": tracker.title,
                        "timestamp": ts_iso,
                        "value": entry.value
                    })
            except Exception as e:
                logger.warning(
                    "get_tracker_summary: skipping invalid timestamp %r: %s", ts_iso, e)

    return pd.DataFrame(rows)


def get_time_summary(since_days: int = 7) -> pd.DataFrame:
    since = datetime.now() - timedelta(days=since_days)
    try:
        logs = time_repository.get_all_time_logs(since)
    except Exception as e:
        logger.error(
            "get_time_summary: failed to load time logs: %s", e, exc_info=True)
        return pd.DataFrame()

    df = pd.DataFrame(logs)
    if df.empty:
        return df

    df['start'] = pd.to_datetime(df['start'], errors='coerce')
    df = df[df['start'] >= since]
    return df.groupby('category', dropna=False)['duration_minutes'].sum().reset_index()


def get_daily_tracker_averages(metric_name: str, since_days: int = 7) -> pd.DataFrame:
    since = datetime.now() - timedelta(days=since_days)
    try:
        tracker = track_repository.get_tracker_by_title(metric_name)
    except Exception as e:
        logger.error("get_daily_tracker_averages: failed to load tracker %r: %s",
                     metric_name, e, exc_info=True)
        return pd.DataFrame()

    if not tracker:
        return pd.DataFrame()

    entries = []
    try:
        raw_entries = track_repository.get_entries_for_tracker(tracker.id)
    except Exception as e:
        logger.error("get_daily_tracker_averages: failed to load entries for %r: %s",
                     metric_name, e, exc_info=True)
        raw_entries = []

    for entry in raw_entries:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= since:
                entries.append({"date": ts.date(), "value": entry["value"]})
        except Exception as e:
            logger.warning(
                "get_daily_tracker_averages: skipping invalid entry %r: %s", entry, e)

    if not entries:
        return pd.DataFrame()

    df = pd.DataFrame(entries)
    return df.groupby('date')['value'].mean().reset_index()


def get_correlation_insights() -> List[Dict[str, Any]]:
    try:
        return generate_insights()
    except Exception as e:
        logger.error(
            "get_correlation_insights: insight engine failed: %s", e, exc_info=True)
        return []


def export_data(df: pd.DataFrame, filepath: str):
    if df.empty:
        print("[yellow]⚠️ No data to export.[/yellow]")
        return

    ext = filepath.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'csv':
            df.to_csv(filepath, index=False)
        else:
            df.to_json(filepath, orient='records', indent=2)
        print(f"[green]✅ Exported report to {filepath}[/green]")
    except Exception as e:
        logger.error("export_data: failed writing to %r: %s",
                     filepath, e, exc_info=True)
        print(f"[red]❌ Failed to export report: {e}[/red]")
