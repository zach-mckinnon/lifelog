
import uuid
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any

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


def _pull_changed_time_logs_from_host() -> None:
    """
    If in client mode, fetch only the time-history rows changed on the host
    since our last sync, upsert them locally, and update sync_state.
    """
    if not should_sync():
        return

    # 1) Push any queued local changes first
    process_sync_queue()

    # 2) Read our last‐sync timestamp for "time_history"
    last_ts = get_last_synced("time_history")
    params: Dict[str, Any] = {}
    if last_ts:
        params["since"] = last_ts

    # 3) Fetch all changed logs from host
    remote_list = fetch_from_server("time/entries", params=params)
    for remote in remote_list:
        upsert_local_time_log(remote)

    # 4) Update sync_state to now
    now_iso = datetime.utcnow().isoformat()
    set_last_synced("time_history", now_iso)


def _get_all_time_field_names() -> List[str]:
    """
    Return a list of all columns on time_history except the auto‐inc 'id'.
    This is used when inserting/updating, so we never rely on the numeric `id` for sync.
    """
    # time_fields is imported from models; it returns the dataclass fields for TimeLog.
    # We exclude "id" because SQLite will allocate it automatically.
    return [f.name for f in dataclass_fields(TimeLog) if f.name != "id"]


def upsert_local_time_log(data: Dict[str, Any]) -> None:
    """
    Given a dict “data” from fetch_from_server(…), insert or update the local row by uid:
      • If uid already exists locally → update_record(...)
      • Else → add_record(...)
    We assume `data` includes every column (including uid).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    uid_val = data.get("uid")
    if not uid_val:
        # Cannot upsert without a uid
        conn.close()
        return

    # 1) See if a local row with this uid already exists
    cursor.execute("SELECT id FROM time_history WHERE uid = ?", (uid_val,))
    existing = cursor.fetchone()

    fields = _get_all_time_field_names()  # includes "uid"
    if existing:
        # 2a) Build an updates‐only dict (exclude “id”)
        local_id = existing["id"]
        updates = {k: data[k] for k in fields if k in data}
        update_record("time_history", local_id, updates)
    else:
        # 2b) Insert brand‐new record
        add_record("time_history", data, fields)

    conn.close()


def get_all_time_logs(since: Optional[str] = None) -> List[TimeLog]:
    """
    Return all time‐history rows from local SQLite, optionally filtered by 'since' (ISO string).
    In CLIENT mode, we first pull any remote changes (new or updated logs) and merge them locally.
    Then we do a local SELECT and convert to TimeLog objects.
    """

    # 1) If client‐mode, pull remote logs before returning
    if should_sync():
        _pull_changed_time_logs_from_host()

    # 2) Now run the local SELECT
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if since:
        cursor.execute(
            "SELECT * FROM time_history WHERE start >= ? ORDER BY start ASC",
            (since,)
        )
    else:
        cursor.execute("SELECT * FROM time_history ORDER BY start ASC")

    rows = cursor.fetchall()
    conn.close()

    # Convert to TimeLog dataclasses
    return [time_log_from_row(dict(row)) for row in rows]


def get_time_log_by_uid(uid_val: str) -> Optional[TimeLog]:
    """
    Fetch a single TimeLog by its global UID.
    In client mode, first push queued changes, then pull this one log from the host and upsert locally.
    In host mode (direct DB), just read from local DB by uid.
    """
    # 1) (Client) push first, then pull that one record
    if should_sync():
        _pull_changed_time_logs_from_host()

    # 2) Now select from local SQLite
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM time_history WHERE uid = ?", (uid_val,))
    row = cursor.fetchone()
    conn.close()

    return time_log_from_row(dict(row)) if row else None


def get_active_time_entry() -> Optional[TimeLog]:
    """
    Return the one active (running) timer from local SQLite, i.e. where `end IS NULL`.
    We do NOT pull from the server—clients assume the “active” timer is purely local.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return time_log_from_row(dict(row)) if row else None


def start_time_entry(data: Dict[str, Any]) -> TimeLog:
    """
    Start a new time entry. `data` is a dict with at least {"title": ..., "start": <ISO-string>}
    In CLIENT mode: 
      1) Generate a UUID for the new row → `data['uid'] = <uuid4()>`. 
      2) Insert into local DB (all fields except numeric id).
      3) Queue a sync‐create to the host: `queue_sync_operation("time_history","create", <full-payload>)`.
      4) Drain queue via `process_sync_queue()`.
      5) Return the newly‐inserted TimeLog (with local `id` and `uid`).
    In HOST/DIRECT mode:
      1) Insert directly into SQLite (no queue).
      2) Return the inserted TimeLog (with id/uid).
    """
    # 1) Normalize data: if passed a TimeLog object, convert to dict
    # (Your CLI always passes a dict, so we can skip instance‐check.)

    # 2) Ensure “start” exists (string or datetime) and convert to ISO
    if isinstance(data.get("start"), datetime):
        data["start"] = data["start"].isoformat()
    else:
        # Assume it’s already an ISO string otherwise
        data["start"] = data.get("start") or datetime.now().isoformat()

    # 3) In client mode, assign a new UID
    if not is_direct_db_mode():
        if "uid" not in data or not data["uid"]:
            data["uid"] = str(uuid.uuid4())
    else:
        # In host/direct mode: if they somehow supplied a `uid`, keep it; else generate.
        if "uid" not in data or not data["uid"]:
            data["uid"] = str(uuid.uuid4())

    # 4) Insert into local SQLite
    fields = _get_all_time_field_names()
    add_record("time_history", data, fields)

    # 5) Retrieve the inserted row (we need to know its numeric `id`)
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
    row = cursor.fetchone()
    conn.close()
    new_log = time_log_from_row(dict(row))

    # 6) If client, queue a sync and drain
    if not is_direct_db_mode():
        # Send the full‐payload (including uid) to host
        queue_sync_operation("time_history", "create", data)
        process_sync_queue()

    return new_log


def stop_active_time_entry(
    end_time: datetime,
    tags: Optional[str] = None,
    notes: Optional[str] = None
) -> TimeLog:
    """
    Stop the one active time entry by setting its `end` and computing `duration_minutes`.
    Updates fields: end, duration_minutes, optionally tags/notes/distracted_minutes (if any).
    In CLIENT mode:
      1) Update local row.
      2) Queue a sync “update” by uid (full‐payload).
      3) Drain queue via process_sync_queue().
      4) Return the updated TimeLog.
    In HOST/DIRECT mode:
      1) Update directly in local DB.
      2) Return updated TimeLog.
    """

    # 1) Find the active row
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM time_history WHERE end IS NULL ORDER BY start DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise RuntimeError("No active time entry to stop.")

    record = dict(row)
    local_id = record["id"]
    uid_val = record.get("uid")
    start_iso = record["start"]
    start_dt = datetime.fromisoformat(start_iso)

    # 2) Calculate new fields
    end_iso = end_time.isoformat()
    duration = max(0.0, (end_time - start_dt).total_seconds() / 60)

    updates: Dict[str, Any] = {"end": end_iso, "duration_minutes": duration}
    if tags is not None:
        updates["tags"] = tags
    if notes is not None:
        updates["notes"] = notes

    # 3) Perform the UPDATE on the local row
    update_record("time_history", local_id, updates)
    conn.close()

    # 4) Fetch the freshly‐updated object to return
    updated_log = get_time_log_by_uid(uid_val) if uid_val else None

    # 5) If CLIENT, queue an “update” with full‐payload (all fields except numeric id)
    if not is_direct_db_mode():
        full_payload: Dict[str, Any] = {
            **{k: record[k] for k in _get_all_time_field_names() if k in record},
            **updates
        }
        # Ensure “uid” stays in the payload
        if uid_val:
            full_payload["uid"] = uid_val

        queue_sync_operation("time_history", "update", full_payload)
        process_sync_queue()

    return updated_log


def add_time_entry(data: Dict[str, Any]) -> TimeLog:
    """
    Insert a historical TimeLog (i.e., an entry with start AND end both provided).
    Very similar to start_time_entry, except that `data` must include “end” and “duration_minutes” 
    (e.g. for a distracted block or when manually logging). We still assign a uid/client vs host logic.
    """
    # 1) Guarantee “start” and “end” as ISO strings
    if isinstance(data.get("start"), datetime):
        data["start"] = data["start"].isoformat()
    if isinstance(data.get("end"), datetime):
        data["end"] = data["end"].isoformat()

    # 2) Only compute a duration if we actually have an end time
    if data.get("end") is not None:
        # duration_minutes missing or None? compute it
        if data.get("duration_minutes") is None:
            st = datetime.fromisoformat(data["start"])
            ed = datetime.fromisoformat(data["end"])
            data["duration_minutes"] = max(0.0, (ed - st).total_seconds() / 60)

    # 3) Assign a UID
    if not is_direct_db_mode():
        data["uid"] = data.get("uid") or str(uuid.uuid4())
    else:
        data["uid"] = data.get("uid") or str(uuid.uuid4())

    # 4) Insert into local
    fields = _get_all_time_field_names()
    add_record("time_history", data, fields)

    # 5) Read it back
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM time_history WHERE uid = ?", (data["uid"],))
    row = cursor.fetchone()
    conn.close()
    new_log = time_log_from_row(dict(row))

    # 6) If client, queue create‐sync
    if not is_direct_db_mode():
        queue_sync_operation("time_history", "create", data)
        process_sync_queue()

    return new_log


# -----------------------------------------------------------------------------
# HOST‐ONLY helper functions (used by sync_api, never called by client CLI directly)
# -----------------------------------------------------------------------------

def update_time_log_by_uid(uid_val: str, updates: Dict[str, Any]) -> None:
    """
    Host‐side: UPDATE time_history SET <cols> = ? … WHERE uid = ?
    Called by sync_api when a client sends an 'update' operation.
    """
    if not updates:
        return

    fields = []
    values = []
    for key, val in updates.items():
        # Skip numeric 'id' if provided
        if key == "id":
            continue
        fields.append(f"{key} = ?")
        values.append(val)
    values.append(uid_val)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE time_history SET {', '.join(fields)} WHERE uid = ?",
        tuple(values)
    )
    conn.commit()
    conn.close()


def delete_time_log_by_uid(uid_val: str) -> None:
    """
    Host‐side: DELETE FROM time_history WHERE uid = ?
    Called by sync_api when a client sends a 'delete' operation.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM time_history WHERE uid = ?", (uid_val,))
    conn.commit()
    conn.close()
