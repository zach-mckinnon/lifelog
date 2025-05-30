from datetime import datetime
from typing import Optional
from lifelog.commands.utils.db.database_manager import get_connection, update_record
from lifelog.commands.utils.db.models import TimeLog, time_log_from_row


def get_active_time_entry() -> Optional[TimeLog]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1""")
    row = cur.fetchone()
    conn.close()
    return time_log_from_row(dict(row)) if row else None


def get_all_time_logs(since: datetime = None) -> list:
    conn = get_connection()
    cur = conn.cursor()
    if since:
        cur.execute(
            """SELECT * FROM time_history WHERE start >= ? ORDER BY start DESC""", (since.isoformat(),))
    else:
        cur.execute("""SELECT * FROM time_history ORDER BY start DESC""")
    rows = cur.fetchall()
    conn.close()
    return [time_log_from_row(dict(row)) for row in rows]


def start_time_entry(log: TimeLog):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO time_history (title, start, task_id, category, project, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (log.title, log.start.isoformat(), log.task_id, log.category, log.project, log.tags, log.notes))
    conn.commit()
    conn.close()


def stop_active_time_entry(end_time: datetime, tags: str = None, notes: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1")
    entry = cur.fetchone()
    if not entry:
        conn.close()
        return None
    duration = (
        end_time - datetime.fromisoformat(entry["start"])).total_seconds() / 60
    cur.execute("""
        UPDATE time_history
        SET end = ?, duration_minutes = ?, tags = ?, notes = ?
        WHERE id = ?
    """, (end_time.isoformat(), round(duration, 2), tags, notes, entry["id"]))
    conn.commit()
    conn.close()
    # Optionally return the updated entry as a TimeLog
    entry = dict(entry)
    entry["end"] = end_time.isoformat()
    entry["duration_minutes"] = round(duration, 2)
    entry["tags"] = tags
    entry["notes"] = notes
    from .models import time_log_from_row
    return time_log_from_row(entry)


def update_time_entry(entry_id: int, **updates):
    """
    Update one or more fields on a time log entry by ID.
    Example: update_time_entry(42, distracted_minutes=12.5, notes="New note")
    """
    # Convert datetime fields to isoformat if needed
    for k, v in updates.items():
        if isinstance(v, datetime):
            updates[k] = v.isoformat()
    update_record("time_history", entry_id, updates)


def add_distracted_minutes_to_active(minutes: float):
    active = get_active_time_entry()
    if not active:
        return None
    new_distracted = (active.distracted_minutes or 0) + minutes
    update_time_entry(active.id, distracted_minutes=new_distracted)
    return new_distracted
