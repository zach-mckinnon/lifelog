from datetime import datetime
from .database_manager import get_connection
import sqlite3


def get_active_time_entry():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
      SELECT * FROM time_history
      WHERE end IS NULL
      ORDER BY start DESC
      LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def start_time_entry(title, task_id=None, start_time=None, category=None, project=None, tags=None, notes=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO time_history (title, start, task_id, category, project, tags, notes)
      VALUES (?,    ?,     ?,       ?,        ?,       ?,    ?)
    """, (title, start_time, task_id, category, project, tags, notes))
    conn.commit()
    conn.close()


def stop_active_time_entry(end_time, tags=None, notes=None):
    conn = get_connection()
    cur = conn.cursor()
    # fetch the running one…
    cur.execute(
        "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1")
    entry = cur.fetchone()
    if not entry:
        conn.close()
        return None

    duration = (datetime.fromisoformat(end_time)
                - datetime.fromisoformat(entry["start"])).total_seconds() / 60

    cur.execute("""
      UPDATE time_history
         SET end = ?, duration_minutes = ?, tags = ?, notes = ?
       WHERE id = ?
    """, (end_time, round(duration, 2), tags, notes, entry["id"]))
    conn.commit()
    conn.close()
    return dict(entry)


def add_time_log(title, start, end, task=True, category=None, project=None, tags=None, notes=None, task_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO time_history (title, start, end, duration_minutes, task, category, project, tags, notes, task_id)
        VALUES (?, ?, ?, CAST((JULIANDAY(?) - JULIANDAY(?)) * 24 * 60 AS FLOAT), ?, ?, ?, ?, ?, ?)
    """, (
        title,
        start,
        end,
        end,
        start,
        1 if task else 0,
        category,
        project,
        tags,
        notes,
        task_id
    ))
    conn.commit()
    conn.close()


def get_all_time_logs(since: datetime = None):
    conn = get_connection()
    cur = conn.cursor()
    if since:
        cur.execute("""
            SELECT * FROM time_history
            WHERE start >= ?
            ORDER BY start DESC
        """, (since.isoformat(),))
    else:
        cur.execute("""
            SELECT * FROM time_history
            ORDER BY start DESC
        """)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]
