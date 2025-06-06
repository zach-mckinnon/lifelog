import pytest
import uuid
from datetime import datetime, timedelta

# Adjust these imports to match your project structure:
from lifelog.utils.db.time_repository import (
    start_time_entry,
    stop_active_time_entry,
    add_time_entry,
    get_active_time_entry,
    get_time_log_by_uid,
    get_all_time_logs,
    upsert_local_time_log,
)
from lifelog.utils.db.models import TimeLog
from lifelog.utils.db.db_helper import should_sync


def make_dummy_time_dict(start=None, end=None):
    """
    Return a minimal valid TimeLog payload as a dict (with uid).
    """
    now = datetime.now()
    s = (start or now).isoformat()
    if end:
        e = end
    else:
        # If end is omitted, leave it unassigned for a running timer
        e = None

    return {
        "uid": str(uuid.uuid4()),
        "title": "Test Activity",
        "start": s,
        "end": e.isoformat() if isinstance(e, datetime) else e,
        "duration_minutes": ((datetime.fromisoformat(e.isoformat()) - datetime.fromisoformat(s)).total_seconds() / 60) if e else None,
        "task_id": None,
        "category": "Work",
        "project": "ProjA",
        "tags": None,
        "notes": None,
        "distracted_minutes": 0,
    }


@pytest.fixture(autouse=True)
def disable_sync(monkeypatch):
    """
    By default, pretend we’re in direct/host‐mode so client sync code is skipped.
    """
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.should_sync", lambda: False)
    yield


def test_start_and_get_active_time_entry_direct_mode(test_db_file, clean_tables):
    """
    start_time_entry(...) in direct mode should insert a row with end=None,
    and get_active_time_entry() should return it.
    """
    data = {"title": "Coding", "start": datetime.now().isoformat()}
    tl = start_time_entry(data)
    assert isinstance(tl, TimeLog)
    # Active entry should be the same UID
    active = get_active_time_entry()
    assert active is not None
    assert active.uid == tl.uid
    assert active.end is None


def test_stop_active_time_entry_direct_mode(test_db_file, clean_tables):
    """
    After starting a timer, stop_active_time_entry(...) should set end and duration.
    """
    start = datetime.now() - timedelta(minutes=30)
    data = {"title": "Meeting", "start": start}
    tl = start_time_entry(data)
    # Stop exactly now
    stopped = stop_active_time_entry(
        end_time=datetime.now(), tags="tag1", notes="note1")
    assert stopped is not None
    assert isinstance(stopped, TimeLog)
    assert stopped.end is not None
    assert stopped.duration_minutes >= 29.0  # about 30 minutes minus rounding
    assert stopped.tags == "tag1"
    assert stopped.notes == "note1"


def test_add_time_entry_historical_direct_mode(test_db_file, clean_tables):
    """
    add_time_entry(...) with both start+end should insert a completed block.
    get_all_time_logs(since=None) should include it.
    """
    start = datetime.now() - timedelta(hours=1)
    end = datetime.now()
    d = {
        "title": "Reading",
        "start": start,
        "end": end,
        "duration_minutes": ((end - start).total_seconds() / 60),
        "category": "Learn",
        "project": "ProjB",
        "tags": None,
        "notes": None,
    }
    tl = add_time_entry(d)
    assert isinstance(tl, TimeLog)
    # Check get_all_time_logs includes this entry
    logs = get_all_time_logs()
    assert any(l.uid == tl.uid for l in logs)


def test_upsert_local_time_log_inserts_and_updates(test_db_file, clean_tables):
    """
    upsert_local_time_log(...) should insert if no UID matches,
    and update if same UID appears with changed fields.
    """
    # Create a remote payload with no local entry yet
    now = datetime.now()
    remote = make_dummy_time_dict(start=now - timedelta(minutes=15), end=now)
    # Insert
    upsert_local_time_log(remote)
    logs = get_all_time_logs()
    assert len(logs) == 1
    assert logs[0].uid == remote["uid"]

    # Update the remote payload (modify notes)
    remote2 = remote.copy()
    remote2["notes"] = "Updated note"
    upsert_local_time_log(remote2)

    logs2 = get_all_time_logs()
    assert len(logs2) == 1
    assert logs2[0].notes == "Updated note"


def test_get_time_log_by_uid_direct_mode(test_db_file, clean_tables):
    """
    After inserting a historical entry, get_time_log_by_uid(...) should fetch it by UID.
    """
    start = datetime.now() - timedelta(minutes=20)
    end = datetime.now()
    d = make_dummy_time_dict(start=start, end=end)
    tl1 = add_time_entry(d)
    fetched = get_time_log_by_uid(tl1.uid)
    assert fetched is not None
    assert fetched.uid == tl1.uid


def test_get_all_time_logs_since_filter(test_db_file, clean_tables):
    """
    Insert two logs: one 2 days ago, one today. get_all_time_logs(since=‘yesterday’) should return only the recent one.
    """
    now = datetime.now()
    old_start = now - timedelta(days=2)
    old_end = old_start + timedelta(minutes=10)
    new_start = now - timedelta(hours=1)
    new_end = now

    d_old = {
        "title": "Old",
        "start": old_start,
        "end": old_end,
        "duration_minutes": 10.0,
        "category": "Misc",
        "project": "ProjX",
        "tags": None,
        "notes": None,
    }
    d_new = {
        **make_dummy_time_dict(start=new_start, end=new_end),
    }
    # Insert both
    add_time_entry(d_old)
    tl_new = add_time_entry(d_new)

    since_iso = (now - timedelta(days=1)).isoformat()
    logs = get_all_time_logs(since=since_iso)
    # Only the new one should appear
    assert len(logs) == 1
    assert logs[0].uid == tl_new.uid


def test_client_mode_pull_changed_logs(monkeypatch, test_db_file, clean_tables):
    """
    Simulate client‐mode. Calling get_all_time_logs(...) should pull changed logs from host
    by calling _pull_changed_time_logs_from_host() and upsert them.
    """
    monkeypatch.setattr("lifelog.utils.db.db_helper.should_sync", lambda: True)
    # Stub fetch_from_server to return one remote payload
    now = datetime.now()
    remote = make_dummy_time_dict(start=now - timedelta(minutes=5), end=now)
    monkeypatch.setattr(
        "lifelog.utils.db.time_repository.fetch_from_server",
        lambda *args, **kwargs: [remote]
    )
    # Stub get_last_synced to return None so that pull returns everything
    monkeypatch.setattr(
        "lifelog.utils.db.time_repository.get_last_synced",
        lambda table: None
    )
    # Stub set_last_synced so it does nothing
    monkeypatch.setattr(
        "lifelog.utils.db.time_repository.set_last_synced",
        lambda table, ts: None
    )
    # Stub process_sync_queue to no‐op
    monkeypatch.setattr(
        "lifelog.utils.db.time_repository.process_sync_queue",
        lambda: None
    )

    logs = get_all_time_logs()
    assert len(logs) == 1
    assert logs[0].uid == remote["uid"]
