# lifelog/commands/utils/db/track_repository.py
from lifelog.commands.utils.db.database_manager import get_connection
import sqlite3
import json


def get_all_trackers():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers ORDER BY created DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_tracker_by_id(tracker_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_tracker(title, type, category=None, created=None, goals=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trackers (title, type, category, created, goals)
        VALUES (?, ?, ?, ?, ?)
    """, (title, type, category, created, json.dumps(goals) if goals else None))
    conn.commit()
    conn.close()


def add_tracker_entry(tracker_id, timestamp, value):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tracker_entries (tracker_id, timestamp, value)
        VALUES (?, ?, ?)
    """, (tracker_id, timestamp, value))
    conn.commit()
    conn.close()


def get_entries_for_tracker(tracker_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, value
        FROM tracker_entries
        WHERE tracker_id = ?
        ORDER BY timestamp ASC
    """, (tracker_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_tracker(tracker_id):
    conn = get_connection()
    cur = conn.cursor()
    # First, delete related entries
    cur.execute("DELETE FROM tracker_entries WHERE tracker_id = ?",
                (tracker_id,))
    # Then, delete the tracker itself
    cur.execute("DELETE FROM trackers WHERE id = ?", (tracker_id,))
    conn.commit()
    conn.close()


def query_trackers(title_contains=None, category=None):
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM trackers WHERE 1=1"
    params = []

    if title_contains:
        query += " AND title LIKE ?"
        params.append(f"%{title_contains}%")
    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY created DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_tracker_by_title(title):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers WHERE title = ?", (title,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_trackers_with_entries():
    """
    Fetch all trackers and their associated entries.
    Returns a list of trackers, each with an 'entries' key containing the list of entries.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Step 1: Fetch all trackers
    cur.execute("SELECT * FROM trackers ORDER BY created DESC")
    trackers = cur.fetchall()

    # Step 2: For each tracker, fetch its entries efficiently (using a join or a separate query per tracker)
    tracker_list = []
    for t in trackers:
        t_dict = dict(t)
        cur.execute("""
            SELECT id, timestamp, value
            FROM tracker_entries
            WHERE tracker_id = ?
            ORDER BY timestamp ASC
        """, (t["id"],))
        entries = cur.fetchall()
        t_dict["entries"] = [dict(e) for e in entries]
        tracker_list.append(t_dict)

    conn.close()
    return tracker_list
