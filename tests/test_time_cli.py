# tests/test_time_cli.py

import uuid
import pytest
from datetime import datetime, timedelta
from typer.testing import CliRunner

from lifelog.commands import time_module
from lifelog.utils.db import time_repository
from lifelog.utils.db.database_manager import initialize_schema, get_connection
from lifelog.config import config_manager as cfg
from lifelog.utils.db.db_helper import is_direct_db_mode, should_sync

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """
    Fresh SQLite + force direct (host) mode for time CLI.
    """
    db_file = tmp_path / "test_lifelog_time_cli.db"
    monkeypatch.setenv("LIFELOG_DB_PATH", str(db_file))

    monkeypatch.setattr(
        cfg,
        "load_config",
        lambda: {"deployment": {"mode": "host",
                                "host_server": True}, "api": {"key": "dummy"}}
    )
    monkeypatch.setattr(cfg, "is_host_server", lambda: True)
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.should_sync", lambda: False)
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.is_direct_db_mode", lambda: True)

    conn = get_connection()
    conn.close()
    initialize_schema()
    yield


def test_start_and_stop_time_cli():
    """
    time start <title> should create an active TimeLog; time stop should finalize it.
    """
    # Start a timer
    now_iso = datetime.now().isoformat()
    result_start = runner.invoke(time_module.app, ["start", "WorkSession"])
    assert result_start.exit_code == 0
    # The time_repository should have one active entry
    active = time_repository.get_active_time_entry()
    assert active is not None
    assert active["title"] == "WorkSession"
    assert active["end"] is None

    # Stop the timer immediately
    result_stop = runner.invoke(time_module.app, ["stop"])
    assert result_stop.exit_code == 0

    # Now get_active_time_entry() should be None; instead, get_all_time_logs should return our past record
    assert time_repository.get_active_time_entry() is None

    all_logs = time_repository.get_all_time_logs()
    assert len(all_logs) == 1
    assert all_logs[0].title == "WorkSession"
    assert all_logs[0].end is not None


def test_stop_when_no_active_timer():
    """
    Invoking `time stop` without an active timer should exit with code != 0.
    """
    result = runner.invoke(time_module.app, ["stop"])
    assert result.exit_code != 0
    assert "not actively tracking" in result.stdout


def test_time_summary_no_history():
    """
    If no logs exist, `time summary` should print a “no history” message and exit normally.
    """
    result = runner.invoke(time_module.app, ["summary"])
    assert result.exit_code == 0
    assert "No time tracking history" in result.stdout


def test_time_summary_with_entries():
    """
    Insert two logs: one 2 days ago, one today. `time summary --period day` shows only today’s.
    """
    # Manually insert two entries into the repository
    now = datetime.now()
    yesterday_started = now - timedelta(days=1, hours=1)
    yesterday_ended = yesterday_started + timedelta(minutes=30)
    today_started = now - timedelta(hours=1)
    today_ended = now

    time_repository.start_time_entry({
        "title": "OldSession",
        "start": yesterday_started.isoformat(),
        "end": yesterday_ended.isoformat(),
        "duration_minutes": 30,
        "category": None,
        "project": None,
        "tags": None,
        "notes": None,
        "uid": str(uuid.uuid4()),
    })

    time_repository.start_time_entry({
        "title": "NewSession",
        "start": today_started.isoformat(),
        "end": today_ended.isoformat(),
        "duration_minutes": 60,
        "category": None,
        "project": None,
        "tags": None,
        "notes": None,
        "uid": str(uuid.uuid4()),
    })

    # Now call `time summary --period day`
    result = runner.invoke(time_module.app, ["summary", "--period", "day"])
    assert result.exit_code == 0
    # The summary table should include “NewSession” but not “OldSession”
    assert "NewSession" in result.stdout
    assert "OldSession" not in result.stdout
