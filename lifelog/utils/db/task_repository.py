from dataclasses import asdict
from typing import Any, Dict
import uuid
from lifelog.config.config_manager import is_host_server
from lifelog.utils.db.models import Task, get_task_fields, task_from_row
from lifelog.utils.db.database_manager import get_connection, add_record, update_record
from datetime import datetime
import sqlite3

from lifelog.utils.db import (
    is_direct_db_mode,
    should_sync,
    queue_sync_operation,
)
from lifelog.utils.db.db_helper import fetch_from_server, get_last_synced, process_sync_queue, set_last_synced


def get_all_tasks():
    """
    Return all tasks from the local SQLite database, ordered by due ASC.
    If we're in client mode (should_sync()), first pull remote tasks down and upsert them locally.
    """
    # 1. If client‐mode, pull remote tasks before returning
    if should_sync():
        # Fetch all remote tasks (no filters)
        _pull_changed_tasks_from_host()

    # 2. Now run the local SELECT
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY due ASC")
    rows = cursor.fetchall()
    conn.close()

    return [task_from_row(dict(row)) for row in rows]


def _pull_changed_tasks_from_host() -> None:
    """
    If we are in client mode, fetch only tasks changed on the host since last sync,
    upsert them locally, and update sync_state.
    """
    if not should_sync():
        return

    # 1) Push any pending local changes first
    process_sync_queue()

    # 2) Ask the host for only the tasks changed since `last_synced_at`
    last_ts = get_last_synced("tasks")  # e.g. "2025-06-03T22:15:00"
    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    remote_list = fetch_from_server("tasks", params=params)
    for remote in remote_list:
        upsert_local_task(remote)

    # 3) Update our last‐sync time to right now (UTC ISO format)
    now_iso = datetime.utcnow().isoformat()
    set_last_synced("tasks", now_iso)


def get_task_by_id(task_id):
    """
    Return a single task by numeric ID from the local DB.
    If we're in client mode (should_sync()), first push any queued changes,
    then pull the latest version of this task from the host (by its UID),
    upsert it locally, and finally read from SQLite.
    """
    # 1) If client mode, push queued changes first
    if should_sync():
        _pull_changed_tasks_from_host()

        # 2) Look up the task’s UID locally, so we can fetch the latest from host
        conn_tmp = get_connection()
        conn_tmp.row_factory = sqlite3.Row
        cursor_tmp = conn_tmp.cursor()
        cursor_tmp.execute("SELECT uid FROM tasks WHERE id = ?", (task_id,))
        row_tmp = cursor_tmp.fetchone()
        conn_tmp.close()

        # 3) If we found a UID, fetch exactly that one task from host
        if row_tmp and row_tmp["uid"]:
            uid_val = row_tmp["uid"]
            remote_list = fetch_from_server("tasks", params={"uid": uid_val})
            if remote_list:
                upsert_local_task(remote_list[0])

    # 4) Now read the (possibly updated) task from local SQLite
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task_row = cursor.fetchone()
    conn.close()

    return task_from_row(dict(task_row)) if task_row else None


def add_task(task_data):
    """
    Accepts dict or Task object, handles dataclass conversion, and fills in defaults.
    """
    if isinstance(task_data, Task):
        data = asdict(task_data)
    else:
        data = task_data
    print(f"Adding task with data: {data}")

    data.setdefault("created", datetime.now().isoformat())

    # Set defaults for missing fields
    if "importance" not in data:
        data.setdefault("importance", 1)

    if "priority" not in data:
        data.setdefault("priority", 1)

    if not is_direct_db_mode():
        data.setdefault("uid", str(uuid.uuid4()))

    # Add only fields present in the model/schema
    fields = get_task_fields()

    if is_direct_db_mode():
        add_record("tasks", data, fields)
        # after insertion, fetch last rowid if you need to build the Task
        conn = get_connection()
        last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return get_task_by_id(last_id)

    # 5. If client, queue and immediately try syncing
    else:
        # client mode: same insert logic
        add_record("tasks", data, fields)
        queue_sync_operation("tasks", "create", data)
        process_sync_queue()
        # Here, to return a Task, we must look it up locally by uid:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE uid = ?",
                           (data["uid"],)).fetchone()
        conn.close()
        return task_from_row(dict(row))


def update_task(task_id, updates):
    """
    Update fields of a task by numeric ID.
      • In host/direct-DB mode: do UPDATE … WHERE id = ?.
      • In client mode:
         a) UPDATE local row by ID.
         b) Fetch that row’s UID.
         c) Build a FULL payload from the local row (dict(row)).
         d) Queue an “update” by UID.
         e) Attempt to process_sync_queue().
    """
    if is_direct_db_mode():
        # Host mode: direct update
        update_record("tasks", task_id, updates)

    else:
        # Client mode:
        # a) Update local
        update_record("tasks", task_id, updates)

        # b) Fetch entire local row to get the UID (and all other fields)
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()

        # c) Build full_payload
        if row and row["uid"]:
            full_payload = dict(row)
        else:
            # Fallback: if the UID is missing, queue numeric‐ID based update
            full_payload = {"id": task_id, **updates}

        # d) Queue update
        queue_sync_operation("tasks", "update", full_payload)

        # e) Attempt to drain queue right away
        process_sync_queue()


def delete_task(task_id):
    """
    Delete a task by numeric ID.
      • Host/direct-DB: DELETE WHERE id = ?. 
      • Client mode:
         a) SELECT uid from local row.
         b) DELETE locally by ID.
         c) Queue a “delete” by UID (or numeric ID if UID missing).
         d) Attempt to drain queue.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if is_direct_db_mode():
        # Host mode: delete directly by ID
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()

    else:
        # Client mode:
        # a) Fetch UID
        cursor.execute("SELECT uid FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        # b) Delete locally
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()

        # c) Queue delete by UID or fallback to numeric ID
        if row and row["uid"]:
            queue_sync_operation("tasks", "delete", {"uid": row["uid"]})
        else:
            queue_sync_operation("tasks", "delete", {"id": task_id})

        # d) Attempt to drain queue now
        process_sync_queue()


def upsert_local_task(data: dict):
    """
    Given a dict “data” from fetch_from_server(…), insert or update local row by UID:
      • If UID exists locally → UPDATE local row.
      • Else → INSERT new record locally.
    This should only run in “client” code paths (pulling remote data). 
    """
    uid_val = data.get("uid")
    if not uid_val:
        return  # cannot upsert without a UID

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1) Check if that UID already exists locally
    cursor.execute("SELECT id FROM tasks WHERE uid = ?", (uid_val,))
    existing = cursor.fetchone()

    fields = get_task_fields()  # includes "uid"
    if existing:
        # 2a) Build updates-only dict from data
        local_id = existing["id"]
        updates = {k: data[k] for k in fields if k in data}
        update_record("tasks", local_id, updates)
    else:
        # 2b) Insert a brand-new record locally
        add_record("tasks", data, fields)

    conn.close()


def query_tasks(
    title_contains=None,
    uid=None,
    category=None,
    project=None,
    importance=None,
    due_contains=None,
    status=None,
    show_completed=False,
    sort="priority",
    **kwargs
):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # If host‐mode OR client‐mode (i.e. direct DB or should_sync), we always work off local SQLite.
    if is_direct_db_mode() or should_sync():
        # —––––––––––— Step A: In client mode, “pull” new/updated rows from the host first —––––––––––—
        if should_sync():
            _pull_changed_tasks_from_host()

        # —––––––––––— Step B: Now run the local SELECT exactly as before —––––––––––—
        query = "SELECT * FROM tasks WHERE 1=1"
        sql_params = []

        if uid is not None:
            query += " AND uid = ?"
            sql_params.append(uid)

        if not show_completed:
            query += " AND (status IS NULL OR status != 'done')"

        if title_contains:
            query += " AND title LIKE ?"
            sql_params.append(f"%{title_contains}%")

        if category:
            query += " AND category = ?"
            sql_params.append(category)

        if project:
            query += " AND project = ?"
            sql_params.append(project)

        if importance is not None:
            query += " AND importance = ?"
            sql_params.append(importance)

        if due_contains:
            query += " AND due LIKE ?"
            sql_params.append(f"%{due_contains}%")

        if status:
            query += " AND status = ?"
            sql_params.append(status)

        sort_field = {
            "priority": "priority DESC",
            "due": "due ASC",
            "created": "created ASC",
            "id": "id ASC",
            "status": "status ASC"
        }.get(sort, "priority DESC")

        query += f" ORDER BY {sort_field}"
        cursor.execute(query, sql_params)
        rows = cursor.fetchall()
        conn.close()
        return [task_from_row(dict(row)) for row in rows]

    else:
        # Pure “remote‐only” fallback
        params = {
            "title_contains": title_contains,
            "category": category,
            "project": project,
            "importance": importance,
            "due_contains": due_contains,
            "status": status,
            "show_completed": "true" if show_completed else "false",
            "sort": sort
        }
        params.update(kwargs)
        params = {k: v for k, v in params.items() if v is not None}

        return fetch_from_server("tasks", params=params)


def update_task_by_uid(uid: str, updates: dict):
    """
    UPDATE a task’s fields using its global UID.
    This function should only be called when running in host/server mode.
    """
    if not is_host_server():
        # Deny if someone invokes this on a non-host instance
        return

    fields = []
    values = []
    for key, val in updates.items():
        fields.append(f"{key} = ?")
        values.append(val)
    values.append(uid)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE tasks SET {', '.join(fields)} WHERE uid = ?",
        tuple(values)
    )
    conn.commit()
    conn.close()


def delete_task_by_uid(uid: str):
    """
    DELETE a task by its global UID.
    This function should only be called when running in host/server mode.
    """
    if not is_host_server():
        # Deny if someone invokes this on a non-host instance
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE uid = ?", (uid,))
    conn.commit()
    conn.close()
