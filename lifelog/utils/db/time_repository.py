import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from lifelog.utils.db import (
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
from lifelog.utils.db import add_record, update_record
from lifelog.utils.db.models import TimeLog, time_log_from_row, fields as dataclass_fields
from lifelog.utils.shared_utils import now_utc, parse_date_string, to_utc

logger = logging.getLogger(__name__)


def _get_all_time_field_names() -> List[str]:
    try:
        return [f.name for f in dataclass_fields(TimeLog) if f.name != "id"]
    except Exception as e:
        logger.error("Error retrieving time field names: %s", e, exc_info=True)
        return []

# Pull changed time logs from host, using updated_at and deleted


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
        # Use the sync endpoint path: '/sync/time_history'
        remote_list = fetch_from_server("time_history", params=params) or []
    except Exception as e:
        logger.error("Failed to fetch changed time logs: %s", e, exc_info=True)
        return
    # 4) upsert each from server payload
    for remote in remote_list:
        try:
            upsert_local_time_log(remote)
        except Exception as e:
            logger.error("Failed to upsert remote time log %s: %s",
                         remote.get("uid"), e, exc_info=True)
    # 5) update last_synced
    try:
        set_last_synced("time_history", datetime.now().isoformat())
    except Exception as e:
        logger.error(
            "Failed to set last_synced for time_history: %s", e, exc_info=True)


# Upsert local time log from server payload, handling updated_at and deleted flags
def upsert_local_time_log(data: Dict[str, Any]) -> None:
    uid_val = data.get("uid")
    if not uid_val:
        logger.warning("Cannot upsert time log without uid")
        return
    # Prepare updates/inserts: parse deleted and updated_at
    # Ensure deleted is 0/1
    if 'deleted' in data:
        try:
            data['deleted'] = 1 if data.get('deleted') else 0
        except Exception:
            data.pop('deleted', None)
    # updated_at: assume ISO string; leave as is, normalize_for_db will handle
    # Normalize datetime fields: start, end if present
    if 'start' in data and isinstance(data['start'], str):
        # leave as ISO string
        pass
    if 'end' in data and isinstance(data['end'], str):
        pass
    # Check existence
    rows = safe_query("SELECT id FROM time_history WHERE uid = ?", (uid_val,))
    fields = _get_all_time_field_names()
    if rows:
        local_id = rows[0]["id"]
        updates = {k: data[k] for k in fields if k in data}
        # Ensure updated_at included if present
        if updates:
            try:
                update_record("time_history", local_id, updates)
            except Exception as e:
                logger.error(
                    "upsert_local_time_log: update failed id=%d: %s", local_id, e, exc_info=True)
    else:
        # Insert new record
        try:
            now_iso = datetime.now().isoformat()
            record: Dict[str, Any] = {}
            for k in fields:
                if k in data:
                    record[k] = data[k]
            # Set defaults if missing
            if 'created' in fields:
                # If TimeLog model has created field; otherwise skip
                if 'created' not in record or record.get('created') is None:
                    record['created'] = now_iso
            # UID
            record['uid'] = uid_val
            # updated_at
            if 'updated_at' not in record or record.get('updated_at') is None:
                record['updated_at'] = now_iso
            # deleted
            if 'deleted' not in record:
                record['deleted'] = 0
            add_record("time_history", record, fields)
        except Exception as e:
            logger.error(
                "upsert_local_time_log: insert failed uid=%s: %s", uid_val, e, exc_info=True)


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

    # Prepare all fields before insert:
    fields = _get_all_time_field_names()
    # Ensure every field exists in data, setting None if missing.
    # This avoids KeyError in add_record when data lacks columns like 'end' or 'duration_minutes'.
    for f in fields:
        data.setdefault(f, None)

    # Optional: set updated_at/deleted defaults here if schema expects them on insert.
    # If you want to record creation time:
    now_iso = datetime.now().isoformat()
    if 'updated_at' in fields:
        # If updated_at should default to creation time
        data['updated_at'] = data.get('updated_at') or now_iso
    if 'deleted' in fields:
        # Soft-delete flag default 0
        data['deleted'] = data.get('deleted') if data.get(
            'deleted') is not None else 0

    # insert locally
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


# Add a new time entry: set updated_at and deleted=0
def add_time_entry(data: Dict[str, Any]) -> TimeLog:
    # Normalize datetimes
    if isinstance(data.get("start"), datetime):
        data["start"] = data["start"].isoformat()
    if isinstance(data.get("end"), datetime):
        data["end"] = data["end"].isoformat()
    # Compute duration if needed
    if data.get("end") and data.get("duration_minutes") is None:
        try:
            st = datetime.fromisoformat(data["start"])
            ed = datetime.fromisoformat(data["end"])
            data["duration_minutes"] = max(
                0.0, (ed - st).total_seconds() / 60.0)
        except Exception:
            pass
    # Assign UID
    data.setdefault("uid", str(uuid.uuid4()))
    # Set updated_at and deleted
    now_iso = datetime.now().isoformat()
    data['updated_at'] = now_iso
    data['deleted'] = 0
    # Insert locally
    fields = _get_all_time_field_names()
    for f in fields:
        data.setdefault(f, None)
    add_record("time_history", data, fields)
    # Fetch new
    rows = safe_query(
        "SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
    if not rows:
        raise RuntimeError(
            f"Inserted time entry not found for uid={data['uid']}")
    new_log = time_log_from_row(dict(rows[0]))
    # Sync if needed
    if not is_direct_db_mode() and should_sync():
        payload = data.copy()
        queue_sync_operation("time_history", "create", payload)
        try:
            process_sync_queue()
        except Exception as e:
            logger.error("Failed to sync new time entry uid=%s: %s",
                         data["uid"], e, exc_info=True)
    return new_log


# Update time entry: set updated_at
def update_time_entry(entry_id: int, **updates) -> Optional[TimeLog]:
    # Fetch existing to get uid
    rows = safe_query("SELECT uid FROM time_history WHERE id = ?", (entry_id,))
    if not rows:
        raise ValueError(f"Time entry ID {entry_id} not found.")
    uid_val = rows[0]["uid"]
    # Normalize datetimes
    if 'start' in updates and isinstance(updates['start'], datetime):
        updates['start'] = updates['start'].isoformat()
    if 'end' in updates and isinstance(updates['end'], datetime):
        updates['end'] = updates['end'].isoformat()
    # Compute duration if needed
    if 'end' in updates and updates.get('duration_minutes') is None:
        try:
            st = datetime.fromisoformat(rows and safe_query(
                "SELECT start FROM time_history WHERE id = ?", (entry_id,))[0]['start'])
            ed = datetime.fromisoformat(updates['end'])
            updates['duration_minutes'] = max(
                0.0, (ed - st).total_seconds() / 60.0)
        except Exception:
            pass
    # Set updated_at
    updates['updated_at'] = datetime.now().isoformat()
    # Local update
    update_record("time_history", entry_id, updates)
    # Fetch updated
    updated = get_time_log_by_uid(uid_val)
    if updated is None:
        raise RuntimeError(f"Failed to retrieve updated entry uid={uid_val}")
    # Sync if needed
    if not is_direct_db_mode() and should_sync():
        # Build full payload
        # Convert dataclass to dict or row dict
        payload = {**vars(updated)}
        queue_sync_operation("time_history", "update", payload)
        try:
            process_sync_queue()
        except Exception as e:
            logger.error(
                "Failed to sync updated time entry uid=%s: %s", uid_val, e, exc_info=True)
    return updated


# Stop active entry: wrap update_time_entry, but ensure updated_at set
# Existing logic invokes update_time_entry which now sets updated_at

def stop_active_time_entry(
    end_time: Union[datetime, str],
    tags: Optional[str] = None,
    notes: Optional[str] = None
) -> TimeLog:
    """
    Stop the currently active time entry, setting its end, duration, tags, notes,
    and updated_at. Accepts end_time as ISO string or datetime or human-friendly string.
    """
    # 1) Fetch active entry
    active = get_active_time_entry()
    if not active:
        raise RuntimeError("No active time entry to stop.")

    # 2) Normalize start_dt from active.start
    # active.start may be a datetime or ISO string. We ensure datetime and convert to UTC.
    raw_start = getattr(active, "start", None)
    if raw_start is None:
        raise RuntimeError("Active time entry has no start time recorded.")
    if isinstance(raw_start, datetime):
        start_dt = to_utc(raw_start)
    else:
        # assume string: try ISO parse
        try:
            parsed = datetime.fromisoformat(raw_start)
        except Exception:
            # Optionally: try human-friendly parsing
            try:
                parsed = parse_date_string(raw_start, now=now_utc())
            except Exception as e:
                raise ValueError(
                    f"Cannot parse active.start '{raw_start}': {e}")
        start_dt = to_utc(parsed)

    # 3) Normalize end_dt from end_time parameter
    if isinstance(end_time, datetime):
        end_dt = to_utc(end_time)
    else:
        # end_time is a string: try ISO first
        try:
            parsed_end = datetime.fromisoformat(end_time)
        except Exception:
            # Optionally: try human-friendly parsing
            try:
                parsed_end = parse_date_string(end_time, now=now_utc())
            except Exception as e:
                raise ValueError(f"Cannot parse end_time '{end_time}': {e}")
        end_dt = to_utc(parsed_end)

    # 4) Check that end_dt is not before start_dt
    if end_dt < start_dt:
        raise ValueError(
            f"end_time ({end_dt.isoformat()}) is before start time ({start_dt.isoformat()}).")

    # 5) Compute duration in minutes
    duration = (end_dt - start_dt).total_seconds() / 60.0
    # Clamp to zero just in case of tiny negative due to rounding, though above check prevents major negatives
    duration = max(0.0, duration)

    # 6) Prepare update payload
    end_iso = end_dt.isoformat()
    updates: Dict[str, Any] = {
        "end": end_iso,
        "duration_minutes": duration,
        # Explicitly set updated_at to now UTC:
        "updated_at": now_utc().isoformat(),
    }
    if tags is not None:
        updates["tags"] = tags
    if notes is not None:
        updates["notes"] = notes

    # 7) Call update_time_entry, which applies the DB update and sync logic
    return update_time_entry(active.id, **updates)

# Delete time entry: soft-delete instead of hard delete


def delete_time_entry(entry_id: int) -> None:
    # Fetch uid
    rows = safe_query("SELECT uid FROM time_history WHERE id = ?", (entry_id,))
    uid_val = rows[0]["uid"] if rows else None
    # Soft-delete locally: set deleted=1 and updated_at
    now_iso = datetime.now().isoformat()
    safe_execute(
        "UPDATE time_history SET deleted = 1, updated_at = ? WHERE id = ?", (now_iso, entry_id))
    # Sync if needed
    if not is_direct_db_mode() and should_sync() and uid_val:
        payload = {"uid": uid_val, "deleted": True, "updated_at": now_iso}
        queue_sync_operation("time_history", "delete", payload)
        try:
            process_sync_queue()
        except Exception as e:
            logger.error(
                "Failed to sync deleted time entry uid=%s: %s", uid_val, e, exc_info=True)


# ─ Host‐only helpers ────────────────────────────────────────────────────────────


def update_time_log_by_uid(uid_val: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    # Set updated_at
    updates['updated_at'] = datetime.now().isoformat()
    # Normalize datetime fields if present
    if 'start' in updates and isinstance(updates['start'], datetime):
        updates['start'] = updates['start'].isoformat()
    if 'end' in updates and isinstance(updates['end'], datetime):
        updates['end'] = updates['end'].isoformat()
    cols = ", ".join(f"{k}=?" for k in updates if k != "id")
    params = tuple(updates[k] for k in updates if k != "id") + (uid_val,)
    safe_execute(f"UPDATE time_history SET {cols} WHERE uid = ?", params)


def delete_time_log_by_uid(uid_val: str) -> None:
    # Soft-delete on host: set deleted and updated_at
    now_iso = datetime.now().isoformat()
    safe_execute(
        "UPDATE time_history SET deleted = 1, updated_at = ? WHERE uid = ?", (now_iso, uid_val))


def add_distracted_minutes_to_active(mins: float) -> float:
    active = get_active_time_entry()
    if not active:
        raise RuntimeError("No active entry to add distracted minutes.")
    current = active.distracted_minutes or 0.0
    new_total = current + float(mins)
    update_time_entry(active.id, distracted_minutes=new_total)
    return new_total
