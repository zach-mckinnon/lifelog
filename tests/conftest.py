# tests/conftest.py

import sqlite3
import pytest
from pathlib import Path
import importlib
from _pytest.monkeypatch import MonkeyPatch

# ────────────────────────────────────────────────────────────────────────────────
# 1) Fixture: create a temporary SQLite file and monkey-patch LIFELOG_DB_PATH
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def test_db_file(tmp_path_factory):
    """
    Create a temporary SQLite file and set LIFELOG_DB_PATH so that
    database_manager.get_connection() uses it. Initialize the schema once.
    """
    mp = MonkeyPatch()

    # Create a new temporary directory for the test DB
    db_dir = tmp_path_factory.mktemp("lifelog_test_db")
    test_db = db_dir / "test_lifelog.db"

    # Ensure environment uses that path
    mp.setenv("LIFELOG_DB_PATH", str(test_db))

    # Reload database_manager so that DB_PATH is recomputed
    import lifelog.utils.db.database_manager as dbman
    importlib.reload(dbman)

    # Initialize schema in this new database
    dbman.initialize_schema()

    yield test_db

    # Teardown: undo environment patch, attempt to remove the file
    mp.undo()
    try:
        if test_db.exists():
            test_db.unlink()
    except PermissionError:
        # On Windows, the file may still be open; skip deletion.
        pass


# ────────────────────────────────────────────────────────────────────────────────
# 2) Fixture: drop all tables before each individual test so tests run clean
# ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_tables(test_db_file):
    """
    Before each test function, drop all user tables and re-create schema.
    Ensures a truly clean slate for every test.
    """
    # Connect directly to the test DB
    conn = sqlite3.connect(str(test_db_file))
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    # List all tables, but skip any internal sqlite_ tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    # Drop each user table (skip sqlite_sequence, sqlite_stat*, etc.)
    for t in tables:
        if not t.startswith("sqlite_"):
            cursor.execute(f"DROP TABLE IF EXISTS `{t}`")
    conn.commit()
    conn.close()

    # Re‐initialize schema for the next test
    import lifelog.utils.db.database_manager as dbman
    importlib.reload(dbman)
    dbman.initialize_schema()

    yield

    # After each test, nothing else to do. Next test will re‐clean.
