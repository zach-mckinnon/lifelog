# lifelog/models.py
from pydantic import BaseModel
from typing import Optional,  Union
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


from dataclasses import dataclass, asdict, fields
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    id: int = None  # Optional for new tasks
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


class Tracker:
    id: Optional[int]
    title: str
    type: str
    category: Optional[str]
    created: str
    tags: Optional[str] = None
    notes: Optional[str] = None
    goals: Optional[list] = None


class TrackerEntry(BaseModel):
    id: int
    tracker_id: int
    timestamp: str
    value: float


@dataclass
class GoalBase:
    id: Optional[int]  # Primary key (from the 'goals' table)
    tracker_id: int    # FK to Tracker
    title: str
    kind: str          # sum, count, bool, streak, etc.
    period: str = "day"  # day/week/month


@dataclass
class GoalSum(GoalBase):
    amount: float
    unit: Optional[str] = None


@dataclass
class GoalCount(GoalBase):
    amount: int
    unit: Optional[str] = None


@dataclass
class GoalBool(GoalBase):
    # No extra fields, just True/False tracking per period
    pass


@dataclass
class GoalStreak(GoalBase):
    target_streak: int


@dataclass
class GoalDuration(GoalBase):
    amount: float
    unit: str = "minutes"


@dataclass
class GoalMilestone(GoalBase):
    target: float
    unit: Optional[str] = None


@dataclass
class GoalReduction(GoalBase):
    amount: float
    unit: Optional[str] = None@dataclass


class GoalRange(GoalBase):
    min_amount: float
    max_amount: float
    unit: Optional[str] = None
    mode: str = "goal"  # could also be "tracker"


@dataclass
class GoalPercentage(GoalBase):
    target_percentage: float
    current_percentage: float = 0


@dataclass
class GoalReplacement(GoalBase):
    old_behavior: str
    new_behavior: str


Goal = Union[
    GoalSum, GoalCount, GoalBool, GoalStreak, GoalDuration, GoalMilestone,
    GoalReduction, GoalRange, GoalPercentage, GoalReplacement
]


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
