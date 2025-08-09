from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import logging
import uuid

from lifelog.utils.db import add_record, update_record
from lifelog.utils.db.models import (
    Tracker, TrackerEntry, Goal,
    tracker_from_row, entry_from_row, goal_from_row,
    get_tracker_fields, get_goal_fields
)
from lifelog.utils.db import (
    safe_query, safe_execute,
    fetch_from_server, get_last_synced, set_last_synced,
    should_sync, is_direct_db_mode,
    queue_sync_operation, process_sync_queue
)
from lifelog.utils.db.db_helper import normalize_for_db

logger = logging.getLogger(__name__)


def _get_all_tracker_field_names() -> List[str]:
    # Now get_tracker_fields includes 'updated_at' and 'deleted'
    return [f for f in get_tracker_fields() if f != "id"]


def _get_all_goal_field_names() -> List[str]:
    return [f for f in get_goal_fields() if f != "id"]


# Pull changed trackers from host, unchanged but upsert_local_tracker will handle updated_at/deleted
def _pull_changed_trackers_from_host() -> None:
    if not should_sync():
        return
    try:
        process_sync_queue()
    except Exception as e:
        logger.error(
            "Trackers pull: process_sync_queue failed: %s", e, exc_info=True)
    try:
        last_ts = get_last_synced("trackers")
    except Exception as e:
        logger.error("Trackers pull: get_last_synced failed: %s",
                     e, exc_info=True)
        last_ts = None
    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts
    try:
        remote_list = fetch_from_server("trackers", params=params) or []
    except Exception as e:
        logger.error("Trackers pull: fetch_from_server failed: %s",
                     e, exc_info=True)
        remote_list = []
    for remote in remote_list:
        try:
            upsert_local_tracker(remote)
        except Exception as e:
            logger.error(
                "Trackers pull: upsert_local_tracker failed: %s", e, exc_info=True)
    try:
        set_last_synced("trackers", datetime.now().isoformat())
    except Exception as e:
        logger.error("Trackers pull: set_last_synced failed: %s",
                     e, exc_info=True)


def _pull_changed_goals_from_host() -> None:
    if not should_sync():
        return

    try:
        process_sync_queue()
    except Exception as e:
        logger.error("Goals pull: process_sync_queue failed: %s",
                     e, exc_info=True)

    try:
        last_ts = get_last_synced("goals")
    except Exception as e:
        logger.error("Goals pull: get_last_synced failed: %s",
                     e, exc_info=True)
        last_ts = None

    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    try:
        remote_list = fetch_from_server("goals", params=params) or []
    except Exception as e:
        logger.error("Goals pull: fetch_from_server failed: %s",
                     e, exc_info=True)
        remote_list = []

    for remote in remote_list:
        try:
            upsert_local_goal(remote)
        except Exception as e:
            logger.error(
                "Goals pull: upsert_local_goal failed: %s", e, exc_info=True)

    try:
        set_last_synced("goals", datetime.now().isoformat())
    except Exception as e:
        logger.error("Goals pull: set_last_synced failed: %s",
                     e, exc_info=True)


# Upsert local tracker from server payload, handling updated_at and deleted
def upsert_local_tracker(data: Dict[str, Any]) -> None:
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning("upsert_local_tracker: missing uid")
        return
    # Ensure status of fields: parse updated_at and deleted if present
    # Convert updated_at to ISO or leave as string; normalize_for_db will handle
    # Convert deleted to 0/1
    if 'deleted' in data:
        try:
            data['deleted'] = 1 if data.get('deleted') else 0
        except Exception:
            data.pop('deleted', None)
    if 'updated_at' in data:
        # assume ISO string; leave as is
        pass
    rows = safe_query("SELECT id FROM trackers WHERE uid = ?", (uid_val,))
    fields = _get_all_tracker_field_names()
    if rows:
        local_id = rows[0]["id"]
        # Prepare updates: include only fields present
        updates = {k: data[k] for k in fields if k in data}
        if updates:
            # Ensure updated_at included if present
            try:
                update_record("trackers", local_id, normalize_for_db(updates))
            except Exception as e:
                logger.error(
                    "upsert_local_tracker: update failed: %s", e, exc_info=True)
    else:
        # Insert: ensure created, updated_at, deleted present
        now = datetime.now()
        record = {}
        for k in fields:
            if k in data:
                record[k] = data[k]
        # Set defaults if missing
        if 'created' not in record or record.get('created') is None:
            record['created'] = now.isoformat()
        if 'uid' not in record:
            record['uid'] = uid_val
        if 'updated_at' not in record or record.get('updated_at') is None:
            record['updated_at'] = now.isoformat()
        if 'deleted' not in record:
            record['deleted'] = 0
        try:
            add_record("trackers", normalize_for_db(record), fields)
        except Exception as e:
            logger.error("upsert_local_tracker: insert failed: %s",
                         e, exc_info=True)


def upsert_local_goal(data: Dict[str, Any]) -> None:
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning("upsert_local_goal: missing uid")
        return

    rows = safe_query("SELECT id, kind FROM goals WHERE uid = ?", (uid_val,))
    core_fields = _get_all_goal_field_names()

    if rows:
        local_id, old_kind = rows[0]["id"], rows[0]["kind"]
        updates = {k: data[k] for k in core_fields if k in data}
        if updates:
            try:
                update_record("goals", local_id, updates)
            except Exception as e:
                logger.error(
                    "upsert_local_goal: core update failed: %s", e, exc_info=True)
        # detail handling omitted for brevity—assume similar to core
    else:
        try:
            add_record("goals", data, core_fields)
        except Exception as e:
            logger.error(
                "upsert_local_goal: core insert failed: %s", e, exc_info=True)
        # detail handling omitted for brevity

# Get tracker by id, ignoring soft-deleted? Business logic may skip deleted trackers


def get_tracker_by_id(tracker_id: int) -> Optional[Tracker]:
    if should_sync():
        _pull_changed_trackers_from_host()
    rows = safe_query(
        "SELECT * FROM trackers WHERE id = ? AND deleted = 0", (tracker_id,))
    return tracker_from_row(dict(rows[0])) if rows else None

# Get by uid similarly


def get_tracker_by_uid(uid_val: str) -> Optional[Tracker]:
    if should_sync():
        _pull_changed_trackers_from_host()
    rows = safe_query(
        "SELECT * FROM trackers WHERE uid = ? AND deleted = 0", (uid_val,))
    return tracker_from_row(dict(rows[0])) if rows else None


def get_tracker_by_title(title: str) -> Optional[Tracker]:
    """Find tracker by exact title match (case-insensitive)."""
    if should_sync():
        _pull_changed_trackers_from_host()
    rows = safe_query(
        "SELECT * FROM trackers WHERE LOWER(title) = LOWER(?) AND deleted = 0", (title,))
    return tracker_from_row(dict(rows[0])) if rows else None


# Fetch all trackers, exclude deleted


def get_all_trackers(
    title_contains: Optional[str] = None,
    category: Optional[str] = None
) -> List[Tracker]:
    if should_sync():
        _pull_changed_trackers_from_host()
    query = "SELECT * FROM trackers WHERE deleted = 0"
    params: List[Any] = []
    if title_contains:
        query += " AND title LIKE ?"
        params.append(f"%{title_contains}%")
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY created DESC"
    rows = safe_query(query, tuple(params))
    return [tracker_from_row(dict(r)) for r in rows]
# Add tracker: set created, updated_at, deleted, serialize any enums if needed


def add_tracker(tracker_data: Any) -> Tracker:
    # Normalize input
    data = tracker_data.to_dict() if hasattr(
        tracker_data, "to_dict") else dict(tracker_data)
    now = datetime.now()
    # Set created
    if data.get("created") is None:
        data["created"] = now.isoformat()
    # UID
    if not data.get("uid"):
        data["uid"] = str(uuid.uuid4())
    # New fields:
    data['updated_at'] = now.isoformat()
    data['deleted'] = 0
    fields = _get_all_tracker_field_names()
    # Write to DB
    add_record("trackers", normalize_for_db(data), fields)
    # Re-fetch
    rows = safe_query("SELECT * FROM trackers WHERE uid = ?", (data["uid"],))
    new = tracker_from_row(dict(rows[0])) if rows else None
    if new and not is_direct_db_mode() and should_sync():
        # Queue full payload including updated_at and deleted
        payload = {k: getattr(new, k) for k in fields if hasattr(new, k)}
        queue_sync_operation("trackers", "create", normalize_for_db(payload))
        process_sync_queue()
    return new

# Update tracker: set updated_at, serialize enums if any, include deleted if provided? Normally update fields


def update_tracker(tracker_id: int, updates: Dict[str, Any]) -> Optional[Tracker]:
    now = datetime.now()
    # Handle any enum fields here (if Tracker.type is enum, convert to .value)
    if 'type' in updates:
        # Example: if there is a TrackerType enum, convert similarly to TaskStatus
        val = updates['type']
        # if isinstance(val, Enum): updates['type'] = val.value
        # else: leave as is or validate
        pass
    # Set updated_at
    updates['updated_at'] = now.isoformat()
    # Optionally handle deleted flag: if user requests deletion via this, but typically delete_tracker handles
    # Normalize and write
    if is_direct_db_mode():
        update_record("trackers", tracker_id, normalize_for_db(updates))
        return get_tracker_by_id(tracker_id)
    # Client mode
    update_record("trackers", tracker_id, normalize_for_db(updates))
    rows = safe_query("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    full = dict(rows[0]) if rows else None
    if full and should_sync():
        queue_sync_operation("trackers", "update", normalize_for_db(full))
        process_sync_queue()
    return tracker_from_row(full) if full else None

# Delete tracker: soft-delete by setting deleted=1 and updated_at, queue delete


def delete_tracker(tracker_id: int) -> bool:
    rows = safe_query("SELECT uid FROM trackers WHERE id = ?", (tracker_id,))
    if not rows:
        return False
    uid_val = rows[0]["uid"]
    # Soft-delete locally: set deleted and updated_at
    now_iso = datetime.now().isoformat()
    safe_execute(
        "UPDATE trackers SET deleted = 1, updated_at = ? WHERE id = ?", (now_iso, tracker_id))
    if not is_direct_db_mode() and should_sync():
        # Payload for delete: include uid, deleted flag, updated_at
        payload = {"uid": uid_val, "deleted": True, "updated_at": now_iso}
        queue_sync_operation("trackers", "delete", payload)
        process_sync_queue()
    return True


def add_tracker_entry(tracker_id: int, timestamp: Union[str, datetime], value: float, notes: Optional[str] = None) -> TrackerEntry:
    import uuid
    ts_str = timestamp if isinstance(timestamp, str) else timestamp.isoformat()
    uid = str(uuid.uuid4())
    # use safe_execute for insert
    cur = safe_execute(
        "INSERT INTO tracker_entries (tracker_id, timestamp, value, notes, uid) VALUES (?, ?, ?, ?, ?)",
        (tracker_id, ts_str, value, notes, uid)
    )
    new_id = cur.lastrowid
    rows = safe_query("SELECT * FROM tracker_entries WHERE id = ?", (new_id,))
    return entry_from_row(dict(rows[0]))


def get_entries_for_tracker(tracker_id: int) -> List[TrackerEntry]:
    rows = safe_query(
        "SELECT * FROM tracker_entries WHERE tracker_id = ? ORDER BY timestamp ASC",
        (tracker_id,)
    )
    return [entry_from_row(dict(r)) for r in rows]


def _fetch_goal_details(goal_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch goal-specific details and merge with core goal data."""
    goal_id = goal_dict["id"]
    kind = goal_dict["kind"]

    if kind in ["sum", "count", "reduction"]:
        detail_rows = safe_query(
            "SELECT * FROM goal_sum WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "amount": detail["amount"],
                "unit": detail.get("unit")
            })
    elif kind == "bool":
        detail_rows = safe_query(
            "SELECT * FROM goal_bool WHERE goal_id = ?", (goal_id,))
        # bool goals don't have additional fields beyond core
    elif kind == "streak":
        detail_rows = safe_query(
            "SELECT * FROM goal_streak WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "target_streak": detail["target_streak"],
                "current_streak": detail.get("current_streak", 0),
                "best_streak": detail.get("best_streak", 0)
            })
    elif kind == "duration":
        detail_rows = safe_query(
            "SELECT * FROM goal_duration WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "amount": detail["amount"],
                "unit": detail.get("unit", "minutes")
            })
    elif kind == "milestone":
        detail_rows = safe_query(
            "SELECT * FROM goal_milestone WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "target": detail["target"],
                "current": detail.get("current", 0),
                "unit": detail.get("unit")
            })
    elif kind == "range":
        detail_rows = safe_query(
            "SELECT * FROM goal_range WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "min_amount": detail["min_amount"],
                "max_amount": detail["max_amount"],
                "unit": detail.get("unit"),
                "mode": detail.get("mode", "goal")
            })
    elif kind == "percentage":
        detail_rows = safe_query(
            "SELECT * FROM goal_percentage WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "target_percentage": detail["target_percentage"],
                "current_percentage": detail.get("current_percentage", 0)
            })
    elif kind == "replacement":
        detail_rows = safe_query(
            "SELECT * FROM goal_replacement WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "old_behavior": detail["old_behavior"],
                "new_behavior": detail["new_behavior"]
            })
    elif kind == "average":
        detail_rows = safe_query(
            "SELECT * FROM goal_average WHERE goal_id = ?", (goal_id,))
        if detail_rows:
            detail = dict(detail_rows[0])
            goal_dict.update({
                "min_expected": detail.get("min_expected"),
                "max_expected": detail.get("max_expected"),
                "outlier_threshold": detail.get("outlier_threshold", 1.5),
                "unit": detail.get("unit")
            })

    return goal_dict


def get_goals_for_tracker(tracker_id: int) -> List[Goal]:
    if should_sync():
        _pull_changed_goals_from_host()

    rows = safe_query(
        "SELECT * FROM goals WHERE tracker_id = ?", (tracker_id,))
    result: List[Goal] = []
    for core in rows:
        core_d = dict(core)
        # Fetch goal-specific details
        goal_d = _fetch_goal_details(core_d)
        result.append(goal_from_row(goal_d))
    return result


def get_goal_by_id(goal_id: int) -> Optional[Goal]:
    rows = safe_query("SELECT * FROM goals WHERE id = ?", (goal_id,))
    if not rows:
        return None
    d = dict(rows[0])
    # Fetch goal-specific details
    goal_d = _fetch_goal_details(d)
    return goal_from_row(goal_d)


def add_goal(tracker_id: int, goal_data: Dict[str, Any]) -> Goal:
    data = goal_data.copy()
    data["tracker_id"] = tracker_id
    data.setdefault("uid", str(uuid.uuid4()))
    core_fields = _get_all_goal_field_names()
    add_record("goals", data, core_fields)

    rows = safe_query("SELECT id FROM goals WHERE uid = ?", (data["uid"],))
    new_id = rows[0]["id"]

    # Insert goal-specific details based on kind
    kind = data.get("kind")
    if kind == "sum" or kind == "count" or kind == "reduction":
        safe_execute("""
            INSERT INTO goal_sum (goal_id, uid, amount, unit) 
            VALUES (?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("amount"), data.get("unit")))
    elif kind == "bool":
        safe_execute("""
            INSERT INTO goal_bool (goal_id, uid) 
            VALUES (?, ?)
        """, (new_id, data["uid"]))
    elif kind == "streak":
        safe_execute("""
            INSERT INTO goal_streak (goal_id, uid, target_streak, current_streak) 
            VALUES (?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("target_streak", 0), 0))
    elif kind == "duration":
        safe_execute("""
            INSERT INTO goal_duration (goal_id, uid, amount, unit) 
            VALUES (?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("amount"), data.get("unit", "minutes")))
    elif kind == "milestone":
        safe_execute("""
            INSERT INTO goal_milestone (goal_id, uid, target, current, unit) 
            VALUES (?, ?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("target"), 0, data.get("unit")))
    elif kind == "range":
        safe_execute("""
            INSERT INTO goal_range (goal_id, uid, min_amount, max_amount, unit, mode) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("min_amount"), data.get("max_amount"),
              data.get("unit"), data.get("mode", "goal")))
    elif kind == "percentage":
        safe_execute("""
            INSERT INTO goal_percentage (goal_id, uid, target_percentage, current_percentage) 
            VALUES (?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("target_percentage"), 0))
    elif kind == "replacement":
        safe_execute("""
            INSERT INTO goal_replacement (goal_id, uid, old_behavior, new_behavior) 
            VALUES (?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("old_behavior"), data.get("new_behavior")))
    elif kind == "average":
        safe_execute("""
            INSERT INTO goal_average (goal_id, uid, min_expected, max_expected, outlier_threshold, unit) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (new_id, data["uid"], data.get("min_expected"), data.get("max_expected"),
              data.get("outlier_threshold", 1.5), data.get("unit")))

    if not is_direct_db_mode() and should_sync():
        queue_sync_operation("goals", "create", data)
        process_sync_queue()

    return get_goal_by_id(new_id)


def update_goal(goal_id: int, updates: Dict[str, Any]) -> Optional[Goal]:
    if is_direct_db_mode():
        update_record("goals", goal_id, updates)
        return get_goal_by_id(goal_id)

    update_record("goals", goal_id, updates)
    rows = safe_query("SELECT * FROM goals WHERE id = ?", (goal_id,))
    full = dict(rows[0])
    queue_sync_operation("goals", "update", full)
    process_sync_queue()
    return goal_from_row(full)


def delete_goal(goal_id: int) -> bool:
    rows = safe_query("SELECT uid FROM goals WHERE id = ?", (goal_id,))
    if not rows:
        return False
    uid_val = rows[0]["uid"]
    safe_execute("DELETE FROM goals WHERE id = ?", (goal_id,))

    if not is_direct_db_mode() and should_sync():
        queue_sync_operation("goals", "delete", {"uid": uid_val})
        process_sync_queue()

    return True


def query_goals(**filters) -> List[Goal]:
    if filters:
        clause = " AND ".join(f"{k}=?" for k in filters)
        rows = safe_query(
            f"SELECT * FROM goals WHERE {clause}", tuple(filters.values()))
    else:
        rows = safe_query("SELECT * FROM goals")
    return [goal_from_row(dict(r)) for r in rows]
