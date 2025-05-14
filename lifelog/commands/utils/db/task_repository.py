# lifelog/commands/utils/db/task_repository.py

from .database_manager import get_connection
from datetime import datetime
import sqlite3
# --- Task CRUD ---


def get_all_tasks():
    conn = get_connection()
    conn.row_factory = sqlite3.Row  # ensures we get Row objects
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY due ASC")
    rows = cursor.fetchall()
    conn.close()
    # Convert to dict
    return [dict(row) for row in rows]


def get_task_by_id(task_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    conn.close()
    return dict(task) if task else None


def task_exists_with_title(title):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE title = ?", (title,))
    task = cursor.fetchone()
    conn.close()
    return task


def add_task(task_data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks 
        (title, project, category, importance, created, due, status, start, end, priority, recur_interval, recur_unit, recur_days_of_week, recur_base)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_data['title'],
        task_data.get('project'),
        task_data.get('category'),
        task_data.get('impt'),
        task_data.get('created', datetime.now().isoformat()),
        task_data.get('due'),
        task_data.get('status', 'backlog'),
        task_data.get('start'),
        task_data.get('end'),
        task_data.get('priority', 0),
        task_data.get('recur_interval'),
        task_data.get('recur_unit'),
        task_data.get('recur_days_of_week'),
        task_data.get('recur_base'),
    ))
    conn.commit()
    conn.close()


def update_task(task_id, updates):
    conn = get_connection()
    cursor = conn.cursor()
    fields = []
    values = []
    for key, value in updates.items():
        fields.append(f"{key} = ?")
        values.append(value)
    values.append(task_id)
    cursor.execute(
        f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

# --- Task Tracking (time logs for tasks) ---


def add_task_tracking(task_id, start, end, duration_minutes, tags=None, notes=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO task_tracking (task_id, start, end, duration_minutes, tags, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        start,
        end,
        duration_minutes,
        tags,
        notes
    ))
    conn.commit()
    conn.close()


def get_task_tracking(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM task_tracking WHERE task_id = ? ORDER BY start DESC", (task_id,))
    tracking = cursor.fetchall()
    conn.close()
    return tracking


def query_tasks(
    title_contains=None,
    category=None,
    project=None,
    importance=None,
    due_contains=None,
    status=None,
    show_completed=False,
    sort="priority"
):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM tasks WHERE 1=1"
    params = []

    if not show_completed:
        query += " AND (status IS NULL OR status != 'done')"

    if title_contains:
        query += " AND title LIKE ?"
        params.append(f"%{title_contains}%")

    if category:
        query += " AND category = ?"
        params.append(category)

    if project:
        query += " AND project = ?"
        params.append(project)

    if importance is not None:
        query += " AND importance = ?"
        params.append(importance)

    if due_contains:
        query += " AND due LIKE ?"
        params.append(f"%{due_contains}%")

    if status:
        query += " AND status = ?"
        params.append(status)

    # Sorting
    sort_field = {
        "priority": "priority DESC",
        "due": "due ASC",
        "created": "created ASC",
        "id": "id ASC",
        "status": "status ASC"
    }.get(sort, "priority DESC")

    query += f" ORDER BY {sort_field}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
