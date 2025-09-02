# lifelog/utils/core_utils.py
"""
Core utility functions that don't depend on database or models.
This module exists to break circular import dependencies.
"""

from datetime import datetime, timezone
from dateutil import tz


def now_utc() -> datetime:
    """
    Return current time as UTC-aware datetime.
    """
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC-aware datetime.
    - If dt is naïve, interpret it as UTC.
    - If dt is aware, convert from its tzinfo to UTC.
    Returns a datetime with tzinfo=datetime.timezone.utc.
    """
    if dt.tzinfo is None:
        # Interpret naïve dt as UTC for simplicity
        dt = dt.replace(tzinfo=timezone.utc)
    # Convert to UTC
    return dt.astimezone(timezone.utc)


def get_user_timezone():
    """
    Return a tzinfo object for the user's timezone.
    Falls back to system local timezone since we can't import config here.
    """
    try:
        return tz.tzlocal()
    except Exception:
        return timezone.utc


def calculate_priority(task) -> float:
    """
    Calculate task priority based on importance and urgency.
    Works with both Task instances and dict representations.
    """
    if isinstance(task, dict):
        importance = task.get("importance", 3)
        due_val = task.get("due", None)
    else:  # assume Task instance
        importance = getattr(task, "importance", 3) or 3
        due_val = getattr(task, "due", None)
    
    urgency = 0.0
    if due_val:
        # due_val is likely a datetime already (repository parsed ISO into datetime)
        if isinstance(due_val, str):
            try:
                due_date = datetime.fromisoformat(due_val)
            except Exception:
                due_date = None
        else:
            due_date = due_val
        if due_date:
            days_left = (due_date - now_utc()).days
            urgency = max(0.0, 1.0 - days_left / 10)
    return (importance * 0.6) + (urgency * 0.4)