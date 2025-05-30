from dataclasses import asdict
from lifelog.commands.utils.db.models import Task, get_task_fields, task_from_row
from lifelog.commands.utils.db.database_manager import get_connection, add_record, update_record
from datetime import datetime
import sqlite3


def get_all_tasks():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY due ASC")
    rows = cursor.fetchall()
    conn.close()
    # Use dataclass model for validation/usage
    return [task_from_row(dict(row)) for row in rows]


def get_task_by_id(task_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    conn.close()
    return task_from_row(dict(task)) if task else None


def add_task(task_data):
    """
    Accepts dict or Task object, handles dataclass conversion, and fills in defaults.
    """
    if isinstance(task_data, Task):
        data = asdict(task_data)
    else:
        data = task_data
    # Set defaults for missing fields
    data.setdefault("created", datetime.now().isoformat())
    data.setdefault("importance", 1)
    data.setdefault("priority", 1)
    # Add only fields present in the model/schema
    fields = get_task_fields()
    add_record("tasks", data, fields)


def update_task(task_id, updates):
    """
    Accepts partial dict (only changed fields).
    """
    update_record("tasks", task_id, updates)


def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
