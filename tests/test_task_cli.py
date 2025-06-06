# tests/test_task_cli.py

import os
import uuid
import pytest
from datetime import datetime, timedelta
from typer.testing import CliRunner

# Adjust these imports to match your package structure:
from lifelog.commands import task_module
from lifelog.utils.db import task_repository
from lifelog.utils.db.database_manager import initialize_schema, get_connection
from lifelog.config import config_manager as cfg
from lifelog.utils.db.db_helper import is_direct_db_mode, should_sync

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """
    Create a temp SQLite file; point LIFELOG_DB_PATH to it; force direct (host) mode.
    """
    db_file = tmp_path / "test_lifelog_task_cli.db"
    monkeypatch.setenv("LIFELOG_DB_PATH", str(db_file))

    # Monkey‐patch load_config() so that host_server=True and API key (if needed) is valid
    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda: {"deployment": {"mode": "host",
                                "host_server": True}, "api": {"key": "dummy"}}
    )
    monkeypatch.setattr(cfg, "is_host_server", lambda: True)

    # Force direct DB mode by patching should_sync() and is_direct_db_mode()
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.should_sync", lambda: False)
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.is_direct_db_mode", lambda: True)

    # Initialize a fresh schema
    conn = get_connection()
    conn.close()
    initialize_schema()
    yield
    # (tmp_path auto‐cleans up; no teardown necessary)


def test_add_task_minimal_title():
    """
    llog task add <title> should succeed with just a title (other fields defaulted).
    """
    # We do not supply category, project, etc. Only required "title".
    result = runner.invoke(task_module.app, ["add", "MyFirstTask"])
    assert result.exit_code == 0

    # Now confirm it was persisted in DB:
    tasks = task_repository.query_tasks()
    assert len(tasks) == 1
    assert tasks[0].title == "MyFirstTask"
    assert isinstance(tasks[0].uid, str) and len(tasks[0].uid) > 0


def test_add_task_invalid_due_date():
    """
    Passing an invalid due date string should cause the command to exit with an error.
    """
    # Provide a clearly invalid due date (Typer will not parse it)
    result = runner.invoke(
        task_module.app,
        ["add", "BadDueTask", "--due", "not-a-date"]
    )
    # We expect an exit_code != 0 and an error message about invalid due date
    assert result.exit_code != 0
    assert "Invalid due date" in result.stdout


def test_list_and_filter_tasks():
    """
    Create two tasks, then verify `task list` filters by title and status.
    """
    # Create 2 tasks
    runner.invoke(task_module.app, ["add", "FirstTask"])
    runner.invoke(task_module.app, ["add", "SecondTask", "--category", "CatX"])

    # Mark SecondTask as done (simulate by calling 'done' subcommand)
    # First, look up its numeric ID
    all_tasks = task_repository.query_tasks()
    id_map = {t.title: t.id for t in all_tasks}
    second_id = id_map["SecondTask"]
    runner.invoke(task_module.app, ["done", str(second_id)])

    # Now run `task list` with no filters - we should see both (but by default show_completed=False,
    # so only FirstTask appears)
    out1 = runner.invoke(task_module.app, ["list"])
    assert "FirstTask" in out1.stdout
    assert "SecondTask" not in out1.stdout

    # If we pass --show-completed, we should see both
    out2 = runner.invoke(task_module.app, ["list", "--show-completed"])
    assert "FirstTask" in out2.stdout and "SecondTask" in out2.stdout

    # Filter by title_contains
    out3 = runner.invoke(task_module.app, ["list", "First"])
    assert "FirstTask" in out3.stdout and "SecondTask" not in out3.stdout


def test_modify_task_and_delete():
    """
    Test `task modify` to change title and `task delete` to remove.
    """
    # Create a task
    runner.invoke(task_module.app, ["add", "Modifiable"])
    task = task_repository.query_tasks()[0]
    tid = task.id

    # Modify: change title to "Renamed"
    result_mod = runner.invoke(
        task_module.app, ["modify", str(tid), "--title", "Renamed"])
    assert result_mod.exit_code == 0
    updated = task_repository.get_task_by_id(tid)
    assert updated.title == "Renamed"

    # Delete it
    result_del = runner.invoke(task_module.app, ["delete", str(tid)])
    assert result_del.exit_code == 0
    assert task_repository.get_task_by_id(tid) is None


def test_start_and_stop_task_time_tracking():
    """
    Simulate starting a task and stopping it via `task start` and `task done`.
    Verify that a TimeLog is created/ended and the task status is updated.
    """
    # Create a task
    runner.invoke(task_module.app, ["add", "TrackMe"])
    task = task_repository.query_tasks()[0]
    tid = task.id

    # Start the task
    start_out = runner.invoke(task_module.app, ["start", str(tid)])
    assert start_out.exit_code == 0
    # Confirm its status = "active"
    t1 = task_repository.get_task_by_id(tid)
    assert t1.status == "active"

    # Stop the task with `done` (no active timer besides itself)
    done_out = runner.invoke(task_module.app, ["done", str(tid)])
    assert done_out.exit_code == 0
    t2 = task_repository.get_task_by_id(tid)
    assert t2.status == "done"

    # Attempting to stop again (with no active timer) should not error in a surprising way,
    # but will mark done again or simply say “no active timer”
    second_done = runner.invoke(task_module.app, ["done", str(tid)])
    assert second_done.exit_code == 0  # just reports “no active timer” + marks done


def test_auto_recur_creates_new_tasks_host_mode():
    """
    Insert a “recurring” task whose recur_base was yesterday. 
    When we run `task auto_recur`, a new instance should be added (host mode).
    """
    # Manually insert a task with recur fields set to daily. Use repository directly:
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    data = {
        "uid": str(uuid.uuid4()),
        "title": "DailyTask",
        "project": None,
        "category": None,
        "importance": 1,
        "created": yesterday.isoformat(),
        "due": yesterday.isoformat(),
        "status": "backlog",
        "priority": 0,
        "recur_interval": 1,
        "recur_unit": "day",
        "recur_days_of_week": None,
        "recur_base": yesterday.isoformat(),
        "tags": None,
        "notes": None,
    }
    # Use upsert_local_task (or add_task if direct mode) to insert
    task_repository.add_task(data)

    # Confirm exactly one exists
    before = task_repository.query_tasks()
    assert len(before) == 1
    original = before[0]

    # Run auto_recur
    result = runner.invoke(task_module.app, ["auto_recur"])
    assert result.exit_code == 0

    # Now there should be two tasks: the original and the newly generated one
    after = task_repository.query_tasks()
    assert len(after) == 2
    titles = [t.title for t in after]
    assert titles.count("DailyTask") == 2

    # Ensure the new one’s `recur_base` equals “today” (approx)
    new_tasks = [t for t in after if t.id != original.id]
    assert len(new_tasks) == 1
    new_base = datetime.fromisoformat(new_tasks[0].recur_base)
    # new_base date should be “today”
    assert new_base.date() == now.date()


def test_auto_recur_does_not_run_in_client_mode(monkeypatch):
    """
    If should_sync() is True (client mode), auto_recur should not create new tasks locally.
    """
    # Re‐initialize a clean DB
    conn = get_connection()
    conn.close()
    initialize_schema()

    # Insert a “recur” task as before
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    data = {
        "uid": str(uuid.uuid4()),
        "title": "ClientDaily",
        "project": None,
        "category": None,
        "importance": 1,
        "created": yesterday.isoformat(),
        "due": yesterday.isoformat(),
        "status": "backlog",
        "priority": 0,
        "recur_interval": 1,
        "recur_unit": "day",
        "recur_days_of_week": None,
        "recur_base": yesterday.isoformat(),
        "tags": None,
        "notes": None,
    }
    task_repository.add_task(data)

    # Monkey‐patch to simulate client mode
    monkeypatch.setattr("lifelog.utils.db.db_helper.should_sync", lambda: True)
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.is_direct_db_mode", lambda: False)

    # Run auto_recur
    result = runner.invoke(task_module.app, ["auto_recur"])
    assert result.exit_code == 0

    # In client mode, add_task(data) inside auto_recur will queue but not insert immediately,
    # so local DB should still only show 1 task
    tasks = task_repository.query_tasks()
    assert len(tasks) == 1
