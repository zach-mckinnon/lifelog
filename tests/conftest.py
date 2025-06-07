# tests/conftest.py

import sqlite3
import pytest
from pathlib import Path
import importlib
from _pytest.monkeypatch import MonkeyPatch
# ────────────────────────────────────────────────────────────────────────────────
# Headless-safe curses stub (Linux + Windows)
#     --- place this BEFORE other imports that might import curses
# ────────────────────────────────────────────────────────────────────────────────
import sys
import types

import typer
from rich.prompt import Confirm


# def _install_dummy_curses():
#     """
#     Create a minimal stand-in for the real curses module so any call made during
#     tests never raises `_curses.error` (the typical “must call initscr() first”).
#     Executed once, at import time, before the test suite collects files.
#     """
#     if "curses" in sys.modules:        # already real curses? leave it alone
#         return

#     dummy = types.ModuleType("curses")
#     # Basic attributes used by your UI code
#     dummy.A_NORMAL = 0
#     dummy.A_BOLD = 1
#     dummy.A_REVERSE = 2
#     dummy.KEY_UP = 259
#     dummy.KEY_DOWN = 258
#     dummy.KEY_ENTER = 10
#     dummy.KEY_BACKSPACE = 263
#     dummy.KEY_LEFT = 260
#     dummy.KEY_RIGHT = 261
#     dummy.KEY_DC = 330
#     dummy.color_pair = lambda n: n

#     # Safe no-op versions of functions that normally need `initscr`
#     for _fn in (
#         "initscr", "endwin", "echo", "noecho", "cbreak", "nocbreak",
#         "raw", "noraw", "start_color", "use_default_colors", "curs_set"
#     ):
#         setattr(dummy, _fn, lambda *a, **k: None)

#     # A dead-simple window object for newwin()
#     class _DummyWin:
#         def __init__(self, h=25, w=80): self._h, self._w = h, w
#         def getmaxyx(self): return (self._h, self._w)
#         def border(self): pass
#         def addstr(self, *a, **k): pass
#         def erase(self): pass
#         def noutrefresh(self): pass
#         def refresh(self): pass
#         def getch(self): return -1
#         def curs_set(self, *_): pass
#         def keypad(self, *_): pass
#         def nodelay(self, *_): pass

#     dummy.newwin = lambda *args, **kw: _DummyWin(*args)

#     # Provide a very small ascii sub-module
#     dummy.ascii = types.SimpleNamespace(EOT=4)

#     # Finally, register the stub (both curses and curses.ascii)
#     sys.modules["curses"] = dummy
#     sys.modules["curses.ascii"] = dummy.ascii


# _install_dummy_curses()

# ────────────────────────────────────────────────────────────────────────────────
# Fixture: create a temporary SQLite file and monkey-patch LIFELOG_DB_PATH
# ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _stub_typer_prompts(monkeypatch):
    """
    Silence every interactive question coming from typer.confirm,
    typer.prompt, and rich.prompt.Confirm.ask so tests run headless.
    """
    # Always say “no” to yes/no confirmations.
    monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)
    monkeypatch.setattr(Confirm, "ask", lambda *a, **k: False)

    # When code calls typer.prompt("…") just return an empty string
    # (or a sentinel value if a specific answer is required in a test).
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: "")

    yield


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
