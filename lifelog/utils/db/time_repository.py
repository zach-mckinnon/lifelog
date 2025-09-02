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
from lifelog.utils.core_utils import now_utc, to_utc
from lifelog.utils.error_handler import handle_db_errors, validate_time_entry_data

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
        from lifelog.utils.core_utils import now_utc
        set_last_synced("time_history", now_utc().isoformat())
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


@handle_db_errors("start_time_entry")
def start_time_entry(data: Dict[str, Any]) -> TimeLog:
    """Start a new time entry with validation and error handling."""
    from lifelog.utils.core_utils import now_utc
    
    # Validate data
    data = validate_time_entry_data(data)
    
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
    now_iso = now_utc().isoformat()
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
        # Ensure timezone-aware: if naive, assume UTC
        if end_dt.tzinfo is None:
            from datetime import timezone
            end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        end_dt = end_time
        # Ensure timezone-aware: if naive, assume UTC
        if end_dt.tzinfo is None:
            from datetime import timezone
            end_dt = end_dt.replace(tzinfo=timezone.utc)

    active = get_active_time_entry()
    if not active:
        raise RuntimeError("No active time entry to stop.")

    # Parse stored start (assuming active.start is ISO string)
    if isinstance(active.start, str):
        start_dt = datetime.fromisoformat(active.start)
        # Ensure timezone-aware: if naive, assume UTC
        if start_dt.tzinfo is None:
            from datetime import timezone
            start_dt = start_dt.replace(tzinfo=timezone.utc)
    elif isinstance(active.start, datetime):
        start_dt = active.start
        # Ensure timezone-aware: if naive, assume UTC
        if start_dt.tzinfo is None:
            from datetime import timezone
            start_dt = start_dt.replace(tzinfo=timezone.utc)
    else:
        raise RuntimeError(
            f"Cannot parse start time of active entry: {active.start}")

    # Check that end >= start
    if end_dt < start_dt:
        raise ValueError(
            f"End time {end_dt.isoformat()} is before start time {start_dt.isoformat()}")

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
    from lifelog.utils.core_utils import now_utc
    now_iso = now_utc().isoformat()
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
    # Normalize datetimes in updates
    from datetime import datetime
    norm_updates = {}
    for k, v in updates.items():
        if isinstance(v, datetime):
            norm_updates[k] = v.isoformat()
        else:
            norm_updates[k] = v
    # Possibly check if updating 'end': ensure end >= start, if both known
    if 'end' in norm_updates:
        # fetch existing start to compare
        existing = safe_query(
            "SELECT start FROM time_history WHERE id = ?", (entry_id,))
        if existing:
            try:
                start_dt = datetime.fromisoformat(existing[0]["start"])
                end_dt = datetime.fromisoformat(norm_updates['end'])
                if end_dt < start_dt:
                    raise ValueError(
                        f"End time {end_dt.isoformat()} is before start {start_dt.isoformat()}")
            except Exception as e:
                raise
    # Update locally
    update_record("time_history", entry_id, norm_updates)
    # Fetch updated
    updated = get_time_log_by_uid(...)  # by uid fetched earlier
    if updated is None:
        return None
    # Sync if needed, converting any datetime fields
    if not is_direct_db_mode() and should_sync():
        payload: Dict[str, Any] = {}
        for field_name, value in vars(updated).items():
            if isinstance(value, datetime):
                payload[field_name] = value.isoformat()
            else:
                payload[field_name] = value
        queue_sync_operation("time_history", "update", payload)
        process_sync_queue()
    return updated


# Stop active entry: wrap update_time_entry, but ensure updated_at set
# Existing logic invokes update_time_entry which now sets updated_at


def stop_active_time_entry(
    end_time: Union[datetime, str],
    tags: Optional[str] = None,
    notes: Optional[str] = None
) -> TimeLog:
    # Normalize end_time into a datetime
    if isinstance(end_time, str):
        try:
            end_dt = datetime.fromisoformat(end_time)
        except Exception as e:
            raise ValueError(f"Invalid end_time format: {end_time}") from e
    elif isinstance(end_time, datetime):
        end_dt = end_time
    else:
        raise ValueError("end_time must be a datetime or ISO string")

    active = get_active_time_entry()
    if not active:
        raise RuntimeError("No active time entry to stop.")

    # Parse stored start (assuming active.start is ISO string)
    if isinstance(active.start, str):
        start_dt = datetime.fromisoformat(active.start)
    elif isinstance(active.start, datetime):
        start_dt = active.start
    else:
        raise RuntimeError(
            f"Cannot parse start time of active entry: {active.start}")

    # Check that end >= start
    if end_dt < start_dt:
        raise ValueError(
            f"End time {end_dt.isoformat()} is before start time {start_dt.isoformat()}")

    end_iso = end_dt.isoformat()
    duration = max(0.0, (end_dt - start_dt).total_seconds() / 60.0)
    updates: Dict[str, Any] = {"end": end_iso, "duration_minutes": duration}
    if tags is not None:
        updates["tags"] = tags
    if notes is not None:
        updates["notes"] = notes

    # Update locally
    try:
        update_record("time_history", active.id, updates)
    except Exception as e:
        logging.error("Failed to update time entry stop: %s", e, exc_info=True)
        raise

    # Fetch updated entry
    updated = get_time_log_by_uid(active.uid)
    if updated is None:
        raise RuntimeError(
            f"Failed to retrieve stopped entry uid={active.uid}")

    # Sync if needed, but ensure all datetime fields in payload are ISO strings
    if not is_direct_db_mode() and should_sync():
        # Build a serializable payload: convert any datetime fields to ISO
        payload: Dict[str, Any] = {}
        # Use known TimeLog dataclass fields; here we do a safe conversion:
        for field_name, value in vars(updated).items():
            if isinstance(value, datetime):
                payload[field_name] = value.isoformat()
            else:
                payload[field_name] = value
        try:
            queue_sync_operation("time_history", "update", payload)
            process_sync_queue()
        except Exception as e:
            logging.error(
                "Failed to sync stopped time entry uid=%s: %s", active.uid, e, exc_info=True)
            # Do not raise further; local stop succeeded. Or re-raise if you want strict sync.
    return updated


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
