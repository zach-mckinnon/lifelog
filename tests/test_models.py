# tests/test_models.py

import pytest
from datetime import datetime
from dataclasses import fields as dataclass_fields

import lifelog.utils.db.models as m


def test_get_task_fields_matches_dataclass():
    """
    get_task_fields() should return all field names of Task except 'id'.
    """
    expected = [f.name for f in dataclass_fields(m.Task) if f.name != "id"]
    got = m.get_task_fields()
    assert set(got) == set(expected)


def test_task_from_row_parses_datetimes():
    """
    Provide a dict with ISO strings for created and due, 
    ensure task_from_row returns a Task with datetime objects.
    """
    iso_created = "2025-06-10T14:30:00"
    iso_due = "2025-06-15T12:00:00"
    row = {
        "id": 1,
        "title": "Model Test Task",
        "project": "Proj",
        "category": "Cat",
        "importance": 3,
        "created": iso_created,
        "due": iso_due,
        "status": "backlog",
        "start": None,
        "end": None,
        "priority": 10.0,
        "recur_interval": None,
        "recur_unit": None,
        "recur_days_of_week": None,
        "recur_base": None,
        "tags": "a,b,c",
        "notes": "note",
        "uid": "model-uid-1"
    }
    task = m.task_from_row(row)
    assert isinstance(task, m.Task)
    assert task.title == "Model Test Task"
    assert isinstance(task.created, datetime)
    assert isinstance(task.due, datetime)
    assert task.uid == "model-uid-1"


def test_get_tracker_fields_and_tracker_from_row():
    """
    get_tracker_fields() must match the columns in the 'trackers' schema (excluding 'id'),
    and tracker_from_row() should map a row dict into a Tracker dataclass.
    """
    expected = ["uid", "title", "type", "category", "created"]
    assert m.get_tracker_fields() == expected

    row = {
        "id": 5,
        "uid": "trk-uid-123",
        "title": "Health",
        "type": "sum",
        "category": "Wellness",
        "created": "2025-06-10T00:00:00",
        # extra keys should be ignored
        "extra": "ignored"
    }
    tracker = m.tracker_from_row(row)
    assert tracker.id == 5
    assert tracker.uid == "trk-uid-123"
    assert tracker.title == "Health"
    assert tracker.type == "sum"
    assert tracker.category == "Wellness"
    assert tracker.goals is None  # default
    # 'created' stays a string here (models defined created: str)
    assert tracker.created == "2025-06-10T00:00:00"


def test_get_goal_fields_list():
    """
    get_goal_fields() should return exactly the five core columns for 'goals': 
    ['uid','tracker_id','title','kind','period']
    """
    got = m.get_goal_fields()
    expected = ["uid", "tracker_id", "title", "kind", "period"]
    assert got == expected


def test_entry_from_row_creates_tracker_entry():
    """
    entry_from_row() should map a dict with id, tracker_id, timestamp, value 
    into a TrackerEntry dataclass. 'uid' is always None (not stored in table).
    """
    row = {"id": 10, "tracker_id": 5,
           "timestamp": "2025-06-10T08:00:00", "value": 42.5}
    entry = m.entry_from_row(row)
    assert entry.id == 10
    assert entry.tracker_id == 5
    assert entry.timestamp == "2025-06-10T08:00:00"
    assert pytest.approx(entry.value, rel=1e-6) == 42.5
    assert entry.uid is None


@pytest.mark.parametrize("kind, detail", [
    ("sum", {"amount": 100.0, "unit": "steps"}),
    ("count", {"amount": 3, "unit": None}),
    ("bool", {}),
    ("streak", {"target_streak": 7}),
    ("duration", {"amount": 30.0, "unit": "minutes"}),
    ("milestone", {"target": 50.0, "unit": "kg"}),
    ("reduction", {"amount": 5.0, "unit": "hours"}),
    ("range", {"min_amount": 1.0, "max_amount": 10.0,
     "unit": "lbs", "mode": "goal"}),
    ("percentage", {"target_percentage": 80.0, "current_percentage": 20.0}),
    ("replacement", {"old_behavior": "smoke", "new_behavior": "vape"}),
])
def test_goal_from_row_each_kind(kind, detail):
    """
    For each goal kind, build a fake row that includes the core 'goals' columns
    plus the appropriate detail columns, and verify goal_from_row(...) returns the
    correct dataclass instance type.
    """
    base = {
        "id": 42,
        "tracker_id": 7,
        "title": "Test Goal",
        "kind": kind,
        "period": "day",
    }
    # Merge in detail fields
    row = {**base, **detail}
    # Guarantee all detail keys exist in the row, even if None (for missing columns)
    # For this test, it's sufficient to pass the keys used by goal_from_row
    if kind == "sum":
        row.setdefault("unit", None)
    elif kind == "count":
        row.setdefault("unit", None)
    elif kind == "bool":
        pass
    elif kind == "streak":
        row.setdefault("target_streak", None)
    elif kind == "duration":
        row.setdefault("unit", None)
    elif kind == "milestone":
        row.setdefault("unit", None)
    elif kind == "reduction":
        row.setdefault("unit", None)
    elif kind == "range":
        row.setdefault("unit", None)
        row.setdefault("mode", "goal")
    elif kind == "percentage":
        row.setdefault("current_percentage", 0)
    elif kind == "replacement":
        pass

    goal_obj = m.goal_from_row(row)
    # Check the returned type
    type_map = {
        "sum": m.GoalSum,
        "count": m.GoalCount,
        "bool": m.GoalBool,
        "streak": m.GoalStreak,
        "duration": m.GoalDuration,
        "milestone": m.GoalMilestone,
        "reduction": m.GoalReduction,
        "range": m.GoalRange,
        "percentage": m.GoalPercentage,
        "replacement": m.GoalReplacement,
    }
    assert isinstance(goal_obj, type_map[kind])
    assert goal_obj.id == 42
    assert goal_obj.tracker_id == 7
    assert goal_obj.title == "Test Goal"
    assert goal_obj.kind == kind
    assert goal_obj.period == "day"
