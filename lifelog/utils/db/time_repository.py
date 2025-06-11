
import logging
import uuid
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any, Union

from lifelog.utils.db.db_helper import (
    get_last_synced,
    is_direct_db_mode,
    set_last_synced,
    should_sync,
    queue_sync_operation,
    process_sync_queue,
    fetch_from_server,
)
from lifelog.utils.db.database_manager import get_connection, add_record, update_record
from lifelog.utils.db.models import TimeLog, time_log_from_row, fields as dataclass_fields

logger = logging.getLogger(__name__)


def _pull_changed_time_logs_from_host() -> None:
    """
    If in client mode and syncing is enabled, fetch time-history rows changed on the host
    since our last sync, upsert them locally, and update sync_state timestamp.
    """
    if not should_sync():
        return

    try:
        # 1) Push any queued local changes first
        process_sync_queue()
    except Exception as e:
        logger.error(
            f"Error pushing queued time log changes before pull: {e}", exc_info=True)
        # Continue to attempt pull even if push failed

    # 2) Read our last-sync timestamp for "time_history"
    try:
        last_ts = get_last_synced("time_history")
    except Exception as e:
        logger.error(
            f"Error getting last synced timestamp for time_history: {e}", exc_info=True)
        last_ts = None

    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) Fetch all changed logs from host
    try:
        remote_list = fetch_from_server("time/entries", params=params)
    except Exception as e:
        logger.error(
            f"Failed to fetch changed time logs from host: {e}", exc_info=True)
        return

    for remote in remote_list or []:
        try:
            upsert_local_time_log(remote)
        except Exception as e:
            logger.error(
                f"Failed to upsert remote time log {remote.get('uid')}: {e}", exc_info=True)
            # Continue processing others

    # 4) Update sync_state to now (UTC ISO)
    try:
        now_iso = datetime.utcnow().isoformat()
        set_last_synced("time_history", now_iso)
    except Exception as e:
        logger.error(
            f"Failed to set last synced timestamp for time_history: {e}", exc_info=True)


def _get_all_time_field_names() -> List[str]:
    """
    Return a list of all column names for time_history, excluding the auto-increment 'id'.
    Used when inserting/updating, so we never rely on the numeric `id` for sync payloads.
    """
    try:
        # dataclass_fields(TimeLog) returns a sequence of dataclass Field objects
        return [f.name for f in dataclass_fields(TimeLog) if f.name != "id"]
    except Exception as e:
        logger.error(
            f"Error retrieving time field names from TimeLog dataclass: {e}", exc_info=True)
        return []


def upsert_local_time_log(data: Dict[str, Any]) -> None:
    """
    Given a dict `data` from fetch_from_server(...), insert or update the local row by uid:
      • If uid already exists locally → update_record(...)
      • Else → add_record(...)
    We assume `data` includes columns matching time_history schema, including 'uid'.
    """
    conn = None
    try:
        uid_val = data.get("uid")
        if not uid_val:
            logger.warning(
                "Cannot upsert time log without uid: data lacks 'uid'")
            return

        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1) Check if a local row with this uid already exists
        cursor.execute("SELECT id FROM time_history WHERE uid = ?", (uid_val,))
        existing = cursor.fetchone()

        fields = _get_all_time_field_names()  # includes "uid" if defined
        if existing:
            local_id = existing["id"]
            # Build updates-only dict (only fields present in data and in schema)
            updates = {k: data[k] for k in fields if k in data}
            try:
                update_record("time_history", local_id, updates)
            except Exception as e:
                logger.error(
                    f"Failed to update local time_history id={local_id} during upsert: {e}", exc_info=True)
        else:
            # Insert new record
            try:
                add_record("time_history", data, fields)
            except Exception as e:
                logger.error(
                    f"Failed to add new local time_history uid={uid_val}: {e}", exc_info=True)
    except Exception as e:
        logger.error(
            f"Error in upsert_local_time_log for uid={data.get('uid')}: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()


def get_all_time_logs(since: Optional[Union[str, datetime]] = None) -> List[TimeLog]:
    """
    Return all time-history rows from local SQLite, optionally filtered by 'since' (ISO string or datetime).
    In CLIENT mode, first pull remote changes and merge them locally before selecting.
    Returns a list of TimeLog objects. Raises on fatal DB errors.
    """
    # 1) If client-mode and syncing is enabled, pull remote logs first
    if should_sync():
        try:
            _pull_changed_time_logs_from_host()
        except Exception as e:
            logger.error(
                f"Error pulling changed time logs before get_all_time_logs: {e}", exc_info=True)
            # Continue to local select even if pull failed

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if since:
            if isinstance(since, datetime):
                since_iso = since.isoformat()
            else:
                since_iso = str(since)
            cursor.execute(
                "SELECT * FROM time_history WHERE start >= ? ORDER BY start ASC",
                (since_iso,)
            )
        else:
            cursor.execute("SELECT * FROM time_history ORDER BY start ASC")

        rows = cursor.fetchall()
        # Convert to TimeLog dataclasses
        result = []
        for row in rows:
            try:
                result.append(time_log_from_row(dict(row)))
            except Exception as e:
                logger.error(
                    f"Failed to convert row to TimeLog: {e}; row={dict(row)}", exc_info=True)
        return result
    except Exception as e:
        logger.error(
            f"Error fetching time logs from local DB: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def get_time_log_by_uid(uid_val: str) -> Optional[TimeLog]:
    """
    Fetch a single TimeLog by its global UID.
    In CLIENT mode, first push queued changes and pull changed logs from host, then read locally.
    In HOST/DIRECT mode, read directly from local DB by uid.
    Returns TimeLog or None if not found.
    """
    # 1) If client-mode and syncing is enabled, pull changes first
    if should_sync():
        try:
            _pull_changed_time_logs_from_host()
        except Exception as e:
            logger.error(
                f"Error pulling changed time logs before get_time_log_by_uid: {e}", exc_info=True)
            # Continue to select local even if pull failed

    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM time_history WHERE uid = ?", (uid_val,))
        row = cursor.fetchone()
        if row:
            try:
                return time_log_from_row(dict(row))
            except Exception as e:
                logger.error(
                    f"Failed to convert row to TimeLog for uid={uid_val}: {e}", exc_info=True)
                return None
        else:
            return None
    except Exception as e:
        logger.error(
            f"Error fetching time log by uid={uid_val}: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def get_active_time_entry() -> Optional[TimeLog]:
    """
    Return the one active (running) timer from local SQLite, i.e., where `end IS NULL`.
    Does NOT pull from server—active timers are assumed purely local.
    Returns TimeLog or None if none active.
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            try:
                return time_log_from_row(dict(row))
            except Exception as e:
                logger.error(
                    f"Failed to convert active row to TimeLog: {e}; row={dict(row)}", exc_info=True)
                return None
        else:
            return None
    except Exception as e:
        logger.error(f"Error fetching active time entry: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def start_time_entry(data: Dict[str, Any]) -> TimeLog:
    """
    Start a new time entry. `data` is a dict with at least {"title": ..., "start": <ISO-string> or datetime}.
    In CLIENT mode:
      1) Normalize and assign a UUID if missing.
      2) Insert into local DB.
      3) Queue a sync-create to the host and drain queue.
      4) Return the newly-inserted TimeLog.
    In HOST/DIRECT mode:
      1) Normalize and assign a UUID if missing.
      2) Insert directly into SQLite.
      3) Return the inserted TimeLog.
    Raises on validation or DB errors.
    """
    # 1) Normalize 'start'
    try:
        if isinstance(data.get("start"), datetime):
            data["start"] = data["start"].isoformat()
        else:
            # If missing or not datetime, set to now ISO
            data["start"] = data.get("start") or datetime.now().isoformat()
    except Exception as e:
        logger.error(
            f"Error normalizing start in start_time_entry: {e}", exc_info=True)
        raise

    # 2) Normalize/assign uid
    try:
        if "uid" not in data or not data["uid"]:
            data["uid"] = str(uuid.uuid4())
    except Exception as e:
        logger.error(
            f"Error generating uid for new time entry: {e}", exc_info=True)
        raise

    # 3) Insert into local SQLite
    fields = _get_all_time_field_names()
    try:
        add_record("time_history", data, fields)
    except Exception as e:
        logger.error(
            f"Failed to insert new time entry into local DB: {e}; data={data}", exc_info=True)
        raise

    # 4) Retrieve the inserted row by uid
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(
                f"Inserted time entry not found locally for uid={data['uid']}")
        new_log = time_log_from_row(dict(row))
    except Exception as e:
        logger.error(
            f"Error retrieving new time entry after insert: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

    # 5) If client mode and syncing is enabled, queue sync-create
    if not is_direct_db_mode() and should_sync():
        try:
            queue_sync_operation("time_history", "create", data)
            process_sync_queue()
        except Exception as e:
            logger.error(
                f"Failed to queue/process sync-create for new time entry uid={data['uid']}: {e}", exc_info=True)
            # Do not raise, since local insert succeeded; caller can decide
    return new_log


def stop_active_time_entry(
    end_time: Union[datetime, str],
    tags: Optional[str] = None,
    notes: Optional[str] = None
) -> TimeLog:
    """
    Stop the one active time entry by setting its `end` and computing `duration_minutes`.
    Accepts `end_time` as a datetime or ISO-format string.
    In CLIENT mode and if syncing is enabled: updates local, queues sync-update by uid, drains queue.
    In HOST/DIRECT mode: updates directly.
    Raises:
      - RuntimeError if no active entry to stop.
      - ValueError/TypeError for invalid end_time or stored start format.
      - Other exceptions on DB errors.
    Returns the updated TimeLog.
    """
    # 1) Normalize end_time into datetime
    if isinstance(end_time, str):
        try:
            end_dt = datetime.fromisoformat(end_time)
        except Exception:
            logger.error(
                f"Invalid ISO datetime string for end_time: {end_time}", exc_info=True)
            raise ValueError(
                f"Invalid ISO datetime string for end_time: {end_time}")
    elif isinstance(end_time, datetime):
        end_dt = end_time
    else:
        logger.error(
            f"end_time has invalid type: {type(end_time)}. Must be datetime or ISO string.")
        raise TypeError("end_time must be datetime or ISO-format string")

    # 2) Open DB and find active row
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("No active time entry to stop.")
        record = dict(row)
        local_id = record["id"]
        uid_val = record.get("uid")
        start_iso = record["start"]
        try:
            start_dt = datetime.fromisoformat(start_iso)
        except Exception:
            raise ValueError(
                f"Stored start time is not valid ISO format: {start_iso}")

        # 3) Calculate updated fields
        end_iso = end_dt.isoformat()
        duration = max(0.0, (end_dt - start_dt).total_seconds() / 60.0)
        updates: Dict[str, Any] = {
            "end": end_iso, "duration_minutes": duration}
        if tags is not None:
            updates["tags"] = tags
        if notes is not None:
            updates["notes"] = notes

        # 4) Perform the UPDATE on the local row
        try:
            update_record("time_history", local_id, updates)
        except Exception as e:
            logger.error(
                f"Failed to update time_history id={local_id} on stop: {e}", exc_info=True)
            raise

    finally:
        if conn:
            conn.close()

    # 5) Fetch the freshly-updated object to return
    updated_log: Optional[TimeLog] = None
    try:
        if uid_val:
            updated_log = get_time_log_by_uid(uid_val)
        else:
            # Fallback: fetch by numeric ID if no uid
            conn2 = get_connection()
            conn2.row_factory = sqlite3.Row
            cursor2 = conn2.cursor()
            cursor2.execute(
                "SELECT * FROM time_history WHERE id = ?", (local_id,))
            row2 = cursor2.fetchone()
            conn2.close()
            if row2:
                updated_log = time_log_from_row(dict(row2))
    except Exception as e:
        logger.error(
            f"Error retrieving updated time entry after stop for id={local_id}: {e}", exc_info=True)
        # Proceed; updated_log may be None

    # 6) If client mode and syncing is enabled, queue sync-update with full payload
    if not is_direct_db_mode() and should_sync():
        # Build full_payload from the original record plus updates
        full_payload: Dict[str, Any] = {}
        try:
            for k in _get_all_time_field_names():
                if k in record:
                    full_payload[k] = record[k]
            full_payload.update(updates)
            if uid_val:
                full_payload["uid"] = uid_val
            queue_sync_operation("time_history", "update", full_payload)
            process_sync_queue()
        except Exception as e:
            logger.error(
                f"Failed to queue/process sync-update for stopped time entry uid={uid_val}: {e}", exc_info=True)
            # Do not raise further

    if updated_log is None:
        logger.warning(
            f"stop_active_time_entry completed but failed to retrieve updated TimeLog for id={local_id}")
    return updated_log  # May be None if retrieval failed


def add_time_entry(data: Dict[str, Any]) -> TimeLog:
    """
    Insert a historical TimeLog with both start and end provided.
    `data` may include 'start' and 'end' as datetime or ISO strings; 'duration_minutes' may be omitted.
    In CLIENT mode and if syncing is enabled:
      1) Normalize fields, assign uid if missing.
      2) Insert locally.
      3) Queue sync-create and drain.
      4) Return the new TimeLog.
    In HOST/DIRECT mode:
      1) Normalize fields, assign uid if missing.
      2) Insert locally.
      3) Return the new TimeLog.
    Raises on validation or DB errors.
    """
    # 1) Normalize 'start' and 'end'
    try:
        if isinstance(data.get("start"), datetime):
            data["start"] = data["start"].isoformat()
        if isinstance(data.get("end"), datetime):
            data["end"] = data["end"].isoformat()
    except Exception as e:
        logger.error(
            f"Error normalizing start/end in add_time_entry: {e}", exc_info=True)
        raise

    # 2) Compute duration if end provided and duration missing
    try:
        if data.get("end") is not None:
            if data.get("duration_minutes") is None:
                st = datetime.fromisoformat(data["start"])
                ed = datetime.fromisoformat(data["end"])
                data["duration_minutes"] = max(
                    0.0, (ed - st).total_seconds() / 60.0)
    except Exception as e:
        logger.error(
            f"Error computing duration in add_time_entry: {e}", exc_info=True)
        raise

    # 3) Assign uid if missing
    try:
        if not data.get("uid"):
            data["uid"] = str(uuid.uuid4())
    except Exception as e:
        logger.error(
            f"Error generating uid in add_time_entry: {e}", exc_info=True)
        raise

    # 4) Insert into local SQLite
    fields = _get_all_time_field_names()
    try:
        add_record("time_history", data, fields)
    except Exception as e:
        logger.error(
            f"Failed to insert historical time entry into local DB: {e}; data={data}", exc_info=True)
        raise

    # 5) Read back by uid
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(
                f"Inserted time entry not found locally for uid={data['uid']}")
        new_log = time_log_from_row(dict(row))
    except Exception as e:
        logger.error(
            f"Error retrieving new historical time entry after insert: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

    # 6) If client mode and syncing is enabled, queue sync-create
    if not is_direct_db_mode() and should_sync():
        try:
            queue_sync_operation("time_history", "create", data)
            process_sync_queue()
        except Exception as e:
            logger.error(
                f"Failed to queue/process sync-create for historical time entry uid={data['uid']}: {e}", exc_info=True)
            # Do not raise, since local insert succeeded

    return new_log


def update_time_entry(entry_id: int, **updates) -> Optional[TimeLog]:
    """
    Update fields of a time entry by numeric ID.
    In HOST/DIRECT mode: updates local DB directly.
    In CLIENT mode and if syncing is enabled:
      1) Update local row.
      2) Fetch updated row to get uid.
      3) Queue sync-update by uid (full payload) or by id if no uid.
      4) Return updated TimeLog.
    Raises ValueError if entry not found; logs and re-raises on DB errors.
    """
    # 1) Fetch existing row to get uid
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM time_history WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Time entry ID {entry_id} not found.")
        record = dict(row)
        uid_val = record.get("uid")
    except Exception as e:
        logger.error(
            f"Error fetching time entry id={entry_id} before update: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

    # 2) Update local row
    try:
        update_record("time_history", entry_id, updates)
    except Exception as e:
        logger.error(
            f"Failed to update time entry id={entry_id}: {e}", exc_info=True)
        raise

    # 3) Sync if client mode and syncing is enabled
    if not is_direct_db_mode() and should_sync():
        try:
            # Fetch updated row
            conn2 = get_connection()
            conn2.row_factory = sqlite3.Row
            cursor2 = conn2.cursor()
            cursor2.execute(
                "SELECT * FROM time_history WHERE id = ?", (entry_id,))
            row2 = cursor2.fetchone()
            conn2.close()
            if row2 and row2["uid"]:
                full_payload = dict(row2)
                queue_sync_operation("time_history", "update", full_payload)
            else:
                queue_sync_operation("time_history", "update", {
                                     "id": entry_id, **updates})
            process_sync_queue()
        except Exception as e:
            logger.error(
                f"Failed to queue/process sync-update for time entry id={entry_id}, uid={uid_val}: {e}", exc_info=True)
            # Do not raise further

    # 4) Return updated TimeLog
    try:
        if uid_val:
            return get_time_log_by_uid(uid_val)
        else:
            # Fallback: fetch by numeric id
            conn3 = get_connection()
            conn3.row_factory = sqlite3.Row
            cursor3 = conn3.cursor()
            cursor3.execute(
                "SELECT * FROM time_history WHERE id = ?", (entry_id,))
            row3 = cursor3.fetchone()
            conn3.close()
            if row3:
                return time_log_from_row(dict(row3))
            else:
                return None
    except Exception as e:
        logger.error(
            f"Error retrieving updated TimeLog for id={entry_id}: {e}", exc_info=True)
        return None


def delete_time_entry(entry_id: int) -> None:
    """
    Delete a time entry by numeric ID.
    In HOST/DIRECT mode: deletes directly from local DB.
    In CLIENT mode and if syncing is enabled:
      1) Fetch uid if any.
      2) Delete local row.
      3) Queue sync-delete by uid or id.
    Logs errors on failure; raises on DB error.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Fetch uid before deletion
        uid_val = None
        try:
            cursor.execute(
                "SELECT uid FROM time_history WHERE id = ?", (entry_id,))
            row = cursor.fetchone()
            if row:
                uid_val = row[0]
        except Exception as e:
            logger.error(
                f"Error fetching uid for time entry id={entry_id} before delete: {e}", exc_info=True)

        # Delete local row
        try:
            cursor.execute(
                "DELETE FROM time_history WHERE id = ?", (entry_id,))
            conn.commit()
        except Exception as e:
            logger.error(
                f"Failed to delete time entry id={entry_id} locally: {e}", exc_info=True)
            conn.rollback()
            raise

    finally:
        if conn:
            conn.close()

    # Queue sync-delete if client mode and syncing is enabled
    if not is_direct_db_mode() and should_sync():
        try:
            if uid_val:
                queue_sync_operation(
                    "time_history", "delete", {"uid": uid_val})
            else:
                queue_sync_operation(
                    "time_history", "delete", {"id": entry_id})
            process_sync_queue()
        except Exception as e:
            logger.error(
                f"Failed to queue/process sync-delete for time entry id={entry_id}, uid={uid_val}: {e}", exc_info=True)
            # Do not raise further


# -------------------------------------------------------------------------------
# HOST-ONLY helper functions (used by sync_api, not called by client CLI directly)
# -------------------------------------------------------------------------------

def update_time_log_by_uid(uid_val: str, updates: Dict[str, Any]) -> None:
    """
    Host-side: UPDATE time_history SET <cols> = ? ... WHERE uid = ?
    Called by sync_api when a client sends an 'update' operation.
    Skips 'id' in updates. Logs errors on failure.
    """
    if not updates:
        return

    # Build SET clause
    fields = []
    values = []
    for key, val in updates.items():
        if key == "id":
            continue
        fields.append(f"{key} = ?")
        values.append(val)
    values.append(uid_val)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        sql = f"UPDATE time_history SET {', '.join(fields)} WHERE uid = ?"
        cursor.execute(sql, tuple(values))
        conn.commit()
    except Exception as e:
        logger.error(
            f"Failed to update time_history uid={uid_val} on host: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def delete_time_log_by_uid(uid_val: str) -> None:
    """
    Host-side: DELETE FROM time_history WHERE uid = ?
    Called by sync_api when a client sends a 'delete' operation.
    Logs errors on failure.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM time_history WHERE uid = ?", (uid_val,))
        conn.commit()
    except Exception as e:
        logger.error(
            f"Failed to delete time_history uid={uid_val} on host: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()
