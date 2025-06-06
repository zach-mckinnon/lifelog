# lifelog/models.py
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, fields
from pydantic import BaseModel
from datetime import datetime


@dataclass
class Task:
    id: int = None
    title: str = ""
    project: Optional[str] = None
    category: Optional[str] = None
    importance: int = 1
    created: Optional[datetime] = None
    due: Optional[datetime] = None
    status: str = "backlog"
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    priority: float = 1
    recur_interval: Optional[int] = None
    recur_unit: Optional[str] = None
    recur_days_of_week: Optional[str] = None
    recur_base: Optional[datetime] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    uid: str = None


def get_task_fields():
    # Exclude 'id' (auto-incremented primary key)
    return [f.name for f in fields(Task) if f.name != "id"]


def task_from_row(row):
    """
    Convert a dict/Row from sqlite3 to a Task object, handling ISO datetime parsing.
    """
    field_types = {f.name: f.type for f in fields(Task)}
    data = {}
    for k, v in row.items():
        if k in field_types:
            typ = field_types[k]
            if typ in [datetime, Optional[datetime]] and v:
                try:
                    data[k] = datetime.fromisoformat(v)
                except Exception:
                    data[k] = None
            else:
                data[k] = v
    return Task(**data)


@dataclass
class TimeLog:
    id: int = None
    title: str = ""
    start: datetime = None
    end: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    task_id: Optional[int] = None
    category: Optional[str] = None
    project: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    distracted_minutes: Optional[float] = 0
    uid: str = None


def time_log_from_row(row):
    # Robustly convert a sqlite3 row or dict to a TimeLog instance
    kwargs = {}
    for field in fields(TimeLog):
        val = row.get(field.name)
        if field.type in [datetime, Optional[datetime]] and val:
            try:
                kwargs[field.name] = datetime.fromisoformat(val)
            except Exception:
                kwargs[field.name] = None
        else:
            kwargs[field.name] = val
        if field.name == "distracted_minutes" and val is None:
            kwargs[field.name] = 0
        else:
            kwargs[field.name] = val
    return TimeLog(**kwargs)


@dataclass
class Tracker:
    id: Optional[int]
    title: str
    type: str
    category: Optional[str]
    created: str
    tags: Optional[str] = None
    notes: Optional[str] = None
    goals: Optional[list] = None
    uid: str = None


@dataclass
class TrackerEntry(BaseModel):
    id: int
    tracker_id: int
    timestamp: str
    value: float
    uid: str = None


@dataclass
class GoalBase:
    id: Optional[int]
    tracker_id: int    # FK to Tracker
    title: str
    kind: str          # sum, count, bool, streak, etc.


@dataclass
class GoalSum(GoalBase):
    amount: float
    unit: Optional[str] = None
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalCount(GoalBase):
    amount: int
    unit: Optional[str] = None
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalBool(GoalBase):
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalStreak(GoalBase):
    target_streak: int
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalDuration(GoalBase):
    amount: float
    unit: str = "minutes"
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalMilestone(GoalBase):
    target: float
    unit: Optional[str] = None
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalReduction(GoalBase):
    amount: float
    unit: Optional[str] = None
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalRange(GoalBase):
    min_amount: float
    max_amount: float
    unit: Optional[str] = None
    mode: str = "goal"  # could also be "tracker"
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalPercentage(GoalBase):
    target_percentage: float
    current_percentage: float = 0
    period: str = "day"  # day/week/month
    uid: str = None


@dataclass
class GoalReplacement(GoalBase):
    old_behavior: str
    new_behavior: str
    period: str = "day"  # day/week/month
    uid: str = None


Goal = Union[
    GoalSum, GoalCount, GoalBool, GoalStreak, GoalDuration, GoalMilestone,
    GoalReduction, GoalRange, GoalPercentage, GoalReplacement
]

# lifelog/utils/db/models.py
# (add these imports at the top of the file if they’re not already present)


# ───────────────────────────────────────────────────────────────────────────────
# 1) get_tracker_fields()
#    Return a list of column names in the "trackers" table, excluding 'id'.
#    We assume your SQLite schema is:
#      CREATE TABLE IF NOT EXISTS trackers (
#          id INTEGER PRIMARY KEY AUTOINCREMENT,
#          uid TEXT UNIQUE,
#          title TEXT,
#          type TEXT,
#          category TEXT,
#          created DATETIME
#      );
#
#    (If you have additional columns—e.g. 'tags' or 'notes'—you can add them here.)
# ───────────────────────────────────────────────────────────────────────────────

def get_tracker_fields() -> List[str]:
    """
    Return all Tracker‐table columns except 'id'.  
    If your schema has: (id, uid, title, type, category, created),
    this will return ['uid','title','type','category','created'].
    """
    return ["uid", "title", "type", "category", "created"]


# ───────────────────────────────────────────────────────────────────────────────
# 2) get_goal_fields()
#    Return a list of column names in the "goals" table (core columns), excluding 'id'.
#    According to your schema:
#      CREATE TABLE IF NOT EXISTS goals (
#          id INTEGER PRIMARY KEY AUTOINCREMENT,
#          uid TEXT UNIQUE,
#          tracker_id INTEGER NOT NULL,
#          title TEXT NOT NULL,
#          kind TEXT NOT NULL,
#          period TEXT DEFAULT 'day',
#          FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
#      );
#
#    We only insert those five columns into the “goals” table.  (Detail columns live in subtype tables.)
# ───────────────────────────────────────────────────────────────────────────────

def get_goal_fields() -> List[str]:
    """
    Return all core columns of the 'goals' table except 'id'.  
    As defined, that is ['uid','tracker_id','title','kind','period'].
    """
    return ["uid", "tracker_id", "title", "kind", "period"]


# ───────────────────────────────────────────────────────────────────────────────
# 3) tracker_from_row(row: Dict[str,Any]) → Tracker
#
#    Accepts a dictionary (or sqlite3.Row converted to dict) with at least
#    the columns (id, uid, title, type, category, created).  It returns a Tracker dataclass.
#
#    Your Tracker model is defined as:
#      @dataclass
#      class Tracker:
#          id: Optional[int]
#          title: str
#          type: str
#          category: Optional[str]
#          created: str
#          tags: Optional[str] = None
#          notes: Optional[str] = None
#          goals: Optional[list] = None
#          uid: str = None
#
#    In many tables, you may not store 'tags' or 'notes'; they can default to None.
# ───────────────────────────────────────────────────────────────────────────────

@dataclass
class Tracker:
    id: Optional[int]
    title: str
    type: str
    category: Optional[str]
    created: str
    tags: Optional[str] = None
    notes: Optional[str] = None
    goals: Optional[list] = None
    uid: str = None


def tracker_from_row(row: Dict[str, Any]) -> Tracker:
    """
    Convert a sqlite3‐row (or dict) into a Tracker dataclass.  
    Any missing keys default to None.  
    """
    return Tracker(
        id=row.get("id"),
        title=row.get("title", ""),
        type=row.get("type", ""),
        category=row.get("category"),
        created=row.get("created", ""),
        tags=row.get("tags"),      # if your schema never writes tags→None
        notes=row.get("notes"),    # if your schema never writes notes→None
        goals=None,                # we do not fetch embedded goals here
        uid=row.get("uid"),
    )


# ───────────────────────────────────────────────────────────────────────────────
# 4) entry_from_row(row: Dict[str,Any]) → TrackerEntry
#
#    The “tracker_entries” schema is:
#      CREATE TABLE IF NOT EXISTS tracker_entries (
#          id INTEGER PRIMARY KEY AUTOINCREMENT,
#          tracker_id INTEGER,
#          timestamp DATETIME,
#          value FLOAT,
#          FOREIGN KEY(tracker_id) REFERENCES trackers(id)
#      );
#
#    Your TrackerEntry model in models.py is:
#      @dataclass
#      class TrackerEntry(BaseModel):
#          id: int
#          tracker_id: int
#          timestamp: str
#          value: float
#          uid: str = None
#
#    We simply pull the four stored columns; uid isn’t stored locally, so it stays None.
# ───────────────────────────────────────────────────────────────────────────────

@dataclass
class TrackerEntry(BaseModel):
    id: int
    tracker_id: int
    timestamp: str
    value: float
    uid: str = None


def entry_from_row(row: Dict[str, Any]) -> TrackerEntry:
    """
    Convert a sqlite3‐row (or dict) into a TrackerEntry object.
    The 'uid' field is not stored in the 'tracker_entries' table, so it will be None.
    """
    return TrackerEntry(
        id=row.get("id"),
        tracker_id=row.get("tracker_id"),
        timestamp=row.get("timestamp"),
        value=row.get("value"),
        uid=None,
    )


def goal_from_row(row):
    kind = row["kind"]
    base = dict(
        id=row["id"],
        tracker_id=row["tracker_id"],
        title=row["title"],
        kind=row["kind"],
        period=row.get("period", "day"),
    )
    if kind == "sum":
        return GoalSum(**base, amount=row["amount"], unit=row.get("unit"))
    elif kind == "count":
        return GoalCount(**base, amount=row["amount"], unit=row.get("unit"))
    elif kind == "bool":
        return GoalBool(**base)
    elif kind == "streak":
        return GoalStreak(**base, target_streak=row["target_streak"])
    elif kind == "duration":
        return GoalDuration(**base, amount=row["amount"], unit=row.get("unit", "minutes"))
    elif kind == "milestone":
        return GoalMilestone(**base, target=row["target"], unit=row.get("unit"))
    elif kind == "reduction":
        return GoalReduction(**base, amount=row["amount"], unit=row.get("unit"))
    elif kind == "range":
        return GoalRange(**base, min_amount=row["min_amount"], max_amount=row["max_amount"], unit=row.get("unit"), mode=row.get("mode", "goal"))
    elif kind == "percentage":
        return GoalPercentage(**base, target_percentage=row["target_percentage"], current_percentage=row.get("current_percentage", 0))
    elif kind == "replacement":
        return GoalReplacement(**base, old_behavior=row["old_behavior"], new_behavior=row["new_behavior"])
    else:
        raise ValueError(f"Unknown goal kind: {kind}")
