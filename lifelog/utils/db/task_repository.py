from dataclasses import asdict
import logging
from typing import Any, Dict, List, Optional
import uuid
from lifelog.config.config_manager import is_host_server
from lifelog.utils.db.models import Task, TaskStatus, get_task_fields, task_from_row
from lifelog.utils.db import get_connection, normalize_for_db
from lifelog.utils.db import add_record, update_record
from lifelog.utils.shared_utils import parse_datetime_robust, ensure_utc_for_storage, convert_local_input_to_utc, now_utc
from datetime import datetime
import sqlite3

from lifelog.utils.db import (
    is_direct_db_mode,
    should_sync,
    queue_sync_operation,
)
from lifelog.utils.db import fetch_from_server, get_last_synced, process_sync_queue, set_last_synced, safe_execute, safe_query
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
    if not should_sync():
        return

    # push local changes
    process_sync_queue()

    # pull remote deltas
    last_ts = get_last_synced("tasks")
    params: Dict[str, Any] = {"since": last_ts} if last_ts else {}
    remote_list = fetch_from_server("tasks", params=params) or []
    for remote in remote_list:
        upsert_local_task(remote)

    # bump last‐sync
    set_last_synced("tasks", datetime.now().isoformat())


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
        with get_connection() as conn_tmp:
            # row_factory is set in get_connection, so rows come as sqlite3.Row
            cursor_tmp = conn_tmp.cursor()
            cursor_tmp.execute(
                "SELECT uid FROM tasks WHERE id = ?", (task_id,))
            row_tmp = cursor_tmp.fetchone()
        # 3) If we found a UID, fetch that specific task from host
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


def add_task(task_data: Any) -> Task:
    """Insert a new Task, ensuring Enums are stored as strings, and set created, updated_at, deleted."""
    data = asdict(task_data) if hasattr(
        task_data, "__dataclass_fields__") else task_data.copy()
    fields = get_task_fields()
    for f in fields:
        data.setdefault(f, None)

    # Defaults and type normalization
    now = datetime.now()
    if data.get("created") is None:
        data["created"] = now
    # Handle status Enum: if None, default; if string, convert to Enum then back to value; if Enum, get value
    status_val = data.get("status")
    if status_val is None:
        data["status"] = TaskStatus.BACKLOG.value
    else:
        # Convert possible values to TaskStatus enum then to string
        try:
            # If already Enum
            if isinstance(status_val, TaskStatus):
                data["status"] = status_val.value
            else:
                # If string, validate Enum
                data["status"] = TaskStatus(status_val).value
        except Exception:
            logger.warning(
                f"Invalid status '{status_val}', defaulting to BACKLOG")
            data["status"] = TaskStatus.BACKLOG.value
    # Importance
    if data.get("importance") is None:
        data["importance"] = 1
    # Priority
    if data.get("priority") is None:
        try:
            data["priority"] = calculate_priority(data)
        except Exception as e:
            logger.error("Priority calc failed: %s", e, exc_info=True)
            data["priority"] = 1.0

    # Convert datetime field strings to UTC datetime objects for storage
    datetime_fields = ["created", "due", "start", "end", "recur_base"]
    for field in datetime_fields:
        if field in data and data[field] is not None and isinstance(data[field], str):
            try:
                # Convert user input (local time) to UTC for database storage
                data[field] = convert_local_input_to_utc(data[field])
            except Exception:
                logger.warning(
                    f"Invalid datetime string for {field}: {data[field]}")
                data[field] = None

    # Set created timestamp to UTC if not provided
    if not data.get("created"):
        data["created"] = now_utc()

    # UID
    if not data.get("uid"):
        data["uid"] = str(uuid.uuid4())
    # New fields: updated_at and deleted
    data["updated_at"] = now
    data["deleted"] = 0

    # Before writing, convert Enum or datetime into normalized DB values
    # normalize_for_db should handle datetime -> ISO; ensure status is string
    db_data = normalize_for_db(data)

    if is_direct_db_mode():
        new_id = add_record("tasks", db_data, fields)
        return get_task_by_id(new_id)
    else:
        add_record("tasks", db_data, fields)
        queue_sync_operation("tasks", "create", db_data)
        process_sync_queue()
        rows = safe_query(
            "SELECT * FROM tasks WHERE uid = ?", (db_data["uid"],)
        )
        return task_from_row(dict(rows[0]))


def update_task(task_id: int, updates: Dict[str, Any]) -> None:
    """Update local task; queue sync with correct updated_at and Enum serialization."""
    # Handle status Enum
    if 'status' in updates:
        status_val = updates['status']
        try:
            if isinstance(status_val, TaskStatus):
                updates['status'] = status_val.value
            else:
                updates['status'] = TaskStatus(status_val).value
        except Exception:
            logger.warning(
                f"Invalid status '{status_val}' in update, ignoring field")
            updates.pop('status', None)

    # Convert datetime field strings to UTC datetime objects for storage
    datetime_fields = ["created", "due", "start", "end", "recur_base"]
    for field in datetime_fields:
        if field in updates and updates[field] is not None and isinstance(updates[field], str):
            try:
                # Convert user input (local time) to UTC for database storage
                updates[field] = convert_local_input_to_utc(updates[field])
            except Exception:
                logger.warning(
                    f"Invalid datetime string for {field}: {updates[field]}")
                updates.pop(field, None)

    # Set updated_at to UTC
    updates['updated_at'] = now_utc()
    db_updates = normalize_for_db(updates)

    if is_direct_db_mode():
        update_record("tasks", task_id, db_updates)
        return

    # client mode
    update_record("tasks", task_id, db_updates)
    # fetch full row to queue
    rows = safe_query("SELECT * FROM tasks WHERE id = ?", (task_id,))
    full = dict(rows[0]) if rows else {"id": task_id, **db_updates}
    # Ensure status in full is string
    if 'status' in full:
        try:
            full['status'] = TaskStatus(full['status']).value
        except Exception:
            full['status'] = TaskStatus.BACKLOG.value
    queue_sync_operation("tasks", "update", full)
    process_sync_queue()


def delete_task(task_id):
    """Delete local and queue soft-delete with updated_at."""
    if is_direct_db_mode():
        safe_execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    else:
        rows = safe_query("SELECT uid FROM tasks WHERE id = ?", (task_id,))
        uid_val = rows[0]["uid"] if rows and rows[0]["uid"] else None
        # Soft-delete locally: set deleted=1 and updated_at
        now_iso = datetime.now().isoformat()
        safe_execute(
            "UPDATE tasks SET deleted = 1, updated_at = ? WHERE id = ?", (now_iso, task_id))
        payload = {"uid": uid_val, "deleted": True,
                   "updated_at": now_iso} if uid_val else {"id": task_id}
        queue_sync_operation("tasks", "delete", payload)
        process_sync_queue()


def upsert_local_task(data: dict) -> None:
    """Upsert from server payload: parse status string to TaskStatus? Keep as string in DB."""
    uid_val = data.get("uid")
    if not uid_val:
        return
    # Prepare db_data: ensure status is string
    if 'status' in data:
        try:
            data['status'] = TaskStatus(data['status']).value
        except Exception:
            data['status'] = TaskStatus.BACKLOG.value
    # Set updated_at and deleted if present; ensure datetime
    if 'updated_at' in data and isinstance(data['updated_at'], str):
        try:
            # leave as ISO string; normalize_for_db will handle
            pass
        except Exception:
            data.pop('updated_at', None)
    if 'deleted' in data:
        data['deleted'] = 1 if data.get('deleted') else 0
    rows = safe_query("SELECT id FROM tasks WHERE uid = ?", (uid_val,))
    fields = get_task_fields()
    db_data = normalize_for_db(data)
    if rows:
        update_record("tasks", rows[0]["id"], {
                      k: db_data[k] for k in fields if k in db_data})
    else:
        add_record("tasks", db_data, fields)


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
    """Host-only: update fields, serialize Enum, set updated_at."""
    if not is_host_server():
        return
    if 'status' in updates:
        try:
            val = updates['status']
            if isinstance(val, TaskStatus):
                updates['status'] = val.value
            else:
                updates['status'] = TaskStatus(val).value
        except Exception:
            updates.pop('status', None)
    # Set updated_at
    updates['updated_at'] = datetime.now()
    db_updates = normalize_for_db(updates)
    cols = ", ".join(f"{k}=?" for k in db_updates)
    params = tuple(db_updates.values()) + (uid,)
    safe_execute(f"UPDATE tasks SET {cols} WHERE uid = ?", params)


def delete_task_by_uid(uid: str) -> None:
    """Host-only: soft-delete by UID."""
    if not is_host_server():
        return
    now_iso = datetime.now().isoformat()
    safe_execute(
        "UPDATE tasks SET deleted = 1, updated_at = ? WHERE uid = ?", (now_iso, uid))
