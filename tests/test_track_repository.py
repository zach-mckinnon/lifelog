# tests/test_track_repository.py

import os
import uuid
import pytest
from datetime import datetime, timedelta

from lifelog.utils.db.track_repository import (
    add_tracker,
    get_tracker_by_id,
    get_tracker_by_title,
    update_tracker,
    delete_tracker,
    add_tracker_entry,
    get_entries_for_tracker,
    add_goal,
    get_goals_for_tracker,
    update_goal,
    delete_goal,
    upsert_local_tracker,
    upsert_local_goal,
)
from lifelog.utils.db.models import Tracker, GoalSum, GoalCount, GoalRange

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def test_db_file(tmp_path, monkeypatch):
    """
    Create a temporary SQLite file and point the application's DB-lookup logic to it.
    Assumes that `get_connection()` reads an environment var or config key like LIFELOG_DB_PATH.
    Adjust based on your actual DB‐path configuration in db_helper or database_manager.
    """
    db_path = tmp_path / "test_lifelog.db"
    # If your code uses an env var, do something like:
    monkeypatch.setenv("LIFELOG_DB_PATH", str(db_path))
    # If your code uses a config file, you can override accordingly.

    # Initialize schema on the fresh file:
    from lifelog.utils.db.database_manager import initialize_schema, get_connection
    conn = get_connection()  # This should point to `db_path`
    conn.close()
    initialize_schema()
    yield
    # Teardown happens automatically when tmp_path is garbage‐collected


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def make_tracker_dict(title_suffix=""):
    """
    Return a minimal dict for Tracker, without id (so add_tracker will assign).
    """
    return {
        "title": f"Tracker{title_suffix}",
        "type": "sum",
        "category": "General",
        "created": datetime.now().isoformat(),
        "tags": None,
        "notes": None
    }

# -----------------------------------------------------------------------------
# Tracker CRUD tests
# -----------------------------------------------------------------------------


def test_add_and_get_tracker_by_id_and_title():
    # 1) Add tracker
    td = make_tracker_dict("_A")
    tr = Tracker(**td, uid=str(uuid.uuid4()))
    added: Tracker = add_tracker(tr)
    assert added.id is not None
    assert added.title == td["title"]

    # 2) Fetch by numeric ID
    fetched = get_tracker_by_id(added.id)
    assert isinstance(fetched, Tracker)
    assert fetched.title == td["title"]
    assert fetched.uid == added.uid

    # 3) Fetch by exact title
    fetched2 = get_tracker_by_title(td["title"])
    assert fetched2.id == added.id
    assert fetched2.uid == added.uid

    # 4) Update the tracker’s category and notes
    new_notes = "Updated notes"
    updated = update_tracker(added.id, {"notes": new_notes})
    assert updated.id == added.id
    assert updated.notes == new_notes

    # 5) Delete the tracker
    result = delete_tracker(added.id)
    assert result is True
    # Now it should no longer exist
    assert get_tracker_by_id(added.id) is None
    assert get_tracker_by_title(td["title"]) is None


# -----------------------------------------------------------------------------
# Tracker Entry tests (purely local)
# -----------------------------------------------------------------------------

def test_add_and_list_tracker_entries():
    td = make_tracker_dict("_B")
    tr = Tracker(**td, uid=str(uuid.uuid4()))
    added: Tracker = add_tracker(tr)

    # Add three chronological entries
    base_time = datetime.now()
    values = [1.5, 2.0, 3.3]
    for offset, val in enumerate(values):
        ts = (base_time + timedelta(minutes=offset)).isoformat()
        entry = add_tracker_entry(added.id, ts, val)
        assert entry.tracker_id == added.id
        assert pytest.approx(entry.value) == val

    # Retrieve entries back (should be in ascending timestamp order)
    all_entries = get_entries_for_tracker(added.id)
    assert len(all_entries) == 3
    returned_values = [e.value for e in all_entries]
    assert returned_values == values


# -----------------------------------------------------------------------------
# Upsert‐local tests (simulate “pull from host”)
# -----------------------------------------------------------------------------

def test_upsert_local_tracker_creates_or_updates():
    # Create a dict similar to what fetch_from_server would return
    dummy_uid = str(uuid.uuid4())
    data = {
        "uid": dummy_uid,
        "title": "RemoteTracker",
        "type": "count",
        "category": "RemoteCat",
        "created": datetime.now().isoformat(),
        "tags": "x,y",
        "notes": "imported remotely",
    }

    # Case A: None exists locally → should INSERT
    upsert_local_tracker(data)
    # Now fetch by title and uid
    fetched = get_tracker_by_title("RemoteTracker")
    assert fetched is not None
    assert fetched.uid == dummy_uid

    # Case B: Modify locally and upsert again (simulate an updated remote row)
    data["notes"] = "edited remotely"
    upsert_local_tracker(data)
    # It should not create a second tracker, but instead update the same one
    fetched2 = get_tracker_by_id(fetched.id)
    assert fetched2.notes == "edited remotely"


# -----------------------------------------------------------------------------
# Goal CRUD tests
# -----------------------------------------------------------------------------

def test_add_and_get_goals_for_tracker_and_subtypes():
    # Step 1: Add a tracker
    td = make_tracker_dict("_C")
    tr = Tracker(**td, uid=str(uuid.uuid4()))
    added_tr: Tracker = add_tracker(tr)

    # Step 2: Add a SUM goal under that tracker
    sum_goal_data = {
        "title": "Daily Water",
        "kind": "sum",
        "period": "day",
        "amount": 3000.0,
        "unit": "ml"
    }
    new_sum_goal = add_goal(added_tr.id, sum_goal_data)
    assert new_sum_goal.kind == "sum"
    assert isinstance(new_sum_goal, GoalSum)
    assert new_sum_goal.amount == pytest.approx(3000.0)
    assert new_sum_goal.unit == "ml"

    # Step 3: Add a COUNT goal under same tracker
    count_goal_data = {
        "title": "Pushups",
        "kind": "count",
        "period": "week",
        "amount": 100,
        "unit": None
    }
    new_count_goal = add_goal(added_tr.id, count_goal_data)
    assert new_count_goal.kind == "count"
    assert isinstance(new_count_goal, GoalCount)
    assert new_count_goal.amount == 100

    # Now there should be exactly 2 goals for this tracker
    all_goals = get_goals_for_tracker(added_tr.id)
    assert len(all_goals) == 2
    kinds = {g.kind for g in all_goals}
    assert kinds == {"sum", "count"}

    # Step 4: Update the SUM goal (change amount + unit)
    updated = update_goal(new_sum_goal.id, {"amount": 3500.0, "unit": "ml"})
    assert updated.id == new_sum_goal.id
    assert isinstance(updated, GoalSum)
    assert updated.amount == pytest.approx(3500.0)

    # Step 5: Delete the COUNT goal
    assert delete_goal(new_count_goal.id) is True
    remaining = get_goals_for_tracker(added_tr.id)
    assert len(remaining) == 1
    assert remaining[0].id == new_sum_goal.id

    # Step 6: Test RANGE‐type goal → subtype insertion
    range_goal_data = {
        "title": "WeightRange",
        "kind": "range",
        "period": "day",
        "min_amount": 60.0,
        "max_amount": 75.0,
        "unit": "kg",
        "mode": "goal"
    }
    range_goal = add_goal(added_tr.id, range_goal_data)
    assert isinstance(range_goal, GoalRange)
    assert range_goal.min_amount == pytest.approx(60.0)
    assert range_goal.max_amount == pytest.approx(75.0)
    assert range_goal.unit == "kg"
    assert range_goal.mode == "goal"

    # Clean up: delete the tracker (should cascade-delete all remaining goals)
    assert delete_tracker(added_tr.id) is True
    assert get_goals_for_tracker(added_tr.id) == []


def test_upsert_local_goal_creates_or_updates():
    # 1) Create a tracker
    td = make_tracker_dict("_D")
    tr = Tracker(**td, uid=str(uuid.uuid4()))
    added_tr = add_tracker(tr)

    # 2) Build a pretend remote-goal dict
    goal_uid = str(uuid.uuid4())
    remote_goal = {
        "uid": goal_uid,
        "tracker_id": added_tr.id,
        "title": "RemoteSum",
        "kind": "sum",
        "period": "day",
        "amount": 500.0,
        "unit": "sessions"
    }

    # Case A: upsert when no local exists → insert
    upsert_local_goal(remote_goal)
    all_goals = get_goals_for_tracker(added_tr.id)
    assert len(all_goals) == 1
    g = all_goals[0]
    assert g.uid == goal_uid
    assert isinstance(g, GoalSum)
    assert g.amount == pytest.approx(500.0)

    # Case B: modify remote data and upsert again
    remote_goal["amount"] = 750.0
    upsert_local_goal(remote_goal)
    updated_goals = get_goals_for_tracker(added_tr.id)
    assert len(updated_goals) == 1
    g2 = updated_goals[0]
    assert g2.amount == pytest.approx(750.0)


# -----------------------------------------------------------------------------
# Edge‐cases / Error checks
# -----------------------------------------------------------------------------

def test_delete_nonexistent_tracker_returns_false():
    # Deleting an ID that doesn't exist should safely return False
    assert delete_tracker(-9999) is False


def test_delete_nonexistent_goal_returns_false():
    assert delete_goal(-9999) is False
