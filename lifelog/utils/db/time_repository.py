import logging
import uuid
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from lifelog.utils.db.db_helper import (
    safe_execute,
    safe_query,
    fetch_from_server,
    get_last_synced,
    set_last_synced,
    should_sync,
    is_direct_db_mode,
    queue_sync_operation,
    process_sync_queue,
)
from lifelog.utils.db.database_manager import add_record, update_record
from lifelog.utils.db.models import TimeLog, time_log_from_row, fields as dataclass_fields

logger = logging.getLogger(__name__)


def _pull_changed_time_logs_from_host() -> None:
    if not should_sync():
        return

    # 1) push any queued local changes
    try:
        process_sync_queue()
    except Exception as e:
        logger.error("Error pushing queued time log changes: %s",
                     e, exc_info=True)

    # 2) fetch since last sync
    try:
        last_ts = get_last_synced("time_history")
    except Exception as e:
        logger.error(
            "Error getting last_synced for time_history: %s", e, exc_info=True)
        last_ts = None

    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) fetch remote list
    try:
        remote_list = fetch_from_server("time/entries", params=params) or []
    except Exception as e:
        logger.error("Failed to fetch changed time logs: %s", e, exc_info=True)
        return

    # 4) upsert each
    for remote in remote_list:
        try:
            upsert_local_time_log(remote)
        except Exception as e:
            logger.error("Failed to upsert remote time log %s: %s",
                         remote.get("uid"), e, exc_info=True)

    # 5) update last_synced
    try:
        set_last_synced("time_history", datetime.utcnow().isoformat())
    except Exception as e:
        logger.error(
            "Failed to set last_synced for time_history: %s", e, exc_info=True)


def _get_all_time_field_names() -> List[str]:
    try:
        return [f.name for f in dataclass_fields(TimeLog) if f.name != "id"]
    except Exception as e:
        logger.error("Error retrieving time field names: %s", e, exc_info=True)
        return []


def upsert_local_time_log(data: Dict[str, Any]) -> None:
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning("Cannot upsert time log without uid")
        return

    # check exists
    rows = safe_query("SELECT id FROM time_history WHERE uid = ?", (uid_val,))
    fields = _get_all_time_field_names()

    if rows:
        local_id = rows[0]["id"]
        updates = {k: data[k] for k in fields if k in data}
        try:
            update_record("time_history", local_id, updates)
        except Exception as e:
            logger.error("Failed to update time_history id=%d: %s",
                         local_id, e, exc_info=True)
    else:
        try:
            add_record("time_history", data, fields)
        except Exception as e:
            logger.error("Failed to insert time_history uid=%s: %s",
                         uid_val, e, exc_info=True)


def get_all_time_logs(since: Optional[Union[str, datetime]] = None) -> List[TimeLog]:
    if should_sync():
        try:
            _pull_changed_time_logs_from_host()
        except Exception as e:
            logger.error(
                "Error pulling time logs before get_all: %s", e, exc_info=True)

    if since:
        since_iso = since.isoformat() if isinstance(since, datetime) else str(since)
        rows = safe_query(
            "SELECT * FROM time_history WHERE start >= ? ORDER BY start ASC",
            (since_iso,)
        )
    else:
        rows = safe_query("SELECT * FROM time_history ORDER BY start ASC")

    result: List[TimeLog] = []
    for r in rows:
        try:
            result.append(time_log_from_row(dict(r)))
        except Exception as e:
            logger.error("Failed to parse TimeLog row %s: %s",
                         dict(r), e, exc_info=True)
    return result


def get_time_log_by_uid(uid_val: str) -> Optional[TimeLog]:
    if should_sync():
        try:
            _pull_changed_time_logs_from_host()
        except Exception as e:
            logger.error(
                "Error pulling time logs before get_by_uid: %s", e, exc_info=True)

    rows = safe_query("SELECT * FROM time_history WHERE uid = ?", (uid_val,))
    if not rows:
        return None
    try:
        return time_log_from_row(dict(rows[0]))
    except Exception as e:
        logger.error("Failed to convert row to TimeLog for uid=%s: %s",
                     uid_val, e, exc_info=True)
        return None


def get_active_time_entry() -> Optional[TimeLog]:
    rows = safe_query(
        "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1"
    )
    if not rows:
        return None
    try:
        return time_log_from_row(dict(rows[0]))
    except Exception as e:
        logger.error("Failed to parse active TimeLog: %s", e, exc_info=True)
        return None


def start_time_entry(data: Dict[str, Any]) -> TimeLog:
    from lifelog.utils.shared_utils import now_utc
    # normalize start
    start_val = data.get("start")
    if isinstance(start_val, datetime):
        data["start"] = start_val.isoformat()
    elif not start_val:
        data["start"] = now_utc().isoformat()

    # assign uid
    data.setdefault("uid", str(uuid.uuid4()))

    # insert locally
    fields = _get_all_time_field_names()
    add_record("time_history", data, fields)

    # fetch new row
    rows = safe_query(
        "SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
    if not rows:
        raise RuntimeError(
            f"Inserted time entry not found for uid={data['uid']}")
    new_log = time_log_from_row(dict(rows[0]))

    # sync if needed
    if not is_direct_db_mode() and should_sync():
        try:
            queue_sync_operation("time_history", "create", data)
            process_sync_queue()
        except Exception as e:
            logger.error("Failed to sync new time entry uid=%s: %s",
                         data["uid"], e, exc_info=True)

    return new_log


def stop_active_time_entry(
    end_time: Union[datetime, str],
    tags: Optional[str] = None,
    notes: Optional[str] = None
) -> TimeLog:
    # normalize end_time
    if isinstance(end_time, str):
        end_dt = datetime.fromisoformat(end_time)
    else:
        end_dt = end_time

    active = get_active_time_entry()
    if not active:
        raise RuntimeError("No active time entry to stop.")

    start_dt = datetime.fromisoformat(active.start)
    end_iso = end_dt.isoformat()
    duration = max(0.0, (end_dt - start_dt).total_seconds() / 60.0)
    updates: Dict[str, Any] = {"end": end_iso, "duration_minutes": duration}
    if tags is not None:
        updates["tags"] = tags
    if notes is not None:
        updates["notes"] = notes

    # local update
    update_record("time_history", active.id, updates)

    # fetch updated
    updated = get_time_log_by_uid(active.uid)
    if updated is None:
        raise RuntimeError(
            f"Failed to retrieve stopped entry uid={active.uid}")

    # sync if needed
    if not is_direct_db_mode() and should_sync():
        payload = {**vars(updated)}
        queue_sync_operation("time_history", "update", payload)
        process_sync_queue()

    return updated


def add_time_entry(data: Dict[str, Any]) -> TimeLog:
    # normalize datetimes
    if isinstance(data.get("start"), datetime):
        data["start"] = data["start"].isoformat()
    if isinstance(data.get("end"), datetime):
        data["end"] = data["end"].isoformat()

    # compute duration if needed
    if data.get("end") and data.get("duration_minutes") is None:
        st = datetime.fromisoformat(data["start"])
        ed = datetime.fromisoformat(data["end"])
        data["duration_minutes"] = max(0.0, (ed - st).total_seconds() / 60.0)

    # assign uid
    data.setdefault("uid", str(uuid.uuid4()))

    # insert locally
    fields = _get_all_time_field_names()
    add_record("time_history", data, fields)

    # fetch new
    rows = safe_query(
        "SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
    if not rows:
        raise RuntimeError(
            f"Inserted time entry not found for uid={data['uid']}")
    new_log = time_log_from_row(dict(rows[0]))

    # sync
    if not is_direct_db_mode() and should_sync():
        queue_sync_operation("time_history", "create", data)
        process_sync_queue()

    return new_log


def update_time_entry(entry_id: int, **updates) -> Optional[TimeLog]:
    # fetch existing to get uid
    rows = safe_query("SELECT uid FROM time_history WHERE id = ?", (entry_id,))
    if not rows:
        raise ValueError(f"Time entry ID {entry_id} not found.")
    uid_val = rows[0]["uid"]

    # local update
    update_record("time_history", entry_id, updates)

    # sync if needed
    if not is_direct_db_mode() and should_sync():
        # build full payload
        full = safe_query(
            "SELECT * FROM time_history WHERE id = ?", (entry_id,))
        payload = dict(full[0]) if full else {"id": entry_id, **updates}
        queue_sync_operation("time_history", "update", payload)
        process_sync_queue()

    # return updated
    return get_time_log_by_uid(uid_val)


def delete_time_entry(entry_id: int) -> None:
    # fetch uid
    rows = safe_query("SELECT uid FROM time_history WHERE id = ?", (entry_id,))
    uid_val = rows[0]["uid"] if rows else None

    # delete locally
    safe_execute("DELETE FROM time_history WHERE id = ?", (entry_id,))

    # sync if needed
    if not is_direct_db_mode() and should_sync():
        payload = {"uid": uid_val} if uid_val else {"id": entry_id}
        queue_sync_operation("time_history", "delete", payload)
        process_sync_queue()


# ─ Host‐only helpers ────────────────────────────────────────────────────────────

def update_time_log_by_uid(uid_val: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    cols = ", ".join(f"{k}=?" for k in updates if k != "id")
    params = tuple(v for k, v in updates.items() if k != "id") + (uid_val,)
    safe_execute(f"UPDATE time_history SET {cols} WHERE uid = ?", params)


def delete_time_log_by_uid(uid_val: str) -> None:
    safe_execute("DELETE FROM time_history WHERE uid = ?", (uid_val,))


def add_distracted_minutes_to_active(mins: float) -> float:
    active = get_active_time_entry()
    if not active:
        raise RuntimeError("No active entry to add distracted minutes.")
    current = active.distracted_minutes or 0.0
    new_total = current + float(mins)
    update_time_entry(active.id, distracted_minutes=new_total)
    return new_total
