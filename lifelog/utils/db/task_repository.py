from dataclasses import asdict
import logging
from typing import Any, Dict, List, Optional
import uuid
from lifelog.config.config_manager import is_host_server
from lifelog.utils.db.models import Task, TaskStatus, get_task_fields, task_from_row
from lifelog.utils.db.database_manager import get_connection, add_record, update_record
from datetime import datetime
import sqlite3

from lifelog.utils.db import (
    is_direct_db_mode,
    should_sync,
    queue_sync_operation,
)
from lifelog.utils.db.db_helper import fetch_from_server, get_last_synced, process_sync_queue, set_last_synced, safe_execute, safe_query
from lifelog.utils.shared_utils import calculate_priority
logger = logging.getLogger(__name__)


def get_all_tasks() -> List[Task]:
    """
    Return all tasks from the local SQLite database, ordered by due ASC.
    If we're in client mode (should_sync()), first pull remote tasks down and upsert them locally.
    """
    # 1. If client‐mode, pull remote tasks before returning
    if should_sync():
        # Fetch all remote tasks (no filters)
        _pull_changed_tasks_from_host()

    rows = safe_query("SELECT * FROM tasks ORDER BY due ASC")
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
    rows = safe_query("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not rows:
        return None
    return task_from_row(dict(rows[0]))


def add_task(task_data) -> Task:
    """
    Accept dict or Task object; fill in defaults only if missing:
      - created: now if missing
      - status: 'backlog' if missing
      - importance: DEFAULT_IMPORTANCE (e.g. 1) if missing
      - priority: calculate_priority(data) if missing
      - uid: auto-generate if missing
    Then INSERT into tasks table and return the created Task object.
    """
    # 1) Convert dataclass to dict or copy dict
    if hasattr(task_data, "__dataclass_fields__"):
        data = asdict(task_data)
    else:
        data = task_data.copy()

    # 2) Ensure all known fields exist in data (set to None if completely absent)
    fields = get_task_fields()
    for f in fields:
        data.setdefault(f, None)

    # 3) Defaults only when missing (None)
    # created timestamp
    if data.get("created") is None:
        data.id = datetime.now().isoformat()

    # status default
    status_val = data.get("status")
    if status_val is not None:
        try:
            data["status"] = TaskStatus(status_val)
        except ValueError:
            raise ValueError(f"Invalid status: {status_val}")
    else:
        data["status"] = TaskStatus.BACKLOG

    # importance default: only if missing
    if data.get("importance") is None:
        # You may define a module-level constant DEFAULT_IMPORTANCE = 1
        data.importance = 1

    # priority default: only if missing; calculate via calculate_priority()
    if data.get("priority") is None:
        # calculate_priority expects a dict-like with at least "importance" and possibly "due"
        try:
            data["priority"] = calculate_priority(data)
        except Exception as e:
            # In case calculation fails, fallback to a safe default, e.g. 1.0
            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to calculate priority for new task: {e}", exc_info=True)
            data["priority"] = 1.0

    if 'due' in data and data['due'] is not None:
        data['due'] = datetime.fromisoformat(data['due'])

    # 4) UID: auto-generate if missing
    if not data.get("uid"):
        data["uid"] = str(uuid.uuid4())

    if is_direct_db_mode():
        new_id = add_record("tasks", data, fields)
        return get_task_by_id(new_id)
    else:
        add_record("tasks", data, fields)
        queue_sync_operation("tasks", "create", data)
        process_sync_queue()
        rows = safe_query("SELECT * FROM tasks WHERE uid = ?", (data["uid"],))
        return task_from_row(dict(rows[0]))


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

        # fetch full row to get UID
        rows = safe_query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        full_payload = dict(rows[0]) if rows else {"id": task_id, **updates}

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
    if is_direct_db_mode():
        safe_execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    else:
        # fetch UID
        rows = safe_query("SELECT uid FROM tasks WHERE id = ?", (task_id,))
        uid_val = rows[0]["uid"] if rows and rows[0]["uid"] else None

        # delete locally
        safe_execute("DELETE FROM tasks WHERE id = ?", (task_id,))

        # queue
        payload = {"uid": uid_val} if uid_val else {"id": task_id}
        queue_sync_operation("tasks", "delete", payload)
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
        return

    # does it exist?
    rows = safe_query("SELECT id FROM tasks WHERE uid = ?", (uid_val,))
    fields = get_task_fields()

    if rows:
        local_id = rows[0]["id"]
        updates = {k: data[k] for k in fields if k in data}
        update_record("tasks", local_id, updates)
    else:
        add_record("tasks", data, fields)


def query_tasks(
    title_contains: Optional[str] = None,
    uid: Optional[str] = None,
    category: Optional[str] = None,
    project: Optional[str] = None,
    importance: Optional[int] = None,
    due_contains: Optional[str] = None,
    status: Optional[str] = None,
    show_completed: bool = False,
    sort: str = "priority",
    **kwargs
) -> List[Task]:
    """
    Flexible query against local tasks, with optional remote pull in client mode.
    """
    if should_sync():
        _pull_changed_tasks_from_host()

    if is_direct_db_mode() or should_sync():
        query = "SELECT * FROM tasks WHERE 1=1"
        params: List[Any] = []

        if uid:
            query += " AND uid = ?"
            params.append(uid)
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
        if not show_completed and status is None:
            query += " AND (status IS NULL OR status != 'done')"

        sort_map = {
            "priority": "priority DESC",
            "due":      "due ASC",
            "created":  "created ASC",
            "id":       "id ASC",
            "status":   "status ASC",
        }
        query += f" ORDER BY {sort_map.get(sort, 'priority DESC')}"

        rows = safe_query(query, tuple(params))
        return [task_from_row(dict(r)) for r in rows]

    # pure-remote fallback
    params = {k: v for k, v in {
        "title_contains": title_contains,
        "category":       category,
        "project":        project,
        "importance":     importance,
        "due_contains":   due_contains,
        "status":         status,
        "sort":           sort,
        **kwargs,
    }.items() if v is not None}

    return fetch_from_server("tasks", params=params)


def update_task_by_uid(uid: str, updates: Dict[str, Any]) -> None:
    """
    Host-only update by UID.
    """
    if not is_host_server():
        return

    cols = ", ".join(f"{k}=?" for k in updates)
    params = tuple(updates.values()) + (uid,)
    safe_execute(f"UPDATE tasks SET {cols} WHERE uid = ?", params)


def delete_task_by_uid(uid: str) -> None:
    """
    Host-only delete by UID.
    """
    if not is_host_server():
        return

    safe_execute("DELETE FROM tasks WHERE uid = ?", (uid,))
