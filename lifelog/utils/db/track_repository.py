# lifelog/utils/db/track_repository.py

from datetime import datetime
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

# ───────────────────────────────────────────────────────────────────────────────
# IMPORTANT: Your schema must include these columns:
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


def _pull_changed_trackers_from_host() -> None:
    """
    If in client mode, fetch only trackers changed on the host
    since our last sync, upsert them locally, and update sync_state.
    """
    if not should_sync():
        return

    # 1) Push any queued tracker‐create/update/delete operations
    process_sync_queue()

    # 2) Read last sync timestamp for "trackers"
    last_ts = get_last_synced("trackers")
    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) Fetch changed trackers from host
    remote_list = fetch_from_server("trackers", params=params)
    for remote in remote_list:
        upsert_local_tracker(remote)

    # 4) Update sync_state to now
    now_iso = datetime.utcnow().isoformat()
    set_last_synced("trackers", now_iso)


def _pull_changed_goals_from_host() -> None:
    """
    If in client mode, fetch only goals changed on the host
    since our last sync, upsert them locally, and update sync_state.
    """
    if not should_sync():
        return

    # 1) Push any queued goal‐create/update/delete
    process_sync_queue()

    # 2) Read last sync timestamp for "goals"
    last_ts = get_last_synced("goals")
    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) Fetch changed goals from host
    remote_list = fetch_from_server("goals", params=params)
    for remote in remote_list:
        upsert_local_goal(remote)

    # 4) Update sync_state to now
    now_iso = datetime.utcnow().isoformat()
    set_last_synced("goals", now_iso)


def _get_all_tracker_field_names() -> List[str]:
    """
    Return all Tracker table columns except 'id', to be used in INSERT/UPDATE:
    ['uid','title','type','category','created','tags','notes']
    """
    return [f for f in get_tracker_fields() if f != "id"]


def _get_all_goal_field_names() -> List[str]:
    """
    Return only the five core 'goals' columns, excluding 'id':
      ['uid','tracker_id','title','kind','period'].
    """
    return [f for f in get_goal_fields() if f != "id"]

# ───────────────────────────────────────────────────────────────────────────────
# UPsert Helpers (used during “pull” from host in client mode)
# ───────────────────────────────────────────────────────────────────────────────


def upsert_local_tracker(data: Dict[str, Any]) -> None:
    """
    Given a dict from fetch_from_server('trackers', …), insert or update local by uid:
      • If uid exists → UPDATE trackers SET … WHERE uid = ?
      • Else         → INSERT INTO trackers (…) VALUES (…)
    """
    uid_val = data.get("uid")
    if not uid_val:
        return

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1) Check if a local row with this uid exists
    cursor.execute("SELECT id FROM trackers WHERE uid = ?", (uid_val,))
    existing = cursor.fetchone()

    fields = _get_all_tracker_field_names()
    if existing:
        local_id = existing["id"]
        updates = {k: data[k] for k in fields if k in data}
        update_record("trackers", local_id, updates)
    else:
        add_record("trackers", data, fields)

    conn.close()


def upsert_local_goal(data: Dict[str, Any]) -> None:
    """
    Given a dict from fetch_from_server('goals', …), insert or update local by uid:
    """
    uid_val = data.get("uid")
    if not uid_val:
        return

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM goals WHERE uid = ?", (uid_val,))
    existing = cursor.fetchone()

    fields = _get_all_goal_field_names()
    if existing:
        local_id = existing["id"]
        updates = {k: data[k] for k in fields if k in data}
        update_record("goals", local_id, updates)
    else:
        add_record("goals", data, fields)

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
    In CLIENT mode, first push local changes & pull remote, upsert locally, then SELECT.
    """
    if should_sync():
        _pull_changed_trackers_from_host()

    # 3) Now read from local SQLite
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
    conn.close()

    return [tracker_from_row(dict(r)) for r in rows]


def get_tracker_by_title(title: str) -> Optional[Tracker]:
    """
    Return one Tracker (as a dataclass) whose `title` exactly matches the given string.
    If in CLIENT mode, first pull any changed trackers before doing the local SELECT.
    """
    if should_sync():
        _pull_changed_trackers_from_host()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM trackers WHERE title = ? LIMIT 1", (title,))
    row = cur.fetchone()
    conn.close()
    return tracker_from_row(dict(row)) if row else None


def get_tracker_by_id(tracker_id: int) -> Optional[Tracker]:
    """
    Return one Tracker by numeric ID. In CLIENT mode, push → pull by uid → upsert → return.
    """
    if should_sync():
        _pull_changed_trackers_from_host()

    # 3) Read local
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    row = cursor.fetchone()
    conn.close()

    return tracker_from_row(dict(row)) if row else None


def get_tracker_by_uid(uid_val: str) -> Optional[Tracker]:
    """
    Return one Tracker by its global UID. In CLIENT mode, push → pull by uid → upsert → return.
    """
    if should_sync():
        _pull_changed_trackers_from_host()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trackers WHERE uid = ?", (uid_val,))
    row = cursor.fetchone()
    conn.close()

    return tracker_from_row(dict(row)) if row else None


def add_tracker(tracker_data: Any) -> Tracker:
    """
    Insert a new Tracker (definition). Always returns the newly created Tracker.
    • In CLIENT mode: assign uid, insert locally, queue create sync, drain, then re-select.
    • In HOST/DIRECT mode: assign uid if missing, insert directly, then return.
    """
    # 1) If passed a dataclass instance, convert to dict
    if isinstance(tracker_data, Tracker):
        data = tracker_data.__dict__.copy()
    else:
        data = tracker_data.copy()

    # 2) Fill defaults
    data.setdefault("title", None)
    data.setdefault("type", None)
    data.setdefault("category", None)
    data.setdefault("created", datetime.now().isoformat())
    data.setdefault("tags", None)
    data.setdefault("notes", None)

    # 3) Ensure a global UID
    if not is_direct_db_mode():
        data.setdefault("uid", str(uuid.uuid4()))
    else:
        data.setdefault("uid", data.get("uid") or str(uuid.uuid4()))

    # 4) Insert into local SQLite
    fields = _get_all_tracker_field_names()
    add_record("trackers", data, fields)

    # 5) Re-fetch the inserted row (so we know its numeric id)
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trackers WHERE uid = ?", (data["uid"],))
    row = cursor.fetchone()
    conn.close()
    new_tracker = tracker_from_row(dict(row))

    # 6) In CLIENT mode, queue a “create” and drain the queue
    if not is_direct_db_mode():
        queue_sync_operation("trackers", "create", data)
        process_sync_queue()

    return new_tracker


def update_tracker(tracker_id: int, updates: Dict[str, Any]) -> Tracker:
    """
    Update an existing tracker (partial fields).
    • In HOST/DIRECT: UPDATE … WHERE id = ?
    • In CLIENT: UPDATE local by id, then fetch full row, queue “update” by uid (full payload), drain.
    Returns the updated Tracker.
    """
    if is_direct_db_mode():
        # Direct UPDATE by numeric ID
        update_record("trackers", tracker_id, updates)
        return get_tracker_by_id(tracker_id)

    else:
        # CLIENT mode
        update_record("trackers", tracker_id, updates)

        # Fetch local row to get uid & full payload
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
        row = cursor.fetchone()
        conn.close()

        full_payload = dict(row) if row else {}
        # Remove numeric id before sending; host only needs uid
        full_payload.pop("id", None)

        queue_sync_operation("trackers", "update", full_payload)
        process_sync_queue()

        return tracker_from_row(dict(row)) if row else None


def delete_tracker(tracker_id: int) -> bool:
    """
    Delete a tracker (and its goals/entries via FOREIGN KEY CASCADE).
    • HOST/DIRECT: DELETE FROM trackers WHERE id = ?; return True.
    • CLIENT: SELECT uid, DELETE locally, queue “delete” by uid, drain. Return True.
    """
    # 1) Look up uid if CLIENT
    conn = get_connection()
    cursor = conn.cursor()

    if is_direct_db_mode():
        cursor.execute("DELETE FROM trackers WHERE id = ?", (tracker_id,))
        conn.commit()
        conn.close()
        return True

    else:
        # CLIENT mode
        cursor.execute("SELECT uid FROM trackers WHERE id = ?", (tracker_id,))
        row = cursor.fetchone()
        uid_val = row["uid"] if row else None

        # Delete locally
        cursor.execute("DELETE FROM trackers WHERE id = ?", (tracker_id,))
        conn.commit()
        conn.close()

        # Queue delete by uid (or fallback to id if no uid)
        if uid_val:
            queue_sync_operation("trackers", "delete", {"uid": uid_val})
        else:
            queue_sync_operation("trackers", "delete", {"id": tracker_id})

        process_sync_queue()
        return True


# ───────────────────────────────────────────────────────────────────────────────
# TRACKER-ENTRY CRUD (these are purely local; we do NOT sync entries themselves)
# ───────────────────────────────────────────────────────────────────────────────

def add_tracker_entry(tracker_id: int, timestamp: str, value: float) -> TrackerEntry:
    """
    Record a new entry for a given tracker. This is local-only; no sync to host.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO tracker_entries (tracker_id, timestamp, value) VALUES (?, ?, ?)",
        (tracker_id, timestamp, value)
    )
    conn.commit()

    # Re‐fetch the inserted row
    new_id = cursor.lastrowid
    cursor.execute("SELECT * FROM tracker_entries WHERE id = ?", (new_id,))
    row = cursor.fetchone()
    conn.close()
    return entry_from_row(dict(row))


def get_entries_for_tracker(tracker_id: int) -> List[TrackerEntry]:
    """
    Return all entries for a given tracker_id (local-only).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tracker_entries WHERE tracker_id = ? ORDER BY timestamp ASC",
        (tracker_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [entry_from_row(dict(r)) for r in rows]


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

def _insert_goal_detail(goal_id: int, data: Dict[str, Any]):
    """
    Depending on data['kind'], insert into the correct subtype table.
    We assume `data` includes exactly whatever detail‐fields that kind needs.
    """
    kind = data["kind"]

    conn = get_connection()
    cur = conn.cursor()

    if kind == "sum":
        # required fields: amount (real), unit (optional)
        cur.execute(
            "INSERT INTO goal_sum (goal_id, amount, unit) VALUES (?, ?, ?)",
            (goal_id, data["amount"], data.get("unit"))
        )

    elif kind == "count":
        # required fields: amount (integer), unit (optional)
        cur.execute(
            "INSERT INTO goal_count (goal_id, amount, unit) VALUES (?, ?, ?)",
            (goal_id, data["amount"], data.get("unit"))
        )

    elif kind == "bool":
        # no extra fields—just insert a row so the existence = True
        cur.execute(
            "INSERT INTO goal_bool (goal_id) VALUES (?)",
            (goal_id,)
        )

    elif kind == "streak":
        # required: target_streak (integer)
        cur.execute(
            "INSERT INTO goal_streak (goal_id, target_streak) VALUES (?, ?)",
            (goal_id, data["target_streak"])
        )

    elif kind == "duration":
        # required: amount (real), unit (text; default 'minutes')
        cur.execute(
            "INSERT INTO goal_duration (goal_id, amount, unit) VALUES (?, ?, ?)",
            (goal_id, data["amount"], data.get("unit", "minutes"))
        )

    elif kind == "milestone":
        # required: target (real), unit (optional)
        cur.execute(
            "INSERT INTO goal_milestone (goal_id, target, unit) VALUES (?, ?, ?)",
            (goal_id, data["target"], data.get("unit"))
        )

    elif kind == "reduction":
        # required: amount (real), unit (optional)
        cur.execute(
            "INSERT INTO goal_reduction (goal_id, amount, unit) VALUES (?, ?, ?)",
            (goal_id, data["amount"], data.get("unit"))
        )

    elif kind == "range":
        # required: min_amount (real), max_amount (real), unit (optional), mode (optional)
        cur.execute(
            "INSERT INTO goal_range (goal_id, min_amount, max_amount, unit, mode) VALUES (?, ?, ?, ?, ?)",
            (goal_id, data["min_amount"], data["max_amount"],
             data.get("unit"), data.get("mode", "goal"))
        )

    elif kind == "percentage":
        # required: target_percentage (real), current_percentage (optional)
        cur.execute(
            "INSERT INTO goal_percentage (goal_id, target_percentage, current_percentage) VALUES (?, ?, ?)",
            (goal_id, data["target_percentage"],
             data.get("current_percentage", 0))
        )

    elif kind == "replacement":
        # required: old_behavior (text), new_behavior (text)
        cur.execute(
            "INSERT INTO goal_replacement (goal_id, old_behavior, new_behavior) VALUES (?, ?, ?)",
            (goal_id, data["old_behavior"], data["new_behavior"])
        )

    else:
        conn.close()
        raise ValueError(f"Unsupported goal kind: {kind}")

    conn.commit()
    conn.close()


def _update_goal_detail(goal_id: int, data: Dict[str, Any]):
    """
    Update (or insert, if not exists) the detail row for the given goal_id.
    Typically called inside update_goal(). We assume `data['kind']` is unchanged,
    or if the kind changed, we DELETE the old detail row and INSERT a brand‐new one.
    """
    kind = data["kind"]
    conn = get_connection()
    cur = conn.cursor()

    # Helper to see if a detail row already exists in that subtype table:
    def _exists(table_name: str) -> bool:
        cur.execute(
            f"SELECT 1 FROM {table_name} WHERE goal_id = ?", (goal_id,))
        return cur.fetchone() is not None

    if kind == "sum":
        if _exists("goal_sum"):
            cur.execute(
                "UPDATE goal_sum SET amount = ?, unit = ? WHERE goal_id = ?",
                (data["amount"], data.get("unit"), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "count":
        if _exists("goal_count"):
            cur.execute(
                "UPDATE goal_count SET amount = ?, unit = ? WHERE goal_id = ?",
                (data["amount"], data.get("unit"), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "bool":
        if not _exists("goal_bool"):
            _insert_goal_detail(goal_id, data)
        # no fields to update otherwise

    elif kind == "streak":
        if _exists("goal_streak"):
            cur.execute(
                "UPDATE goal_streak SET target_streak = ? WHERE goal_id = ?",
                (data["target_streak"], goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "duration":
        if _exists("goal_duration"):
            cur.execute(
                "UPDATE goal_duration SET amount = ?, unit = ? WHERE goal_id = ?",
                (data["amount"], data.get("unit", "minutes"), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "milestone":
        if _exists("goal_milestone"):
            cur.execute(
                "UPDATE goal_milestone SET target = ?, unit = ? WHERE goal_id = ?",
                (data["target"], data.get("unit"), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "reduction":
        if _exists("goal_reduction"):
            cur.execute(
                "UPDATE goal_reduction SET amount = ?, unit = ? WHERE goal_id = ?",
                (data["amount"], data.get("unit"), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "range":
        if _exists("goal_range"):
            cur.execute(
                "UPDATE goal_range SET min_amount = ?, max_amount = ?, unit = ?, mode = ? WHERE goal_id = ?",
                (data["min_amount"], data["max_amount"], data.get(
                    "unit"), data.get("mode", "goal"), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "percentage":
        if _exists("goal_percentage"):
            cur.execute(
                "UPDATE goal_percentage SET target_percentage = ?, current_percentage = ? WHERE goal_id = ?",
                (data["target_percentage"], data.get(
                    "current_percentage", 0), goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    elif kind == "replacement":
        if _exists("goal_replacement"):
            cur.execute(
                "UPDATE goal_replacement SET old_behavior = ?, new_behavior = ? WHERE goal_id = ?",
                (data["old_behavior"], data["new_behavior"], goal_id)
            )
        else:
            _insert_goal_detail(goal_id, data)

    else:
        conn.close()
        raise ValueError(f"Unsupported goal kind: {kind}")

    conn.commit()
    conn.close()


def _delete_goal_detail(goal_id: int, kind: str):
    """
    Delete the detail row from whichever subtype table corresponds to this kind.
    Called inside delete_goal().
    """
    conn = get_connection()
    cur = conn.cursor()

    if kind == "sum":
        cur.execute("DELETE FROM goal_sum WHERE goal_id = ?", (goal_id,))
    elif kind == "count":
        cur.execute("DELETE FROM goal_count WHERE goal_id = ?", (goal_id,))
    elif kind == "bool":
        cur.execute("DELETE FROM goal_bool WHERE goal_id = ?", (goal_id,))
    elif kind == "streak":
        cur.execute("DELETE FROM goal_streak WHERE goal_id = ?", (goal_id,))
    elif kind == "duration":
        cur.execute("DELETE FROM goal_duration WHERE goal_id = ?", (goal_id,))
    elif kind == "milestone":
        cur.execute("DELETE FROM goal_milestone WHERE goal_id = ?", (goal_id,))
    elif kind == "reduction":
        cur.execute("DELETE FROM goal_reduction WHERE goal_id = ?", (goal_id,))
    elif kind == "range":
        cur.execute("DELETE FROM goal_range WHERE goal_id = ?", (goal_id,))
    elif kind == "percentage":
        cur.execute("DELETE FROM goal_percentage WHERE goal_id = ?", (goal_id,))
    elif kind == "replacement":
        cur.execute(
            "DELETE FROM goal_replacement WHERE goal_id = ?", (goal_id,))
    # else: unsupported kind—no detail to delete

    conn.commit()
    conn.close()


def _select_goal_detail(goal_id: int, kind: str) -> Dict[str, Any]:
    """
    Fetch exactly the detail row for this goal_id from the correct subtype table,
    and return a dict of those fields. If no row exists (e.g. a bool goal has no
    additional columns beyond existence), return {}.
    """
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
        # no columns to fetch; existence is enough
        conn.close()
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
            "SELECT min_amount, max_amount, unit, mode FROM goal_range WHERE goal_id = ?",
            (goal_id,)
        )
    elif kind == "percentage":
        cur.execute(
            "SELECT target_percentage, current_percentage FROM goal_percentage WHERE goal_id = ?",
            (goal_id,)
        )
    elif kind == "replacement":
        cur.execute(
            "SELECT old_behavior, new_behavior FROM goal_replacement WHERE goal_id = ?",
            (goal_id,)
        )
    else:
        conn.close()
        raise ValueError(f"Unsupported goal kind: {kind}")

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


# ───────────────────────────────────────────────────────────────────────────────
# PUBLIC CRUD APIs (CLIENT/HOST‐SYNC‐AWARE)
# ───────────────────────────────────────────────────────────────────────────────

def get_goals_for_tracker(tracker_id: int) -> List[Goal]:
    """
    Return all fully‐populated Goal objects for a given tracker_id.
    In CLIENT mode, pull only changed goals since last sync first.
    """
    if should_sync():
        _pull_changed_goals_from_host()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1) Select core rows
    cursor.execute("SELECT * FROM goals WHERE tracker_id = ?", (tracker_id,))
    core_rows = cursor.fetchall()

    results: List[Goal] = []
    for core in core_rows:
        row_dict = dict(core)
        goal_id = row_dict["id"]
        kind = row_dict["kind"]

        # 2) Fetch the detail columns from the correct subtype table:
        if kind == "sum":
            cursor.execute(
                "SELECT amount, unit FROM goal_sum WHERE goal_id = ?", (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["amount"] = det["amount"]
                row_dict["unit"] = det["unit"]

        elif kind == "count":
            cursor.execute(
                "SELECT amount, unit FROM goal_count WHERE goal_id = ?", (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["amount"] = det["amount"]
                row_dict["unit"] = det["unit"]

        elif kind == "bool":
            # no extra fields
            pass

        elif kind == "streak":
            cursor.execute(
                "SELECT target_streak FROM goal_streak WHERE goal_id = ?", (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["target_streak"] = det["target_streak"]

        elif kind == "duration":
            cursor.execute(
                "SELECT amount, unit FROM goal_duration WHERE goal_id = ?", (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["amount"] = det["amount"]
                row_dict["unit"] = det["unit"]

        elif kind == "milestone":
            cursor.execute(
                "SELECT target, unit FROM goal_milestone WHERE goal_id = ?", (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["target"] = det["target"]
                row_dict["unit"] = det["unit"]

        elif kind == "reduction":
            cursor.execute(
                "SELECT amount, unit FROM goal_reduction WHERE goal_id = ?", (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["amount"] = det["amount"]
                row_dict["unit"] = det["unit"]

        elif kind == "range":
            cursor.execute(
                "SELECT min_amount, max_amount, unit, mode FROM goal_range WHERE goal_id = ?",
                (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["min_amount"] = det["min_amount"]
                row_dict["max_amount"] = det["max_amount"]
                row_dict["unit"] = det["unit"]
                row_dict["mode"] = det["mode"]

        elif kind == "percentage":
            cursor.execute(
                "SELECT target_percentage, current_percentage FROM goal_percentage WHERE goal_id = ?",
                (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["target_percentage"] = det["target_percentage"]
                row_dict["current_percentage"] = det["current_percentage"]

        elif kind == "replacement":
            cursor.execute(
                "SELECT old_behavior, new_behavior FROM goal_replacement WHERE goal_id = ?",
                (goal_id,))
            det = cursor.fetchone()
            if det:
                row_dict["old_behavior"] = det["old_behavior"]
                row_dict["new_behavior"] = det["new_behavior"]

        # 3) Now that `row_dict` has both core + detail columns, convert to dataclass
        results.append(goal_from_row(row_dict))

    conn.close()
    return results


def get_goal_by_uid(uid_val: str) -> Optional[Goal]:
    if should_sync():
        _pull_changed_goals_from_host()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM goals WHERE uid = ?", (uid_val,))
    core = cursor.fetchone()
    if not core:
        conn.close()
        return None

    row_dict = dict(core)
    goal_id = row_dict["id"]
    kind = row_dict["kind"]

    # Fetch detail columns exactly as in get_goals_for_tracker
    if kind == "sum":
        cursor.execute(
            "SELECT amount, unit FROM goal_sum WHERE goal_id = ?", (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["amount"] = det["amount"]
            row_dict["unit"] = det["unit"]

    elif kind == "count":
        cursor.execute(
            "SELECT amount, unit FROM goal_count WHERE goal_id = ?", (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["amount"] = det["amount"]
            row_dict["unit"] = det["unit"]

    elif kind == "bool":
        pass

    elif kind == "streak":
        cursor.execute(
            "SELECT target_streak FROM goal_streak WHERE goal_id = ?", (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["target_streak"] = det["target_streak"]

    elif kind == "duration":
        cursor.execute(
            "SELECT amount, unit FROM goal_duration WHERE goal_id = ?", (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["amount"] = det["amount"]
            row_dict["unit"] = det["unit"]

    elif kind == "milestone":
        cursor.execute(
            "SELECT target, unit FROM goal_milestone WHERE goal_id = ?", (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["target"] = det["target"]
            row_dict["unit"] = det["unit"]

    elif kind == "reduction":
        cursor.execute(
            "SELECT amount, unit FROM goal_reduction WHERE goal_id = ?", (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["amount"] = det["amount"]
            row_dict["unit"] = det["unit"]

    elif kind == "range":
        cursor.execute(
            "SELECT min_amount, max_amount, unit, mode FROM goal_range WHERE goal_id = ?",
            (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["min_amount"] = det["min_amount"]
            row_dict["max_amount"] = det["max_amount"]
            row_dict["unit"] = det["unit"]
            row_dict["mode"] = det["mode"]

    elif kind == "percentage":
        cursor.execute(
            "SELECT target_percentage, current_percentage FROM goal_percentage WHERE goal_id = ?",
            (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["target_percentage"] = det["target_percentage"]
            row_dict["current_percentage"] = det["current_percentage"]

    elif kind == "replacement":
        cursor.execute(
            "SELECT old_behavior, new_behavior FROM goal_replacement WHERE goal_id = ?",
            (goal_id,))
        det = cursor.fetchone()
        if det:
            row_dict["old_behavior"] = det["old_behavior"]
            row_dict["new_behavior"] = det["new_behavior"]

    conn.close()
    return goal_from_row(row_dict)


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


def update_goal(goal_id: int, updates: Dict[str, Any]) -> Optional[Goal]:
    """
    Update a goal by numeric ID.

    • HOST/DIRECT mode:
        1) Update the core 'goals' table (only the 5 core columns) via update_record(...)
        2) Update the detail row in the appropriate subtype table (via _update_goal_detail)
        3) Return the fully populated Goal dataclass (via get_goal_by_id)

    • CLIENT mode:
        1) Update local core columns (goals table) via update_record(...)
        2) Update the detail row locally (_update_goal_detail)
        3) Fetch the entire updated goal row from local DB
        4) Pop off the numeric "id" and queue a sync‐"update" by UID (full payload dict)
        5) process_sync_queue()
        6) Return the updated Goal dataclass
    """

    # 1) If we are running in direct/host mode, just update and return
    if is_direct_db_mode():
        # a) Only update the core columns in 'goals' table
        core_fields = [f for f in get_goal_fields() if f != "id"]
        core_updates = {k: updates[k] for k in core_fields if k in updates}
        if core_updates:
            update_record("goals", goal_id, core_updates)

        # b) Now update the detail row (in whichever subtype table) if any detail fields are present
        _update_goal_detail(goal_id, updates)

        # c) Return the fully populated Goal dataclass
        return get_goal_by_id(goal_id)

    # 2) CLIENT mode: update locally, then queue a full‐payload sync by UID
    else:
        # a) Update core columns locally
        core_fields = [f for f in get_goal_fields() if f != "id"]
        core_updates = {k: updates[k] for k in core_fields if k in updates}
        if core_updates:
            update_record("goals", goal_id, core_updates)

        # b) Update the detail row locally
        _update_goal_detail(goal_id, updates)

        # c) Fetch the complete local row now (so we know its UID + all fields)
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # d) Convert to dict, drop the numeric "id", then queue a sync‐update by UID
        full_payload = dict(row)
        full_payload.pop("id", None)

        queue_sync_operation("goals", "update", full_payload)
        process_sync_queue()

        # e) Return the updated Goal dataclass
        return goal_from_row(row)


def delete_goal(goal_id: int) -> bool:
    """
    Delete a goal by numeric ID. ON DELETE CASCADE takes care of subtype rows.
    In CLIENT mode, queue a “delete” by uid.
    """
    # 1) Fetch core row to get uid & kind
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    row_dict = dict(row)
    uid_val = row_dict["uid"]
    kind = row_dict["kind"]
    conn.close()

    # 2) Delete from “goals”; ON DELETE CASCADE removes detail row
    conn2 = get_connection()
    cur2 = conn2.cursor()
    cur2.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn2.commit()
    conn2.close()

    # 3) If CLIENT, queue a “delete” by uid
    if not is_direct_db_mode():
        queue_sync_operation("goals", "delete", {"uid": uid_val})
        process_sync_queue()

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
    This function has to:
      1. Look up local “goals” row by uid.
      2. If exists → UPDATE core + UPDATE detail (via _update_goal_detail)
         If not exists → INSERT core + INSERT detail (via _insert_goal_detail)
    """
    uid_val = data.get("uid")
    if not uid_val:
        return

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, kind FROM goals WHERE uid = ?", (uid_val,))
    existing = cur.fetchone()

    core_fields = _get_core_goal_fields()
    if existing:
        local_id = existing["id"]
        old_kind = existing["kind"]

        # 1) Update core fields (title, kind, period, tracker_id, etc.)
        updates = {k: data[k] for k in core_fields if k in data}
        if updates:
            update_record("goals", local_id, updates)

        # 2) If kind changed, delete old detail and insert new; else update detail
        new_kind = data["kind"]
        if new_kind != old_kind:
            _delete_goal_detail(local_id, old_kind)
            _insert_goal_detail(local_id, data)
        else:
            _update_goal_detail(local_id, data)
    else:
        # 1) Insert new core row
        add_record("goals", data, core_fields)
        # 2) Get new ID
        cur.execute("SELECT id FROM goals WHERE uid = ?", (uid_val,))
        row_new = cur.fetchone()
        new_id = row_new["id"]
        # 3) Insert detail row
        _insert_goal_detail(new_id, data)

    conn.close()


def get_goal_by_id(goal_id: int) -> Optional[Goal]:
    """
    Helper to fetch by numeric ID (server‐only or local).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
    row = cursor.fetchone()
    conn.close()
    return goal_from_row(row) if row else None


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
