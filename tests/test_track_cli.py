# tests/test_track_cli.py

import pytest
import uuid
from datetime import datetime
from typer.testing import CliRunner

from lifelog.commands import track_module
from lifelog.utils.db import track_repository
from lifelog.utils.db.database_manager import initialize_schema, get_connection
from lifelog.config import config_manager as cfg
from lifelog.utils.db.db_helper import is_direct_db_mode, should_sync

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """
    Fresh SQLite + force direct (host) mode for track CLI.
    """
    db_file = tmp_path / "test_lifelog_track_cli.db"
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


def test_add_tracker_minimal():
    """
    `track add <title> -t <type>` should create a new tracker.
    """
    # Create with type=“int”
    result = runner.invoke(
        track_module.app, ["add", "MoodTracker", "-t", "int"])
    assert result.exit_code == 0

    # Confirm in DB
    all_tr = track_repository.get_all_trackers()
    assert len(all_tr) == 1
    assert all_tr[0].title == "MoodTracker"
    assert all_tr[0].type == "int"
    assert isinstance(all_tr[0].uid, str)


@pytest.mark.parametrize("bad_type", ["integer", "invalid"])
def test_add_tracker_invalid_type(bad_type):
    """
    Supplying an invalid type should cause an error exit.
    """
    result = runner.invoke(
        track_module.app, ["add", "BadTracker", "-t", bad_type])
    assert result.exit_code != 0
    assert "Invalid type" in result.stdout


def test_add_tracker_with_goal_interactive(monkeypatch):
    """
    Simulate “Yes” to adding a goal in the interactive prompt. 
    We’ll monkey‐patch create_goal_interactive to return a valid goal dict.
    """
    # Stub out create_goal_interactive to return a SUM‐goal payload
    fake_goal = {
        "title": "DailyWater",
        "kind": "sum",
        "period": "day",
        "amount": 2000.0,
        "unit": "ml"
    }
    monkeypatch.setattr(
        "lifelog.utils.goal_util.create_goal_interactive", lambda t: fake_goal)
    # Stub Confirm.ask to always say “yes”
    monkeypatch.setattr("rich.prompt.Confirm.ask",
                        lambda *args, **kwargs: True)

    result = runner.invoke(
        track_module.app, ["add", "HydrationTracker", "-t", "float"])
    assert result.exit_code == 0

    # Confirm tracker and goal exist in DB
    tr_list = track_repository.get_all_trackers()
    assert len(tr_list) == 1
    tr = tr_list[0]
    goals = track_repository.get_goals_for_tracker(tr.id)
    assert len(goals) == 1
    assert goals[0].kind == "sum"


def test_modify_tracker_and_delete():
    """
    Test `track modify` to change title and `track delete` to remove.
    """
    # First create a tracker
    runner.invoke(track_module.app, ["add", "SleepTracker", "-t", "float"])
    tr = track_repository.get_all_trackers()[0]
    tid = tr.id

    # Modify title to “SleepQuality”
    result_mod = runner.invoke(
        track_module.app, ["modify", str(tid), "SleepQuality"])
    assert result_mod.exit_code == 0
    updated = track_repository.get_tracker_by_id(tid)
    assert updated.title == "SleepQuality"

    # Delete it (force skip confirmation)
    result_del = runner.invoke(
        track_module.app, ["delete", str(tid), "--force"])
    assert result_del.exit_code == 0
    assert track_repository.get_tracker_by_id(tid) is None


def test_list_trackers_shows_goals(monkeypatch):
    """
    If a tracker has a goal, `track list` should display its goal and progress.
    We’ll stub generate_goal_report to return a dummy progress.
    """
    # Create a tracker
    tdata = {
        "title": "StepCounter",
        "type": "int",
        "category": None,
        "created": datetime.now().isoformat(),
        "tags": None,
        "notes": None,
        "uid": str(uuid.uuid4()),
    }
    tid = track_repository.add_tracker(tdata)

    # Add a simple SUM goal under it
    goal_payload = {
        "title": "DailySteps",
        "kind": "sum",
        "period": "day",
        "amount": 10000.0,
        "unit": "steps"
    }
    track_repository.add_goal(tid, goal_payload)

    # Stub out generate_goal_report & format_goal_display to avoid complex logic
    monkeypatch.setattr(
        "lifelog.commands.track.generate_goal_report",
        lambda tracker: {"progress": 5000, "target": 10000}
    )
    monkeypatch.setattr(
        "lifelog.commands.track.format_goal_display",
        lambda title, rpt: [f"{title}: {rpt['progress']}/{rpt['target']}"]
    )

    # Now run `track list`
    result = runner.invoke(track_module.app, ["list"])
    assert result.exit_code == 0
    # Output should mention “DailySteps: 5000/10000”
    assert "DailySteps: 5000/10000" in result.stdout
