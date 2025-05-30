# lifelog/commands/utils/db/track_repository.py
from typing import Any, Dict, List
from lifelog.commands.utils.db.models import Tracker, TrackerEntry, goal_from_row
from lifelog.commands.utils.db.database_manager import get_connection
import json


def get_all_trackers():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers ORDER BY created DESC")
    rows = cur.fetchall()
    conn.close()
    return [Tracker(**dict(row)) for row in rows]


def get_tracker_by_id(tracker_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    row = cur.fetchone()
    conn.close()
    return Tracker(**dict(row)) if row else None


def add_tracker(title, type, category=None, created=None, goals=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trackers (title, type, category, created, goals)
        VALUES (?, ?, ?, ?, ?)
    """, (title, type, category, created, json.dumps(goals) if goals else None))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


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
    return [TrackerEntry(**dict(row)) for row in rows]


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
    return [Tracker(**dict(row)) for row in rows]


def add_goal(tracker_id: int, goal_data: Dict[str, Any]) -> None:
    """Add a goal to the database, associated with a tracker."""
    conn = get_connection()
    cursor = conn.cursor()
    # Construct the SQL query and parameters dynamically, handling optional fields
    fields = ["tracker_id", "title", "kind", "period"]
    values = [tracker_id, goal_data["title"],
              goal_data["kind"], goal_data["period"]]
    placeholders = ["?", "?", "?", "?"]

    for key, value in goal_data.items():
        if key not in ["title", "kind", "period"]:  # These are already handled
            fields.append(key)
            values.append(value)
            placeholders.append("?")

    query = f"INSERT INTO goals ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
    cursor.execute(query, values)
    conn.commit()
    conn.close()


def update_goal(goal_id: int, updates: dict):
    """
    Update any field(s) in a goal.
    """
    conn = get_connection()
    cur = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [goal_id]
    cur.execute(f"UPDATE goals SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_goal(goal_id: int):
    """
    Delete a goal by its ID.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()


def query_goals(**filters):
    """
    Query goals by arbitrary fields.
    Usage: query_goals(tracker_id=3, kind="sum")
    """
    conn = get_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM goals"
    if filters:
        where = " AND ".join([f"{k} = ?" for k in filters])
        sql += f" WHERE {where}"
        cur.execute(sql, tuple(filters.values()))
    else:
        cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    return [goal_from_row(row) for row in rows]

# For tracker


def validate_goal_fields(goal: dict):
    required = ["title", "kind", "period"]
    for k in required:
        if not goal.get(k):
            raise ValueError(f"Missing required field: {k}")

    kind = goal["kind"]
    if kind in ("sum", "count", "reduction", "duration"):
        if not isinstance(goal.get("amount", None), (int, float)):
            raise ValueError("Amount must be a number.")
    if kind == "range":
        if goal.get("min_amount") is None or goal.get("max_amount") is None:
            raise ValueError("Range goals need min_amount and max_amount.")
    # Extend for other types as needed


def get_tracker_by_id(tracker_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    row = cur.fetchone()
    conn.close()
    return Tracker(**row) if row else None

# For goals (use your goal_from_row helper)


def get_goals_for_tracker(tracker_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM goals WHERE tracker_id = ?", (tracker_id,))
    rows = cur.fetchall()
    conn.close()
    return [goal_from_row(row) for row in rows]


def get_all_trackers_with_goals() -> List[Dict[str, Any]]:
    trackers = get_all_trackers()
    for tracker in trackers:
        tracker["goals"] = get_goals_for_tracker(tracker["id"])
    return trackers


def get_all_trackers_with_entries() -> List[Dict[str, Any]]:
    trackers = get_all_trackers()
    for tracker in trackers:
        tracker["entries"] = get_entries_for_tracker(tracker["id"])
    return trackers
