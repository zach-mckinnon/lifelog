from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import pandas as pd

from lifelog.utils.db import track_repository, time_repository, task_repository
from lifelog.utils.reporting.insight_engine import generate_insights
from lifelog.utils.shared_utils import now_utc
import logging

logger = logging.getLogger(__name__)


def get_tracker_summary(since_days: int = 7, fallback_local: bool = True) -> pd.DataFrame:
    """Get tracker data summary with automatic fallback to local data."""
    since = now_utc() - timedelta(days=since_days)

    try:
        # Try to get data with sync first
        trackers = track_repository.get_all_trackers_with_entries()
    except Exception as e:
        logger.error(
            "get_tracker_summary: failed to load trackers: %s", e, exc_info=True)
        if fallback_local:
            try:
                # Fallback to local-only data
                from lifelog.utils.db.db_helper import safe_query
                tracker_rows = safe_query(
                    "SELECT * FROM trackers WHERE deleted = 0", ())
                trackers = []
                for row in tracker_rows:
                    tracker_dict = dict(row)
                    entries = track_repository.get_entries_for_tracker(
                        tracker_dict['id'])
                    tracker_dict['entries'] = entries
                    trackers.append(tracker_dict)
            except Exception as e2:
                logger.error(
                    "get_tracker_summary: local fallback failed: %s", e2, exc_info=True)
                return pd.DataFrame()
        else:
            return pd.DataFrame()

    if not trackers:
        return pd.DataFrame()

    rows = []
    for tracker in trackers:
        tracker_id = tracker.get('id') if isinstance(
            tracker, dict) else getattr(tracker, 'id', None)
        tracker_title = tracker.get('title') if isinstance(
            tracker, dict) else getattr(tracker, 'title', 'Unknown')
        tracker_category = tracker.get('category') if isinstance(
            tracker, dict) else getattr(tracker, 'category', None)

        entries = tracker.get('entries', []) if isinstance(
            tracker, dict) else getattr(tracker, 'entries', [])

        for entry in entries:
            try:
                # Handle both TrackerEntry objects and dicts
                if hasattr(entry, 'timestamp'):
                    ts = entry.timestamp
                    value = entry.value
                    notes = getattr(entry, 'notes', None)
                else:
                    ts = entry.get('timestamp')
                    value = entry.get('value')
                    notes = entry.get('notes')

                # Parse timestamp
                if isinstance(ts, str):
                    ts_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                else:
                    ts_dt = ts

                if ts_dt >= since:
                    rows.append({
                        'tracker_id': tracker_id,
                        'tracker_title': tracker_title,
                        'category': tracker_category or 'uncategorized',
                        'timestamp': ts_dt,
                        'value': value,
                        'notes': notes,
                        'date': ts_dt.date()
                    })
            except Exception as e:
                logger.warning(
                    "get_tracker_summary: skipping invalid entry: %s", e)
                continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_time_summary(since_days: int = 7, fallback_local: bool = True) -> pd.DataFrame:
    """Get time tracking summary with automatic fallback to local data."""
    since = now_utc() - timedelta(days=since_days)

    try:
        logs = time_repository.get_all_time_logs(since)
    except Exception as e:
        logger.error(
            "get_time_summary: failed to load time logs: %s", e, exc_info=True)
        if fallback_local:
            try:
                # Fallback to local-only data
                from lifelog.utils.db.db_helper import safe_query
                query = """
                    SELECT * FROM time_history 
                    WHERE deleted = 0 AND start >= ? 
                    ORDER BY start DESC
                """
                rows = safe_query(query, (since.isoformat(),))
                logs = [dict(row) for row in rows]
            except Exception as e2:
                logger.error(
                    "get_time_summary: local fallback failed: %s", e2, exc_info=True)
                return pd.DataFrame()
        else:
            return pd.DataFrame()

    if not logs:
        return pd.DataFrame()

    # Ensure we have the right data structure
    rows = []
    for log in logs:
        try:
            if hasattr(log, '__dict__'):
                log_dict = log.__dict__
            else:
                log_dict = log

            start_time = log_dict.get('start')
            if isinstance(start_time, str):
                start_dt = datetime.fromisoformat(
                    start_time.replace('Z', '+00:00'))
            else:
                start_dt = start_time

            if start_dt >= since:
                rows.append({
                    'category': log_dict.get('category', 'uncategorized'),
                    'title': log_dict.get('title', 'Unknown'),
                    'duration_minutes': log_dict.get('duration_minutes', 0),
                    'start': start_dt,
                    'date': start_dt.date()
                })
        except Exception as e:
            logger.warning(
                "get_time_summary: skipping invalid log entry: %s", e)
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.groupby('category', dropna=False)['duration_minutes'].sum().reset_index()


def get_daily_tracker_averages(metric_name: str, since_days: int = 7) -> pd.DataFrame:
    from lifelog.utils.shared_utils import now_utc
    since = now_utc() - timedelta(days=since_days)
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
            # Handle TrackerEntry object vs dict
            if hasattr(entry, 'timestamp'):
                ts = datetime.fromisoformat(entry.timestamp)
                value = entry.value
            else:
                ts = datetime.fromisoformat(entry["timestamp"])
                value = entry["value"]

            if ts >= since:
                entries.append({"date": ts.date(), "value": value})
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
