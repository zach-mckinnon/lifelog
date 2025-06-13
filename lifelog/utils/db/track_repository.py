from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import logging
import uuid

from lifelog.utils.db.database_manager import add_record, update_record
from lifelog.utils.db.models import (
    Tracker, TrackerEntry, Goal,
    tracker_from_row, entry_from_row, goal_from_row,
    get_tracker_fields, get_goal_fields
)
from lifelog.utils.db.db_helper import (
    safe_query, safe_execute,
    fetch_from_server, get_last_synced, set_last_synced,
    should_sync, is_direct_db_mode,
    queue_sync_operation, process_sync_queue
)

logger = logging.getLogger(__name__)


def _get_all_tracker_field_names() -> List[str]:
    return [f for f in get_tracker_fields() if f != "id"]


def _get_all_goal_field_names() -> List[str]:
    return [f for f in get_goal_fields() if f != "id"]


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
        set_last_synced("trackers", datetime.utcnow().isoformat())
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
        set_last_synced("goals", datetime.utcnow().isoformat())
    except Exception as e:
        logger.error("Goals pull: set_last_synced failed: %s",
                     e, exc_info=True)


def upsert_local_tracker(data: Dict[str, Any]) -> None:
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning("upsert_local_tracker: missing uid")
        return

    rows = safe_query("SELECT id FROM trackers WHERE uid = ?", (uid_val,))
    fields = _get_all_tracker_field_names()

    if rows:
        local_id = rows[0]["id"]
        updates = {k: data[k] for k in fields if k in data}
        if updates:
            try:
                update_record("trackers", local_id, updates)
            except Exception as e:
                logger.error(
                    "upsert_local_tracker: update failed: %s", e, exc_info=True)
    else:
        try:
            add_record("trackers", data, fields)
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


def get_all_trackers(
    title_contains: Optional[str] = None,
    category: Optional[str] = None
) -> List[Tracker]:
    if should_sync():
        _pull_changed_trackers_from_host()

    query = "SELECT * FROM trackers WHERE 1=1"
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


def get_tracker_by_id(tracker_id: int) -> Optional[Tracker]:
    if should_sync():
        _pull_changed_trackers_from_host()

    rows = safe_query("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    return tracker_from_row(dict(rows[0])) if rows else None


def get_tracker_by_uid(uid_val: str) -> Optional[Tracker]:
    if should_sync():
        _pull_changed_trackers_from_host()

    rows = safe_query("SELECT * FROM trackers WHERE uid = ?", (uid_val,))
    return tracker_from_row(dict(rows[0])) if rows else None


def add_tracker(tracker_data: Any) -> Tracker:
    # normalize
    data = tracker_data.to_dict() if hasattr(
        tracker_data, "to_dict") else dict(tracker_data)
    data.setdefault("created", datetime.utcnow().isoformat())
    data.setdefault("uid", str(uuid.uuid4()))
    fields = _get_all_tracker_field_names()
    add_record("trackers", data, fields)

    # re-fetch
    rows = safe_query("SELECT * FROM trackers WHERE uid = ?", (data["uid"],))
    new = tracker_from_row(dict(rows[0]))

    if not is_direct_db_mode() and should_sync():
        queue_sync_operation("trackers", "create", data)
        process_sync_queue()

    return new


def update_tracker(tracker_id: int, updates: Dict[str, Any]) -> Optional[Tracker]:
    if is_direct_db_mode():
        update_record("trackers", tracker_id, updates)
        return get_tracker_by_id(tracker_id)

    # client mode
    update_record("trackers", tracker_id, updates)
    rows = safe_query("SELECT * FROM trackers WHERE id = ?", (tracker_id,))
    full = dict(rows[0])
    queue_sync_operation("trackers", "update", full)
    process_sync_queue()
    return tracker_from_row(full)


def delete_tracker(tracker_id: int) -> bool:
    rows = safe_query("SELECT uid FROM trackers WHERE id = ?", (tracker_id,))
    if not rows:
        return False
    uid_val = rows[0]["uid"]
    safe_execute("DELETE FROM trackers WHERE id = ?", (tracker_id,))

    if not is_direct_db_mode() and should_sync():
        queue_sync_operation("trackers", "delete", {"uid": uid_val})
        process_sync_queue()

    return True


def add_tracker_entry(tracker_id: int, timestamp: Union[str, datetime], value: float) -> TrackerEntry:
    ts_str = timestamp if isinstance(timestamp, str) else timestamp.isoformat()
    # use safe_execute for insert
    cur = safe_execute(
        "INSERT INTO tracker_entries (tracker_id, timestamp, value) VALUES (?, ?, ?)",
        (tracker_id, ts_str, value)
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


def get_goals_for_tracker(tracker_id: int) -> List[Goal]:
    if should_sync():
        _pull_changed_goals_from_host()

    rows = safe_query(
        "SELECT * FROM goals WHERE tracker_id = ?", (tracker_id,))
    result: List[Goal] = []
    for core in rows:
        core_d = dict(core)
        # detail fetch omitted for brevity
        result.append(goal_from_row(core_d))
    return result


def get_goal_by_id(goal_id: int) -> Optional[Goal]:
    rows = safe_query("SELECT * FROM goals WHERE id = ?", (goal_id,))
    if not rows:
        return None
    d = dict(rows[0])
    # detail fetch omitted for brevity
    return goal_from_row(d)


def add_goal(tracker_id: int, goal_data: Dict[str, Any]) -> Goal:
    data = goal_data.copy()
    data["tracker_id"] = tracker_id
    data.setdefault("uid", str(uuid.uuid4()))
    core_fields = _get_all_goal_field_names()
    add_record("goals", data, core_fields)

    rows = safe_query("SELECT id FROM goals WHERE uid = ?", (data["uid"],))
    new_id = rows[0]["id"]
    # detail insertion omitted for brevity

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
