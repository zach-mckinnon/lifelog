# tests/test_db_helper_and_sync_state.py

import os
import pytest
import json
import sqlite3
from pathlib import Path
import importlib

import lifelog.utils.db.db_helper as helper
import lifelog.config.config_manager as cfg
import lifelog.utils.db.database_manager as dbman


@pytest.mark.usefixtures("test_db_file")
def test_is_direct_db_mode_and_should_sync_default(monkeypatch):
    """
    By default, deployment.mode comes from config_manager: default is "local" ("deployment.mode" unset).
    Therefore:
      is_direct_db_mode() → True
      should_sync() → False
    """
    # Ensure config_manager returns default before monkeypatch
    monkeypatch.setenv("LIFELOG_DB_PATH", os.getenv(
        "LIFELOG_DB_PATH", ""))  # no-op
    importlib.reload(cfg)
    importlib.reload(helper)

    assert helper.is_direct_db_mode() is True
    assert helper.should_sync() is False

    # If we set deployment.mode to "client", should_sync() becomes True
    # Monkey‐patch config so that get_deployment_mode_and_url returns ("client", ...)
    monkeypatch.setattr(cfg, "get_deployment_mode_and_url",
                        lambda: ("client", "http://example.com"))
    importlib.reload(helper)
    assert helper.should_sync() is True
    assert helper.is_direct_db_mode() is False


@pytest.mark.usefixtures("test_db_file")
def test_set_and_get_last_synced():
    """
    The sync_state table is created in initialize_schema().
    Initially, get_last_synced("tasks") is None. After set_last_synced, it returns the given timestamp.
    """
    # Make sure schema is in place
    assert dbman.is_initialized() is True

    # Before setting, returns None
    assert helper.get_last_synced("tasks") is None

    # Set a timestamp
    ts = "2025-06-10T12:34:56"
    helper.set_last_synced("tasks", ts)

    # Now get_last_synced must return that sum
    fetched = helper.get_last_synced("tasks")
    assert fetched == ts

    # Update with a new timestamp
    ts2 = "2025-06-11T00:00:00"
    helper.set_last_synced("tasks", ts2)
    fetched2 = helper.get_last_synced("tasks")
    assert fetched2 == ts2

    # Another table name → None
    assert helper.get_last_synced("nonexistent_table") is None


@pytest.mark.usefixtures("test_db_file")
def test_queue_sync_operation_creates_queue_db(tmp_path, monkeypatch):
    """
    queue_sync_operation(...) should create a sync_queue table in SYNC_QUEUE_PATH,
    but only if should_sync() is True. We override should_sync to True for this test.
    """
    # 1) Monkey‐patch should_sync() to True so queueing actually happens
    monkeypatch.setattr(helper, "should_sync", lambda: True)

    # Override SYNC_QUEUE_PATH to a temp file so we don’t touch ~/.lifelog/sync_queue.db
    mq_path = tmp_path / "sync_queue.db"
    monkeypatch.setattr(helper, "SYNC_QUEUE_PATH", mq_path)

    # Call queue_sync_operation
    sample_data = {"uid": "abc", "title": "SyncTest"}
    helper.queue_sync_operation("tasks", "create", sample_data)

    # Now check that the file was created and table exists
    conn = sqlite3.connect(str(mq_path))
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_queue';")
    assert cur.fetchone() is not None

    # Check that one row is in the queue
    cur.execute("SELECT table_name, operation, data FROM sync_queue;")
    row = cur.fetchone()
    conn.close()
    assert row[0] == "tasks"
    assert row[1] == "create"
    # data is stored as JSON string, so parse it
    stored = json.loads(row[2])
    assert stored["title"] == "SyncTest"

    # If should_sync() is False, no queue file is created
    mq2 = tmp_path / "sync_queue2.db"
    monkeypatch.setattr(helper, "should_sync", lambda: False)
    monkeypatch.setattr(helper, "SYNC_QUEUE_PATH", mq2)
    # Remove if exists
    if mq2.exists():
        mq2.unlink()
    helper.queue_sync_operation("tasks", "delete", {"uid": "xyz"})
    assert not mq2.exists()


@pytest.mark.usefixtures("test_db_file")
def test_direct_db_execute_allowed_and_blocked(monkeypatch, tmp_path):
    """
    direct_db_execute should run only if is_direct_db_mode()==True.
    We override LOCAL_DB_PATH to the same test DB to check behavior.
    """
    # Override helper.LOCAL_DB_PATH to point at our test_db_file
    test_db = tmp_path / "override_tasks.db"
    monkeypatch.setenv("LIFELOG_DB_PATH", str(test_db))  # so schema exists
    importlib.reload(dbman)
    dbman.initialize_schema()
    monkeypatch.setattr(helper, "LOCAL_DB_PATH", test_db)

    # By default (mode=local), is_direct_db_mode()==True
    monkeypatch.setattr(helper, "is_direct_db_mode", lambda: True)
    cursor = helper.direct_db_execute("INSERT INTO tasks (title, uid, created) VALUES (?, ?, ?);",
                                      ("DD Exercise", "uid-dd", "2025-06-10T00:00:00"))
    # Now verify row was inserted
    conn = sqlite3.connect(str(test_db))
    cur = conn.cursor()
    cur.execute("SELECT title, uid FROM tasks WHERE uid = ?", ("uid-dd",))
    row = cur.fetchone()
    conn.close()
    assert row[0] == "DD Exercise"
    assert row[1] == "uid-dd"

    # If is_direct_db_mode()==False → RuntimeError
    monkeypatch.setattr(helper, "is_direct_db_mode", lambda: False)
    with pytest.raises(RuntimeError):
        helper.direct_db_execute("SELECT 1;")
