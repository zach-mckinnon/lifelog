# lifelog/utils/db/track_repository.py

from typing import List
from datetime import datetime
import logging
import uuid
import sqlite3
from typing import Any, Dict, List, Optional

from lifelog.utils.db.database_manager import get_connection, add_record, update_record
from lifelog.utils.db.models import (
    Tracker,
    TrackerEntry,
    Goal,
    goal_from_row,
    get_tracker_fields,
    get_goal_fields,
    tracker_from_row,
    entry_from_row,
)
from lifelog.utils.db.db_helper import (
    get_last_synced,
    is_direct_db_mode,
    set_last_synced,
    should_sync,
    queue_sync_operation,
    process_sync_queue,
    fetch_from_server
)
logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────────────
# IMPORTANT: schema must include these columns:
#
#   TABLE trackers (
#     id   INTEGER PRIMARY KEY AUTOINCREMENT,
#     uid  TEXT UNIQUE,         -- new: global unique ID
#     title TEXT,
#     type  TEXT,
#     category TEXT,
#     created DATETIME,
#     tags     TEXT,
#     notes    TEXT
#   );
#
#   TABLE goals (
#     id          INTEGER PRIMARY KEY AUTOINCREMENT,
#     uid         TEXT UNIQUE,     -- new: global unique ID
#     tracker_id  INTEGER NOT NULL REFERENCES trackers(id) ON DELETE CASCADE,
#     title       TEXT NOT NULL,
#     kind        TEXT NOT NULL,
#     period      TEXT DEFAULT 'day',
#     min_amount  REAL,
#     max_amount  REAL,
#     amount      REAL,
#     unit        TEXT,
#     target_streak INTEGER,
#     target      REAL,
#     mode        TEXT,
#     old_behavior TEXT,
#     new_behavior TEXT
#   );
#
#   TABLE tracker_entries (
#     id          INTEGER PRIMARY KEY AUTOINCREMENT,
#     tracker_id  INTEGER NOT NULL REFERENCES trackers(id) ON DELETE CASCADE,
#     timestamp   DATETIME,
#     value       FLOAT
#   );
#
# Make sure you’ve run migrations so that `trackers.uid` and `goals.uid` exist.
# ───────────────────────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────────────────────
# Helpers to get core fields based on models/schema
# ───────────────────────────────────────────────────────────────────────────────


def _get_all_tracker_field_names() -> List[str]:
    """
    Return all Tracker table columns except 'id', to be used in INSERT/UPDATE:
    e.g., ['uid','title','type','category','created','tags','notes'].
    """
    return [f for f in get_tracker_fields() if f != "id"]


def _get_all_goal_field_names() -> List[str]:
    """
    Return all core 'goals' columns except 'id', based on get_goal_fields().
    Ensure your schema migrations keep get_goal_fields() aligned with actual table.
    """
    return [f for f in get_goal_fields() if f != "id"]

# ───────────────────────────────────────────────────────────────────────────────
# Sync pull helpers
# ───────────────────────────────────────────────────────────────────────────────


def _pull_changed_trackers_from_host() -> None:
    """
    If in client mode, fetch only trackers changed on the host since last sync,
    upsert them locally, and update sync_state.
    """
    if not should_sync():
        return

    # 1) Push any queued operations
    try:
        process_sync_queue()
    except Exception as e:
        logger.error(
            "_pull_changed_trackers_from_host: process_sync_queue failed: %s", e, exc_info=True)

    # 2) Read last sync timestamp for "trackers"
    try:
        last_ts = get_last_synced("trackers")
    except Exception as e:
        logger.error(
            "_pull_changed_trackers_from_host: get_last_synced failed: %s", e, exc_info=True)
        last_ts = None

    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) Fetch changed trackers from host
    try:
        remote_list = fetch_from_server("trackers", params=params) or []
    except Exception as e:
        logger.error(
            "_pull_changed_trackers_from_host: fetch_from_server failed: %s", e, exc_info=True)
        remote_list = []

    for remote in remote_list:
        try:
            upsert_local_tracker(remote)
        except Exception as e:
            logger.error(
                "_pull_changed_trackers_from_host: upsert_local_tracker failed for data=%r: %s", remote, e, exc_info=True)

    # 4) Update sync_state to now
    try:
        now_iso = datetime.now().isoformat()
        set_last_synced("trackers", now_iso)
    except Exception as e:
        logger.error(
            "_pull_changed_trackers_from_host: set_last_synced failed: %s", e, exc_info=True)


def _pull_changed_goals_from_host() -> None:
    """
    If in client mode, fetch only goals changed on the host since last sync,
    upsert them locally, and update sync_state.
    """
    if not should_sync():
        return

    # 1) Push queued changes
    try:
        process_sync_queue()
    except Exception as e:
        logger.error(
            "_pull_changed_goals_from_host: process_sync_queue failed: %s", e, exc_info=True)

    # 2) Read last sync timestamp
    try:
        last_ts = get_last_synced("goals")
    except Exception as e:
        logger.error(
            "_pull_changed_goals_from_host: get_last_synced failed: %s", e, exc_info=True)
        last_ts = None

    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) Fetch changed from host
    try:
        remote_list = fetch_from_server("goals", params=params) or []
    except Exception as e:
        logger.error(
            "_pull_changed_goals_from_host: fetch_from_server failed: %s", e, exc_info=True)
        remote_list = []

    for remote in remote_list:
        try:
            upsert_local_goal(remote)
        except Exception as e:
            logger.error(
                "_pull_changed_goals_from_host: upsert_local_goal failed for data=%r: %s", remote, e, exc_info=True)

    # 4) Update sync_state to now
    try:
        now_iso = datetime.now().isoformat()
        set_last_synced("goals", now_iso)
    except Exception as e:
        logger.error(
            "_pull_changed_goals_from_host: set_last_synced failed: %s", e, exc_info=True)


# ───────────────────────────────────────────────────────────────────────────────
# UPsert Helpers (used during “pull” from host in client mode)
# ───────────────────────────────────────────────────────────────────────────────

def upsert_local_tracker(data: Dict[str, Any]) -> None:
    """
    Given a dict from fetch_from_server("trackers"), insert or update local by uid.
    """
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning("upsert_local_tracker called without uid: %r", data)
        return

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM trackers WHERE uid = ?", (uid_val,))
        existing = cursor.fetchone()
        fields = _get_all_tracker_field_names()
        if existing:
            local_id = existing["id"]
            updates = {k: data[k] for k in fields if k in data}
            if updates:
                try:
                    update_record("trackers", local_id, updates)
                    logger.info("upsert_local_tracker: Updated tracker id=%d uid=%s fields=%s",
                                local_id, uid_val, list(updates.keys()))
                except Exception as e:
                    logger.error(
                        "upsert_local_tracker: Failed to update tracker id=%d: %s", local_id, e, exc_info=True)
        else:
            try:
                add_record("trackers", data, fields)
                logger.info(
                    "upsert_local_tracker: Inserted tracker uid=%s", uid_val)
            except Exception as e:
                logger.error(
                    "upsert_local_tracker: Failed to insert tracker uid=%s: %s", uid_val, e, exc_info=True)
    except Exception as e:
        logger.error(
            "upsert_local_tracker: Unexpected error for uid=%s: %s", uid_val, e, exc_info=True)
    finally:
        if conn:
            conn.close()


# ───────────────────────────────────────────────────────────────────────────────
# TRACKER CRUD (with host/client sync)
# ───────────────────────────────────────────────────────────────────────────────

def get_all_trackers(
    title_contains: Optional[str] = None,
    category: Optional[str] = None
) -> List[Tracker]:
    """
    Return all trackers from local SQLite (ordered by created DESC).
    In CLIENT mode, first push local changes & pull remote (in try/except), then SELECT.
    """
    if should_sync():
        try:
            _pull_changed_trackers_from_host()
        except Exception as e:
            logger.error(
                "get_all_trackers: error pulling from host: %s", e, exc_info=True)

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM trackers WHERE 1=1"
        sql_params: List[Any] = []

        if title_contains:
            query += " AND title LIKE ?"
            sql_params.append(f"%{title_contains}%")
        if category:
            query += " AND category = ?"
            sql_params.append(category)

        query += " ORDER BY created DESC"
        cursor.execute(query, tuple(sql_params))
        rows = cursor.fetchall()
        return [tracker_from_row(dict(r)) for r in rows]
    except Exception as e:
        logger.error("get_all_trackers: DB error: %s", e, exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_tracker_by_title(title: str) -> Optional[Tracker]:
    """
    Return one Tracker (as a dataclass) whose `title` exactly matches.
    """
    if should_sync():
        try:
            _pull_changed_trackers_from_host()
        except Exception as e:
            logger.error(
                "get_tracker_by_title: error pulling from host: %s", e, exc_info=True)

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM trackers WHERE title = ? LIMIT 1", (title,))
        row = cur.fetchone()
        return tracker_from_row(dict(row)) if row else None
    except Exception as e:
        logger.error("get_tracker_by_title: DB error: %s", e, exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_tracker_by_id(tracker_id: int) -> Optional[Tracker]:
    """
    Return one Tracker by numeric ID.
    """
    if should_sync():
        try:
            _pull_changed_trackers_from_host()
        except Exception as e:
            logger.error(
                "get_tracker_by_id: error pulling from host: %s", e, exc_info=True)

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
        row = cursor.fetchone()
        return tracker_from_row(dict(row)) if row else None
    except Exception as e:
        logger.error("get_tracker_by_id: DB error: %s", e, exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_tracker_by_uid(uid_val: str) -> Optional[Tracker]:
    """
    Return one Tracker by its global UID.
    """
    if should_sync():
        try:
            _pull_changed_trackers_from_host()
        except Exception as e:
            logger.error(
                "get_tracker_by_uid: error pulling from host: %s", e, exc_info=True)

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trackers WHERE uid = ?", (uid_val,))
        row = cursor.fetchone()
        return tracker_from_row(dict(row)) if row else None
    except Exception as e:
        logger.error("get_tracker_by_uid: DB error: %s", e, exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def add_tracker(tracker_data: Any) -> Tracker:
    """
    Insert a new Tracker. Validates minimal fields before insert.
    """
    data: Dict[str, Any]
    if isinstance(tracker_data, Tracker):
        data = tracker_data.to_dict().copy()
    else:
        data = tracker_data.copy()

    # Fill defaults
    data.setdefault("title", None)
    data.setdefault("type", None)
    data.setdefault("category", None)
    data.setdefault("created", datetime.utcnow().isoformat())
    data.setdefault("tags", None)
    data.setdefault("notes", None)
    # Minimal validation: title should not be empty
    if not data.get("title"):
        logger.error("add_tracker: Missing required field: title")
        raise ValueError("Tracker 'title' is required")

    if not data.get("uid"):
        data["uid"] = str(uuid.uuid4())

    fields = _get_all_tracker_field_names()
    try:
        add_record("trackers", data, fields)
        logger.info("add_tracker: Inserted tracker uid=%s title=%s",
                    data["uid"], data.get("title"))
    except Exception as e:
        logger.error("add_tracker: Failed to insert tracker %r: %s",
                     data, e, exc_info=True)
        raise

    # Re-fetch newly inserted
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trackers WHERE uid = ?", (data["uid"],))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(
                f"add_tracker: Inserted but cannot fetch tracker uid={data['uid']}")
        new_tracker = tracker_from_row(dict(row))
    except Exception as e:
        logger.error("add_tracker: Failed to re-fetch inserted tracker uid=%s: %s",
                     data["uid"], e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

    # Queue sync if client mode and syncing enabled
    if not is_direct_db_mode() and should_sync():
        try:
            queue_sync_operation("trackers", "create", data)
            process_sync_queue()
            logger.info(
                "add_tracker: Queued sync-create for tracker uid=%s", data["uid"])
        except Exception as e:
            logger.error("add_tracker: Sync-create failed for tracker uid=%s: %s",
                         data["uid"], e, exc_info=True)
    return new_tracker


def update_tracker(tracker_id: int, updates: Dict[str, Any]) -> Optional[Tracker]:
    """
    Update an existing tracker (partial fields).
    Returns updated Tracker or None if not found/error.
    """
    # Basic validation: if title in updates and empty, reject
    if "title" in updates and not updates["title"]:
        logger.error(
            "update_tracker: Missing required field 'title' in updates")
        raise ValueError("Tracker 'title' cannot be empty")

    # HOST/DIRECT mode
    if is_direct_db_mode():
        try:
            update_record("trackers", tracker_id, updates)
            return get_tracker_by_id(tracker_id)
        except Exception as e:
            logger.error(
                "update_tracker: Direct DB update failed for id=%d: %s", tracker_id, e, exc_info=True)
            raise

    # CLIENT mode
    try:
        update_record("trackers", tracker_id, updates)
    except Exception as e:
        logger.error("update_tracker: Local update failed for id=%d: %s",
                     tracker_id, e, exc_info=True)
        raise

    # Fetch local row
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
        row = cursor.fetchone()
        if not row:
            logger.error(
                "update_tracker: After update, tracker id=%d not found", tracker_id)
            return None
        full_payload = dict(row)
    except Exception as e:
        logger.error("update_tracker: Fetch after update failed for id=%d: %s",
                     tracker_id, e, exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

    # Remove numeric id before sending
    full_payload.pop("id", None)
    if not should_sync():
        return tracker_from_row(full_payload)

    # Queue sync
    try:
        queue_sync_operation("trackers", "update", full_payload)
        process_sync_queue()
        logger.info("update_tracker: Queued sync-update for tracker id=%d uid=%s",
                    tracker_id, full_payload.get("uid"))
    except Exception as e:
        logger.error("update_tracker: Sync-update failed for tracker id=%d uid=%s: %s",
                     tracker_id, full_payload.get("uid"), e, exc_info=True)

    return tracker_from_row(full_payload)


def delete_tracker(tracker_id: int) -> bool:
    """
    Delete a tracker (and its goals/entries via FOREIGN KEY CASCADE).
    Returns True on success, False if not found or error.
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT uid FROM trackers WHERE id = ?", (tracker_id,))
        row = cur.fetchone()
        if not row:
            logger.warning(
                "delete_tracker: tracker id=%d not found", tracker_id)
            return False
        uid_val = row["uid"]
        # Delete locally
        cur.execute("DELETE FROM trackers WHERE id = ?", (tracker_id,))
        conn.commit()
    except Exception as e:
        logger.error("delete_tracker: Failed to delete tracker id=%d: %s",
                     tracker_id, e, exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

    # Client sync
    if not is_direct_db_mode() and should_sync():
        payload = {"uid": uid_val} if uid_val else {"id": tracker_id}
        try:
            queue_sync_operation("trackers", "delete", payload)
            process_sync_queue()
            logger.info(
                "delete_tracker: Queued sync-delete for tracker id=%d uid=%s", tracker_id, uid_val)
        except Exception as e:
            logger.error("delete_tracker: Sync-delete failed for tracker id=%d uid=%s: %s",
                         tracker_id, uid_val, e, exc_info=True)
    return True


# ───────────────────────────────────────────────────────────────────────────────
# TRACKER-ENTRY CRUD (these are purely local; we do NOT sync entries themselves)
# ───────────────────────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────────────────────
# TRACKER-ENTRY CRUD (local-only); validate timestamp format
# ───────────────────────────────────────────────────────────────────────────────

def add_tracker_entry(tracker_id: int, timestamp: str, value: float) -> TrackerEntry:
    """
    Record a new entry for a given tracker. Local-only.
    `timestamp` should be ISO-format string or datetime. Validate format.
    """
    # Validate timestamp
    ts_str: str
    if isinstance(timestamp, datetime):
        ts_str = timestamp.isoformat()
    else:
        ts_str = timestamp
    try:
        # attempt parse
        datetime.fromisoformat(ts_str)
    except Exception:
        logger.error(
            "add_tracker_entry: Invalid ISO datetime string: %r", timestamp)
        raise ValueError(
            f"Invalid ISO datetime string for timestamp: {timestamp}")

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tracker_entries (tracker_id, timestamp, value) VALUES (?, ?, ?)",
            (tracker_id, ts_str, value)
        )
        conn.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM tracker_entries WHERE id = ?", (new_id,))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(
                f"add_tracker_entry: Inserted but cannot fetch id={new_id}")
        return entry_from_row(dict(row))
    except Exception as e:
        logger.error("add_tracker_entry: DB error for tracker_id=%d timestamp=%r value=%s: %s",
                     tracker_id, timestamp, value, e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def get_entries_for_tracker(tracker_id: int) -> List[TrackerEntry]:
    """
    Return all entries for a given tracker_id (local-only).
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tracker_entries WHERE tracker_id = ? ORDER BY timestamp ASC",
            (tracker_id,)
        )
        rows = cursor.fetchall()
        return [entry_from_row(dict(r)) for r in rows]
    except Exception as e:
        logger.error("get_entries_for_tracker: DB error for tracker_id=%d: %s",
                     tracker_id, e, exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


# ───────────────────────────────────────────────────────────────────────────────
# GOAL CRUD (with host/client sync)
# ───────────────────────────────────────────────────────────────────────────────

def get_goals_for_tracker(tracker_id: int) -> List[Goal]:
    """
    Return all goals for a given tracker (local-only, except that if in CLIENT mode,
    we will pull remote goals first).
    """
    if should_sync():
        _pull_changed_goals_from_host()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM goals WHERE tracker_id = ?", (tracker_id,))
    rows = cursor.fetchall()
    conn.close()
    return [goal_from_row(r) for r in rows]


# ───────────────────────────────────────────────────────────────────────────────
# Internally, get_goal_fields() returns all columns in the "goals" table:
#    ["id","uid","tracker_id","title","kind","period"]
# So _get_core_goal_fields() is simply:
# ───────────────────────────────────────────────────────────────────────────────

def _get_core_goal_fields() -> List[str]:
    return [f for f in get_goal_fields() if f != "id"]


# ───────────────────────────────────────────────────────────────────────────────
# ――― HELPER: INSERT or UPDATE the “detail” row for a given goal_id based on kind ―――
# ───────────────────────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────────────────────
# Detail helper functions, wrapped in try/except/finally
# ───────────────────────────────────────────────────────────────────────────────

def _insert_goal_detail(goal_id: int, data: Dict[str, Any]):
    """
    Insert into the correct subtype table depending on data['kind'].
    Raises ValueError if unsupported kind or missing fields.
    """
    kind = data.get("kind")
    if not kind:
        raise ValueError("Missing 'kind' in goal detail insertion")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        # For each kind, validate required fields first
        if kind == "sum":
            if "amount" not in data:
                raise ValueError("Missing 'amount' for sum goal")
            cur.execute(
                "INSERT INTO goal_sum (goal_id, amount, unit) VALUES (?, ?, ?)",
                (goal_id, data["amount"], data.get("unit"))
            )
        elif kind == "count":
            if "amount" not in data:
                raise ValueError("Missing 'amount' for count goal")
            cur.execute(
                "INSERT INTO goal_count (goal_id, amount, unit) VALUES (?, ?, ?)",
                (goal_id, data["amount"], data.get("unit"))
            )
        elif kind == "bool":
            cur.execute(
                "INSERT INTO goal_bool (goal_id) VALUES (?)",
                (goal_id,)
            )
        elif kind == "streak":
            if "target_streak" not in data:
                raise ValueError("Missing 'target_streak' for streak goal")
            cur.execute(
                "INSERT INTO goal_streak (goal_id, target_streak) VALUES (?, ?)",
                (goal_id, data["target_streak"])
            )
        elif kind == "duration":
            if "amount" not in data:
                raise ValueError("Missing 'amount' for duration goal")
            cur.execute(
                "INSERT INTO goal_duration (goal_id, amount, unit) VALUES (?, ?, ?)",
                (goal_id, data["amount"], data.get("unit", "minutes"))
            )
        elif kind == "milestone":
            if "target" not in data:
                raise ValueError("Missing 'target' for milestone goal")
            cur.execute(
                "INSERT INTO goal_milestone (goal_id, target, unit) VALUES (?, ?, ?)",
                (goal_id, data["target"], data.get("unit"))
            )
        elif kind == "reduction":
            if "amount" not in data:
                raise ValueError("Missing 'amount' for reduction goal")
            cur.execute(
                "INSERT INTO goal_reduction (goal_id, amount, unit) VALUES (?, ?, ?)",
                (goal_id, data["amount"], data.get("unit"))
            )
        elif kind == "range":
            if "min_amount" not in data or "max_amount" not in data:
                raise ValueError(
                    "Missing 'min_amount' or 'max_amount' for range goal")
            cur.execute(
                "INSERT INTO goal_range (goal_id, min_amount, max_amount, unit, mode) VALUES (?, ?, ?, ?, ?)",
                (goal_id, data["min_amount"], data["max_amount"],
                 data.get("unit"), data.get("mode", "goal"))
            )
        elif kind == "percentage":
            if "target_percentage" not in data:
                raise ValueError(
                    "Missing 'target_percentage' for percentage goal")
            cur.execute(
                "INSERT INTO goal_percentage (goal_id, target_percentage, current_percentage) VALUES (?, ?, ?)",
                (goal_id, data["target_percentage"],
                 data.get("current_percentage", 0))
            )
        elif kind == "replacement":
            if "old_behavior" not in data or "new_behavior" not in data:
                raise ValueError(
                    "Missing 'old_behavior' or 'new_behavior' for replacement goal")
            cur.execute(
                "INSERT INTO goal_replacement (goal_id, old_behavior, new_behavior) VALUES (?, ?, ?)",
                (goal_id, data["old_behavior"], data["new_behavior"])
            )
        else:
            raise ValueError(f"Unsupported goal kind: {kind}")

        conn.commit()
    except Exception as e:
        logger.error("_insert_goal_detail: Failed for goal_id=%d kind=%r data=%r: %s",
                     goal_id, kind, data, e, exc_info=True)
        # Re-raise so transaction rollback can occur at caller if needed
        raise
    finally:
        if conn:
            conn.close()


def _update_goal_detail(goal_id: int, data: Dict[str, Any]):
    """
    Update (or insert, if not exists) the detail row for the given goal_id.
    """
    kind = data.get("kind")
    if not kind:
        raise ValueError("Missing 'kind' in goal detail update")

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        def _exists(table_name: str) -> bool:
            cur.execute(
                f"SELECT 1 FROM {table_name} WHERE goal_id = ?", (goal_id,))
            return cur.fetchone() is not None

        if kind == "sum":
            if _exists("goal_sum"):
                if "amount" not in data:
                    raise ValueError("Missing 'amount' for sum goal update")
                cur.execute(
                    "UPDATE goal_sum SET amount = ?, unit = ? WHERE goal_id = ?",
                    (data["amount"], data.get("unit"), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "count":
            if _exists("goal_count"):
                if "amount" not in data:
                    raise ValueError("Missing 'amount' for count goal update")
                cur.execute(
                    "UPDATE goal_count SET amount = ?, unit = ? WHERE goal_id = ?",
                    (data["amount"], data.get("unit"), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "bool":
            if not _exists("goal_bool"):
                _insert_goal_detail(goal_id, data)
        elif kind == "streak":
            if _exists("goal_streak"):
                if "target_streak" not in data:
                    raise ValueError(
                        "Missing 'target_streak' for streak goal update")
                cur.execute(
                    "UPDATE goal_streak SET target_streak = ? WHERE goal_id = ?",
                    (data["target_streak"], goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "duration":
            if _exists("goal_duration"):
                if "amount" not in data:
                    raise ValueError(
                        "Missing 'amount' for duration goal update")
                cur.execute(
                    "UPDATE goal_duration SET amount = ?, unit = ? WHERE goal_id = ?",
                    (data["amount"], data.get("unit", "minutes"), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "milestone":
            if _exists("goal_milestone"):
                if "target" not in data:
                    raise ValueError(
                        "Missing 'target' for milestone goal update")
                cur.execute(
                    "UPDATE goal_milestone SET target = ?, unit = ? WHERE goal_id = ?",
                    (data["target"], data.get("unit"), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "reduction":
            if _exists("goal_reduction"):
                if "amount" not in data:
                    raise ValueError(
                        "Missing 'amount' for reduction goal update")
                cur.execute(
                    "UPDATE goal_reduction SET amount = ?, unit = ? WHERE goal_id = ?",
                    (data["amount"], data.get("unit"), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "range":
            if _exists("goal_range"):
                if "min_amount" not in data or "max_amount" not in data:
                    raise ValueError(
                        "Missing 'min_amount' or 'max_amount' for range goal update")
                cur.execute(
                    "UPDATE goal_range SET min_amount = ?, max_amount = ?, unit = ?, mode = ? WHERE goal_id = ?",
                    (data["min_amount"], data["max_amount"], data.get(
                        "unit"), data.get("mode", "goal"), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "percentage":
            if _exists("goal_percentage"):
                if "target_percentage" not in data:
                    raise ValueError(
                        "Missing 'target_percentage' for percentage goal update")
                cur.execute(
                    "UPDATE goal_percentage SET target_percentage = ?, current_percentage = ? WHERE goal_id = ?",
                    (data["target_percentage"], data.get(
                        "current_percentage", 0), goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        elif kind == "replacement":
            if _exists("goal_replacement"):
                if "old_behavior" not in data or "new_behavior" not in data:
                    raise ValueError(
                        "Missing 'old_behavior' or 'new_behavior' for replacement goal update")
                cur.execute(
                    "UPDATE goal_replacement SET old_behavior = ?, new_behavior = ? WHERE goal_id = ?",
                    (data["old_behavior"], data["new_behavior"], goal_id)
                )
            else:
                _insert_goal_detail(goal_id, data)
        else:
            raise ValueError(f"Unsupported goal kind: {kind}")

        conn.commit()
    except Exception as e:
        logger.error("_update_goal_detail: Failed for goal_id=%d kind=%r data=%r: %s",
                     goal_id, kind, data, e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _delete_goal_detail(goal_id: int, kind: str):
    """
    Delete the detail row from whichever subtype table corresponds to this kind.
    """
    if not kind:
        logger.warning(
            "_delete_goal_detail: missing kind for goal_id=%d", goal_id)
        return

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if kind == "sum":
            cur.execute("DELETE FROM goal_sum WHERE goal_id = ?", (goal_id,))
        elif kind == "count":
            cur.execute("DELETE FROM goal_count WHERE goal_id = ?", (goal_id,))
        elif kind == "bool":
            cur.execute("DELETE FROM goal_bool WHERE goal_id = ?", (goal_id,))
        elif kind == "streak":
            cur.execute(
                "DELETE FROM goal_streak WHERE goal_id = ?", (goal_id,))
        elif kind == "duration":
            cur.execute(
                "DELETE FROM goal_duration WHERE goal_id = ?", (goal_id,))
        elif kind == "milestone":
            cur.execute(
                "DELETE FROM goal_milestone WHERE goal_id = ?", (goal_id,))
        elif kind == "reduction":
            cur.execute(
                "DELETE FROM goal_reduction WHERE goal_id = ?", (goal_id,))
        elif kind == "range":
            cur.execute("DELETE FROM goal_range WHERE goal_id = ?", (goal_id,))
        elif kind == "percentage":
            cur.execute(
                "DELETE FROM goal_percentage WHERE goal_id = ?", (goal_id,))
        elif kind == "replacement":
            cur.execute(
                "DELETE FROM goal_replacement WHERE goal_id = ?", (goal_id,))
        else:
            logger.warning(
                "_delete_goal_detail: Unsupported kind=%r for goal_id=%d", kind, goal_id)
        conn.commit()
    except Exception as e:
        logger.error("_delete_goal_detail: Failed for goal_id=%d kind=%r: %s",
                     goal_id, kind, e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _select_goal_detail(goal_id: int, kind: str) -> Dict[str, Any]:
    """
    Fetch exactly the detail row for this goal_id from the correct subtype table,
    and return a dict of those fields. If no row exists (e.g. bool goal), return {}.
    """
    if not kind:
        raise ValueError("Missing 'kind' in _select_goal_detail")

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if kind == "sum":
            cur.execute(
                "SELECT amount, unit FROM goal_sum WHERE goal_id = ?", (goal_id,))
        elif kind == "count":
            cur.execute(
                "SELECT amount, unit FROM goal_count WHERE goal_id = ?", (goal_id,))
        elif kind == "bool":
            return {}
        elif kind == "streak":
            cur.execute(
                "SELECT target_streak FROM goal_streak WHERE goal_id = ?", (goal_id,))
        elif kind == "duration":
            cur.execute(
                "SELECT amount, unit FROM goal_duration WHERE goal_id = ?", (goal_id,))
        elif kind == "milestone":
            cur.execute(
                "SELECT target, unit FROM goal_milestone WHERE goal_id = ?", (goal_id,))
        elif kind == "reduction":
            cur.execute(
                "SELECT amount, unit FROM goal_reduction WHERE goal_id = ?", (goal_id,))
        elif kind == "range":
            cur.execute(
                "SELECT min_amount, max_amount, unit, mode FROM goal_range WHERE goal_id = ?", (goal_id,))
        elif kind == "percentage":
            cur.execute(
                "SELECT target_percentage, current_percentage FROM goal_percentage WHERE goal_id = ?", (goal_id,))
        elif kind == "replacement":
            cur.execute(
                "SELECT old_behavior, new_behavior FROM goal_replacement WHERE goal_id = ?", (goal_id,))
        else:
            raise ValueError(f"Unsupported goal kind: {kind}")
        row = cur.fetchone()
        return dict(row) if row else {}
    except Exception as e:
        logger.error("_select_goal_detail: Failed for goal_id=%d kind=%r: %s",
                     goal_id, kind, e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


# ───────────────────────────────────────────────────────────────────────────────
# PUBLIC CRUD APIs (CLIENT/HOST‐SYNC‐AWARE)
# ───────────────────────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────────────────────
# GOAL CRUD (with host/client sync)
# ───────────────────────────────────────────────────────────────────────────────

def get_goals_for_tracker(tracker_id: int) -> List[Goal]:
    """
    Return all fully-populated Goal objects for a given tracker_id.
    In CLIENT mode, pull only changed goals since last sync first.
    """
    if should_sync():
        try:
            _pull_changed_goals_from_host()
        except Exception as e:
            logger.error(
                "get_goals_for_tracker: error pulling from host: %s", e, exc_info=True)

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM goals WHERE tracker_id = ?", (tracker_id,))
        core_rows = cursor.fetchall()

        results: List[Goal] = []
        for core in core_rows:
            row_dict = dict(core)
            goal_id = row_dict["id"]
            kind = row_dict["kind"]
            # Fetch detail fields
            try:
                detail = _select_goal_detail(goal_id, kind)
                row_dict.update(detail)
            except Exception as e:
                logger.error(
                    "get_goals_for_tracker: Failed to fetch detail for goal_id=%d kind=%s: %s", goal_id, kind, e, exc_info=True)
            try:
                results.append(goal_from_row(row_dict))
            except Exception as e:
                logger.error(
                    "get_goals_for_tracker: goal_from_row failed for data=%r: %s", row_dict, e, exc_info=True)
        return results
    except Exception as e:
        logger.error("get_goals_for_tracker: DB error for tracker_id=%d: %s",
                     tracker_id, e, exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_goal_by_uid(uid_val: str) -> Optional[Goal]:
    """
    Fetch a single Goal by its global UID.
    """
    if should_sync():
        try:
            _pull_changed_goals_from_host()
        except Exception as e:
            logger.error(
                "get_goal_by_uid: error pulling from host: %s", e, exc_info=True)

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM goals WHERE uid = ?", (uid_val,))
        row = cursor.fetchone()
        if not row:
            return None
        return get_goal_by_id(row["id"])
    except Exception as e:
        logger.error("get_goal_by_uid: DB error for uid=%s: %s",
                     uid_val, e, exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def add_goal(tracker_id: int, goal_data: Dict[str, Any]) -> Goal:
    """
    1) Insert only core columns into 'goals'
    2) Then insert into the correct subtype table (via _insert_goal_detail)
    3) If CLIENT, queue a sync‐create with the full payload
    4) Return the fully‐populated Goal dataclass
    """
    data = goal_data.copy()
    data["tracker_id"] = tracker_id

    # 1) UID (same as before)
    if not is_direct_db_mode():
        data.setdefault("uid", str(uuid.uuid4()))
    else:
        data.setdefault("uid", data.get("uid") or str(uuid.uuid4()))

    # 2) IDEMPOTENT VALIDATION (optional):
    validate_goal_fields(data)

    # 3) Insert only the FIVE core fields into "goals"
    # now = ['uid','tracker_id','title','kind','period']
    core_fields = _get_all_goal_field_names()
    add_record("goals", data, core_fields)

    # 4) Immediately fetch the newly‐created numeric ID
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM goals WHERE uid = ?", (data["uid"],))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise RuntimeError("Failed to insert into core table")
    new_id = row["id"]

    # 5) Insert into the appropriate detail table
    _insert_goal_detail(new_id, data)
    conn.close()

    # 6) If CLIENT mode, queue a “create” (full payload includes detail keys)
    if not is_direct_db_mode():
        queue_sync_operation("goals", "create", data)
        process_sync_queue()

    # 7) Finally return the fully populated Goal
    return get_goal_by_id(new_id)


def add_goal(tracker_id: int, goal_data: Dict[str, Any]) -> Goal:
    """
    Insert a new Goal:
      1) Validate required fields.
      2) Insert core row into 'goals'.
      3) Insert detail row into subtype table, in a transaction.
      4) Queue sync-create if needed.
      5) Return fully populated Goal dataclass.
    """
    data = goal_data.copy()
    data["tracker_id"] = tracker_id

    # UID assignment
    if not is_direct_db_mode():
        data.setdefault("uid", str(uuid.uuid4()))
    else:
        data.setdefault("uid", data.get("uid") or str(uuid.uuid4()))

    # Validate core + detail before any DB changes
    try:
        validate_goal_fields(data)
    except Exception as e:
        logger.error("add_goal: Validation failed for data=%r: %s",
                     data, e, exc_info=True)
        raise

    # Insert core row
    core_fields = _get_all_goal_field_names()
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        # Begin transaction
        conn.execute("BEGIN")
        # 1) Insert into core table
        add_record("goals", data, core_fields)
        # 2) Fetch new ID
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM goals WHERE uid = ?", (data["uid"],))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("add_goal: Failed to insert into core table")
        new_id = row["id"]
        # 3) Insert detail row
        try:
            _insert_goal_detail(new_id, data)
        except Exception as e:
            raise
        # Commit transaction
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("add_goal: Failed to insert goal for tracker_id=%d data=%r: %s",
                     tracker_id, data, e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

    # Queue sync-create if client mode and syncing enabled
    if not is_direct_db_mode() and should_sync():
        try:
            queue_sync_operation("goals", "create", data)
            process_sync_queue()
            logger.info(
                "add_goal: Queued sync-create for goal uid=%s", data["uid"])
        except Exception as e:
            logger.error("add_goal: Sync-create failed for goal uid=%s: %s",
                         data["uid"], e, exc_info=True)

    # Return fully populated
    return get_goal_by_id(new_id)


def update_goal(goal_id: int, updates: Dict[str, Any]) -> Optional[Goal]:
    """
    Update a goal by numeric ID.
    - Validate fields.
    - In HOST/DIRECT: update core + detail in a transaction, handling kind-change.
    - In CLIENT: update locally, then queue sync-update with full payload if should_sync().
    Returns updated Goal or None.
    """
    # Validate partial updates: if fields provided, ensure valid types/values.
    # Fetch existing goal to get old_kind and existing data
    conn_pre = None
    try:
        conn_pre = get_connection()
        conn_pre.row_factory = sqlite3.Row
        cur_pre = conn_pre.cursor()
        cur_pre.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        row_pre = cur_pre.fetchone()
        if not row_pre:
            logger.warning("update_goal: goal id=%d not found", goal_id)
            return None
        existing = dict(row_pre)
        old_kind = existing["kind"]
    except Exception as e:
        logger.error(
            "update_goal: Failed to fetch existing goal id=%d: %s", goal_id, e, exc_info=True)
        return None
    finally:
        if conn_pre:
            conn_pre.close()

    # Validate fields in `updates`
    # If core fields: title, kind, period etc.
    core_fields = _get_all_goal_field_names()
    core_updates = {k: updates[k] for k in core_fields if k in updates}

    # If kind changes, ensure new kind is valid and detail fields exist
    new_kind = updates.get("kind", old_kind)
    kind_changed = new_kind != old_kind

    # Build a combined data dict for validation: start from existing, then overlay updates
    merged = existing.copy()
    merged.update(updates)
    try:
        validate_goal_fields(merged)
    except Exception as e:
        logger.error("update_goal: Validation failed for updates=%r on goal_id=%d: %s",
                     updates, goal_id, e, exc_info=True)
        raise

    # HOST/DIRECT mode: use transaction
    if is_direct_db_mode():
        conn = None
        try:
            conn = get_connection()
            conn.execute("BEGIN")
            # 1) Update core if any
            if core_updates:
                try:
                    update_record("goals", goal_id, core_updates)
                    logger.info("update_goal: Updated core fields for goal id=%d: %s", goal_id, list(
                        core_updates.keys()))
                except Exception as e:
                    logger.error(
                        "update_goal: Failed to update core for goal id=%d: %s", goal_id, e, exc_info=True)
                    # continue to detail section
            # 2) Handle detail
            if kind_changed:
                # delete old detail then insert new
                try:
                    _delete_goal_detail(goal_id, old_kind)
                    logger.info(
                        "update_goal: Deleted old detail for goal id=%d kind=%s", goal_id, old_kind)
                except Exception as e:
                    logger.error(
                        "update_goal: Failed to delete old detail for goal id=%d: %s", goal_id, e, exc_info=True)
                try:
                    _insert_goal_detail(goal_id, merged)
                    logger.info(
                        "update_goal: Inserted new detail for goal id=%d kind=%s", goal_id, new_kind)
                except Exception as e:
                    logger.error(
                        "update_goal: Failed to insert new detail for goal id=%d: %s", goal_id, e, exc_info=True)
                    raise
            else:
                try:
                    _update_goal_detail(goal_id, merged)
                    logger.info(
                        "update_goal: Updated detail for goal id=%d kind=%s", goal_id, old_kind)
                except Exception as e:
                    logger.error(
                        "update_goal: Failed to update detail for goal id=%d: %s", goal_id, e, exc_info=True)
                    raise
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(
                "update_goal: Transaction failed for goal_id=%d: %s", goal_id, e, exc_info=True)
            raise
        finally:
            if conn:
                conn.close()
        # Return fresh object
        return get_goal_by_id(goal_id)

    # CLIENT mode: update locally first
    # 1) Update core
    try:
        if core_updates:
            update_record("goals", goal_id, core_updates)
            logger.info("update_goal (client): Updated core fields for goal id=%d: %s",
                        goal_id, list(core_updates.keys()))
    except Exception as e:
        logger.error(
            "update_goal (client): Failed to update core for goal id=%d: %s", goal_id, e, exc_info=True)
        raise

    # 2) Handle detail locally
    try:
        if kind_changed:
            try:
                _delete_goal_detail(goal_id, old_kind)
                logger.info(
                    "update_goal (client): Deleted old detail for goal id=%d kind=%s", goal_id, old_kind)
            except Exception as e:
                logger.error(
                    "update_goal (client): Failed to delete old detail for goal id=%d: %s", goal_id, e, exc_info=True)
            _insert_goal_detail(goal_id, merged)
            logger.info(
                "update_goal (client): Inserted new detail for goal id=%d kind=%s", goal_id, new_kind)
        else:
            _update_goal_detail(goal_id, merged)
            logger.info(
                "update_goal (client): Updated detail for goal id=%d kind=%s", goal_id, old_kind)
    except Exception as e:
        logger.error(
            "update_goal (client): Detail update failed for goal id=%d: %s", goal_id, e, exc_info=True)
        raise

    # 3) Build full payload
    conn2 = None
    try:
        conn2 = get_connection()
        conn2.row_factory = sqlite3.Row
        cursor = conn2.cursor()
        cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        row = cursor.fetchone()
        if not row:
            logger.error(
                "update_goal (client): After update, goal id=%d not found", goal_id)
            return None
        full_payload = dict(row)
        # Add detail fields
        try:
            detail = _select_goal_detail(goal_id, full_payload.get("kind"))
            full_payload.update(detail)
        except Exception as e:
            logger.error(
                "update_goal (client): Failed to fetch detail for payload goal id=%d: %s", goal_id, e, exc_info=True)
    except Exception as e:
        logger.error(
            "update_goal (client): DB fetch failed after update for id=%d: %s", goal_id, e, exc_info=True)
        return None
    finally:
        if conn2:
            conn2.close()

    # 4) Queue sync-update if syncing enabled
    if should_sync():
        payload = full_payload.copy()
        payload.pop("id", None)
        try:
            queue_sync_operation("goals", "update", payload)
            process_sync_queue()
            logger.info("update_goal (client): Queued sync-update for goal id=%d uid=%s",
                        goal_id, payload.get("uid"))
        except Exception as e:
            logger.error("update_goal (client): Sync-update failed for goal id=%d uid=%s: %s",
                         goal_id, payload.get("uid"), e, exc_info=True)

    # 5) Return updated object
    try:
        return goal_from_row(full_payload)
    except Exception as e:
        logger.error("update_goal (client): goal_from_row failed for payload=%r: %s",
                     full_payload, e, exc_info=True)
        return None


def delete_goal(goal_id: int) -> bool:
    """
    Delete a goal by numeric ID. ON DELETE CASCADE handles detail rows.
    In CLIENT mode, queue sync-delete by uid if should_sync().
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT uid FROM goals WHERE id = ?", (goal_id,))
        row = cur.fetchone()
        if not row:
            logger.warning("delete_goal: goal id=%d not found", goal_id)
            return False
        uid_val = row["uid"]
        # Delete core row
        cur.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()
        logger.info("delete_goal: Deleted goal id=%d uid=%s", goal_id, uid_val)
    except Exception as e:
        logger.error("delete_goal: Failed to delete goal id=%d: %s",
                     goal_id, e, exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

    # Client sync-delete if enabled
    if not is_direct_db_mode() and should_sync():
        payload = {"uid": uid_val} if uid_val else {"id": goal_id}
        try:
            queue_sync_operation("goals", "delete", payload)
            process_sync_queue()
            logger.info(
                "delete_goal: Queued sync-delete for goal id=%d uid=%s", goal_id, uid_val)
        except Exception as e:
            logger.error("delete_goal: Sync-delete failed for goal id=%d uid=%s: %s",
                         goal_id, uid_val, e, exc_info=True)
    return True


# ───────────────────────────────────────────────────────────────────────────────
# UPsert HELPER FOR CLIENT‐SYNCHRONIZATION (pull from host)
# i.e. “Given a dict from fetch_from_server('goals')…”
# ───────────────────────────────────────────────────────────────────────────────

def upsert_local_goal(data: Dict[str, Any]) -> None:
    """
    When a client pulls from server, it gets back a JSON object that contains:
      • core fields: { "uid", "tracker_id", "title", "kind", "period" }
      • plus exactly the detail fields for that kind.
    This function:
      1) Looks up local goal row by uid.
      2) If exists → UPDATE core + detail.
      3) If not exists → INSERT core + detail.
    """
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning(
            "upsert_local_goal called without uid in data: %r", data)
        return

    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check existing core row
        cur.execute("SELECT id, kind FROM goals WHERE uid = ?", (uid_val,))
        existing = cur.fetchone()

        # ['uid','tracker_id','title','kind','period']
        core_fields = _get_core_goal_fields()
        if existing:
            local_id = existing["id"]
            old_kind = existing["kind"]
            # 1) Update core fields if any present
            updates = {k: data[k] for k in core_fields if k in data}
            if updates:
                try:
                    update_record("goals", local_id, updates)
                    logger.info("Updated core goal id=%d via upsert_local_goal, fields: %s", local_id, list(
                        updates.keys()))
                except Exception as e:
                    logger.error("Failed to update core goal id=%d: %s",
                                 local_id, e, exc_info=True)
                    # Continue to detail handling even if core update partially failed.

            # 2) Handle detail row
            new_kind = data.get("kind")
            if new_kind and new_kind != old_kind:
                # Kind changed: delete old detail row, insert new detail
                try:
                    _delete_goal_detail(local_id, old_kind)
                    logger.info(
                        "Deleted old detail for goal id=%d kind=%s", local_id, old_kind)
                except Exception as e:
                    logger.error("Failed to delete old detail for goal id=%d kind=%s: %s",
                                 local_id, old_kind, e, exc_info=True)
                try:
                    _insert_goal_detail(local_id, data)
                    logger.info(
                        "Inserted new detail for goal id=%d kind=%s", local_id, new_kind)
                except Exception as e:
                    logger.error("Failed to insert new detail for goal id=%d kind=%s: %s",
                                 local_id, new_kind, e, exc_info=True)
            else:
                # Kind unchanged: update or insert detail as needed
                try:
                    _update_goal_detail(local_id, data)
                    logger.info(
                        "Updated detail for goal id=%d kind=%s", local_id, old_kind)
                except Exception as e:
                    logger.error(
                        "Failed to update detail for goal id=%d: %s", local_id, e, exc_info=True)

        else:
            # 1) Insert new core row
            try:
                add_record("goals", data, core_fields)
                logger.info("Inserted new core goal uid=%s", uid_val)
            except Exception as e:
                logger.error("Failed to insert core goal uid=%s: %s",
                             uid_val, e, exc_info=True)
                return
            # 2) Fetch new ID
            cur.execute("SELECT id FROM goals WHERE uid = ?", (uid_val,))
            row_new = cur.fetchone()
            if not row_new:
                logger.error(
                    "Failed to fetch newly inserted goal uid=%s", uid_val)
                return
            new_id = row_new["id"]
            # 3) Insert detail row
            try:
                _insert_goal_detail(new_id, data)
                logger.info(
                    "Inserted detail for new goal id=%d kind=%s", new_id, data.get("kind"))
            except Exception as e:
                logger.error(
                    "Failed to insert detail for new goal id=%d: %s", new_id, e, exc_info=True)
    except Exception as e:
        logger.error(
            "Unexpected error in upsert_local_goal for uid=%s: %s", uid_val, e, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ───────────────────────────────────────────────────────────────────────────────
# Public helper to fetch by numeric ID: includes core + detail
# ───────────────────────────────────────────────────────────────────────────────

def get_goal_by_id(goal_id: int) -> Optional[Goal]:
    """
    Return fully-populated Goal by numeric ID, or None if not found/error.
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        core = cursor.fetchone()
        if not core:
            return None
        row_dict = dict(core)
        kind = row_dict.get("kind")
        # Fetch detail fields
        try:
            detail = _select_goal_detail(goal_id, kind)
            row_dict.update(detail)
        except Exception:
            # already logged in _select_goal_detail
            pass
        return goal_from_row(row_dict)
    except Exception as e:
        logger.error("get_goal_by_id: DB error for id=%d: %s",
                     goal_id, e, exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def query_goals(**filters) -> List[Goal]:
    """
    Query goals by arbitrary fields. Returns list of Goal dataclasses.
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        sql = "SELECT * FROM goals"
        if filters:
            where = " AND ".join([f"{k} = ?" for k in filters])
            sql += f" WHERE {where}"
            cur.execute(sql, tuple(filters.values()))
        else:
            cur.execute(sql)
        rows = cur.fetchall()
        results: List[Goal] = []
        for r in rows:
            try:
                gd = dict(r)
                goal_obj = goal_from_row(gd)
                results.append(goal_obj)
            except Exception as e:
                logger.error("query_goals: goal_from_row failed for row=%r: %s", dict(
                    r), e, exc_info=True)
        return results
    except Exception as e:
        logger.error("query_goals: DB error with filters=%r: %s",
                     filters, e, exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

# For tracker


# ───────────────────────────────────────────────────────────────────────────────
# Validation helper for goals
# ───────────────────────────────────────────────────────────────────────────────

def validate_goal_fields(goal: dict):
    """
    Validate required fields for create/update of a Goal.
    Raises ValueError if invalid.
    """
    required = ["title", "kind", "period", "tracker_id", "uid"]
    for k in required:
        if k not in goal or goal.get(k) is None:
            raise ValueError(f"Missing required field: {k}")

    kind = goal["kind"]
    # Validate based on kind
    if kind in ("sum", "count", "reduction", "duration"):
        amt = goal.get("amount", None)
        if amt is None or not isinstance(amt, (int, float)):
            raise ValueError(f"Goal kind '{kind}' requires numeric 'amount'")
    if kind == "range":
        if goal.get("min_amount") is None or goal.get("max_amount") is None:
            raise ValueError("Range goals need 'min_amount' and 'max_amount'")
        if not isinstance(goal["min_amount"], (int, float)) or not isinstance(goal["max_amount"], (int, float)):
            raise ValueError(
                "Range goal 'min_amount' and 'max_amount' must be numeric")
    if kind == "streak":
        ts = goal.get("target_streak", None)
        if ts is None or not isinstance(ts, int):
            raise ValueError("Streak goals need integer 'target_streak'")
    if kind == "percentage":
        tp = goal.get("target_percentage", None)
        if tp is None or not isinstance(tp, (int, float)):
            raise ValueError(
                "Percentage goals need numeric 'target_percentage'")
        # current_percentage if provided should be numeric
        cp = goal.get("current_percentage", None)
        if cp is not None and not isinstance(cp, (int, float)):
            raise ValueError(
                "Percentage goal 'current_percentage' must be numeric if provided")
    if kind == "milestone":
        tgt = goal.get("target", None)
        if tgt is None or not isinstance(tgt, (int, float)):
            raise ValueError("Milestone goals need numeric 'target'")
    if kind == "replacement":
        if not goal.get("old_behavior") or not goal.get("new_behavior"):
            raise ValueError(
                "Replacement goals need 'old_behavior' and 'new_behavior'")
    if kind == "bool":
        # no extra fields needed
        pass
    # period: ensure it's a non-empty string
    if not isinstance(goal.get("period"), str) or not goal["period"]:
        raise ValueError("Goal 'period' must be a non-empty string")


# ───────────────────────────────────────────────────────────────────────────────
# Helpers combining trackers & goals/entries
# ───────────────────────────────────────────────────────────────────────────────


def get_all_trackers_with_goals() -> List[Tracker]:
    """
    Return all Tracker instances, each with .goals populated as List[Goal].
    """
    trackers = get_all_trackers()  # List[Tracker], goals=None initially
    for tracker in trackers:
        try:
            goals: List[Goal] = get_goals_for_tracker(tracker.id)
        except Exception:
            goals = []
        tracker.goals = goals
    return trackers


def get_all_trackers_with_entries() -> List[Tracker]:
    """
    Return all Tracker instances, each with .entries populated as List[TrackerEntry].
    """
    trackers = get_all_trackers()
    for tracker in trackers:
        try:
            entries: List[TrackerEntry] = get_entries_for_tracker(tracker.id)
        except Exception:
            entries = []
        tracker.entries = entries
    return trackers


def get_goal_details(goal_id: int) -> Dict[str, Any]:
    """
    Fetch detail fields for the given goal_id based on its kind.
    Returns a dict of detail columns (e.g., {'min_amount': ..., 'max_amount': ..., ...}).
    Raises ValueError if goal not found or kind missing.
    """
    goal = get_goal_by_id(goal_id)
    if not goal:
        raise ValueError(f"Goal with id {goal_id} not found")
    kind = goal.kind  # attribute access on dataclass
    if not kind:
        raise ValueError(f"Goal id {goal_id} has no kind")
    # _select_goal_detail returns {} if no detail row (e.g., bool has no extra columns)
    try:
        details = _select_goal_detail(goal_id, kind)
    except Exception as e:
        # Log or wrap exception as needed; for now, re-raise
        raise
    return details or {}
