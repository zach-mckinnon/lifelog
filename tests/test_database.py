# tests/test_database.py

from pathlib import Path
import sqlite3
import pytest

from lifelog.utils.db import database_manager as dbman
from lifelog.utils.db.db_helper import is_direct_db_mode, should_sync


def test_db_path_uses_env(tmp_path, monkeypatch):
    # Ensure the environment variable “LIFELOG_DB_PATH” sets DB_PATH
    monkeypatch.setenv("LIFELOG_DB_PATH", str(tmp_path / "foo.db"))
    # Reload the module so DB_PATH is recalculated
    import importlib
    import lifelog.utils.db.database_manager as _dbman
    importlib.reload(_dbman)
    db_path = _dbman._resolve_db_path()
    assert db_path == Path(tmp_path / "foo.db")


def test_initialize_schema_creates_tables(test_db_file):
    # Connect directly and inspect sqlite_master
    conn = sqlite3.connect(str(test_db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    names = [row[0] for row in cursor.fetchall()]
    # You should at least see your core tables, e.g. ‘tasks’, ‘trackers’, ‘goals’, ‘first_command_flags’
    assert "tasks" in names
    assert "trackers" in names
    assert "goals" in names
    assert "first_command_flags" in names
    conn.close()


def test_is_direct_and_should_sync_default():
    # By default, without any config changes, we expect direct_db_mode = True (no server_url)
    assert is_direct_db_mode() is True
    assert should_sync() is False
