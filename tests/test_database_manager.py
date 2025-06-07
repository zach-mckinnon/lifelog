# tests/test_database_manager.py

import os
import sqlite3
import importlib
import pytest
from pathlib import Path

import lifelog.utils.db.database_manager as dbman


def test_db_path_respects_env(monkeypatch, tmp_path):
    """
    If LIFELOG_DB_PATH is set before importing database_manager,
    DB_PATH should equal that, not BASE_DIR/"lifelog.db".
    """
    # 1) Prepare an env var
    temp_db = tmp_path / "override.db"
    monkeypatch.setenv("LIFELOG_DB_PATH", str(temp_db))

    # 2) Reload the module so DB_PATH is recalculated
    importlib.reload(dbman)
    db_path = dbman._resolve_db_path()
    assert db_path == temp_db.resolve()

    # 3) Ensure underlying parent directory is created when get_connection is called
    conn = dbman.get_connection()
    conn.close()
    assert temp_db.exists()


def test_initialize_schema_and_is_initialized(test_db_file):
    """
    - At session‐start (in conftest), initialize_schema() was called, so is_initialized() is True.
    - After dropping the file, is_initialized() becomes False.
    """
    # test_db_file fixture already ran initialize_schema once.
    # Now is_initialized() should return True.
    assert dbman.is_initialized() is True

    # Delete the file entirely
    Path(os.getenv("LIFELOG_DB_PATH")).unlink()

    # Now is_initialized() should be False (since file doesn't exist)
    assert dbman.is_initialized() is False

    # Re-run initialize_schema() → file recreated + tables exist
    dbman.initialize_schema()
    assert dbman.is_initialized() is True


def test_tables_exist_after_initialize(test_db_file):
    """
    After initialize_schema(), the core tables should exist.
    We check a few representative table names.
    """
    conn = sqlite3.connect(str(test_db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    names = [row[0] for row in cursor.fetchall()]
    conn.close()

    expected_tables = {
        "trackers",
        "tasks",
        "goals",
        "goal_sum",
        "goal_range",
        "tracker_entries",
        "time_history",
        "sync_state",
        "first_command_flags",
    }
    # Each expected table must be in the SQLite schema
    for tbl in expected_tables:
        assert tbl in names


def test_add_and_update_record(test_db_file):
    """
    Test that add_record() correctly inserts a row into the 'tasks' table
    and update_record() modifies it.
    """
    # 1) Insert a new task
    task_data = {
        "uid": "test-uid-1",
        "title": "Database Test Task",
        "project": "Proj",
        "category": "Cat",
        "importance": 1,
        "created": "2025-06-10T00:00:00",
        "due": None,
        "status": "backlog",
        "start": None,
        "end": None,
        "priority": 1.0,
        "recur_interval": None,
        "recur_unit": None,
        "recur_days_of_week": None,
        "recur_base": None,
        "notes": "Test note",
        "tags": "tag1,tag2"
    }
    fields = ["uid", "title", "project", "category", "importance", "created",
              "due", "status", "start", "end", "priority", "recur_interval",
              "recur_unit", "recur_days_of_week", "recur_base", "notes", "tags"]
    # This calls add_record("tasks", ...)
    dbman.add_record("tasks", task_data, fields)

    # Verify it got inserted
    conn = sqlite3.connect(str(test_db_file))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE uid = ?", ("test-uid-1",))
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row["title"] == "Database Test Task"

    # 2) Update the same row (e.g. change status)
    task_id = row["id"]
    dbman.update_record("tasks", task_id, {"status": "done", "priority": 5.5})

    # Query again
    conn2 = sqlite3.connect(str(test_db_file))
    conn2.row_factory = sqlite3.Row
    cur2 = conn2.cursor()
    cur2.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    updated = cur2.fetchone()
    conn2.close()
    assert updated["status"] == "done"
    assert pytest.approx(updated["priority"], rel=1e-6) == 5.5
