# lifelog/models.py
from enum import Enum
from typing import Any, Dict, List, Optional, Union, get_args, get_origin
from dataclasses import asdict, dataclass, fields
from datetime import datetime


class BaseModel:
    def asdict(self) -> dict:
        """
        Convert dataclass to dict, but keep raw types (Enum, datetime) for internal use.
        """
        return asdict(self)

    def to_dict(self) -> dict:
        """
        Convert dataclass to JSON-serializable dict:
         - Enum fields → their .value
         - datetime fields → ISO-format strings
         - Nested dataclasses: also converted recursively
        """
        result = {}
        for f in fields(self.__class__):
            name = f.name
            val = getattr(self, name)
            if val is None:
                result[name] = None
            elif isinstance(val, Enum):
                result[name] = val.value
            elif isinstance(val, datetime):
                result[name] = val.isoformat()
            # For nested dataclasses (if any), assume they implement to_dict()
            elif hasattr(val, "to_dict") and callable(val.to_dict):
                result[name] = val.to_dict()
            # Lists of dataclasses?
            elif isinstance(val, list):
                new_list = []
                for item in val:
                    if hasattr(item, "to_dict"):
                        new_list.append(item.to_dict())
                    else:
                        new_list.append(item)
                result[name] = new_list
            else:
                result[name] = val
        return result

    def __repr__(self):
        cname = self.__class__.__name__
        fields_str = ', '.join(f"{k}={v!r}" for k, v in self.to_dict().items())
        return f"{cname}({fields_str})"


class TaskStatus(Enum):
    BACKLOG = "backlog"
    ACTIVE = "active"
    DONE = "done"


@dataclass
class Task(BaseModel):
    id: int = None
    title: str = ""
    project: Optional[str] = None
    category: Optional[str] = None
    importance: int = 1
    created: Optional[datetime] = None
    due: Optional[datetime] = None
    status: TaskStatus = TaskStatus.BACKLOG
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
    updated_at: Optional[datetime] = None
    deleted: int = 0


def get_task_fields():
    # Exclude 'id' (auto-incremented primary key)
    return [f.name for f in fields(Task) if f.name != "id"]


def task_from_row(row: Dict[str, Any]) -> Task:
    field_types = {f.name: f.type for f in fields(Task)}
    data = {}
    for k, v in row.items():
        if k not in field_types:
            continue
        typ = field_types[k]
        if v is None:
            data[k] = None
            continue
        # datetime fields: created, due, start, end, recur_base, updated_at
        if typ is datetime or typ == Optional[datetime]:
            try:
                data[k] = datetime.fromisoformat(v)
            except Exception:
                data[k] = None
            continue
        # TaskStatus enum
        if typ is TaskStatus or (get_origin(typ) is Optional and TaskStatus in get_args(typ)):
            try:
                data[k] = TaskStatus(v)
            except Exception:
                data[k] = None
            continue
        # deleted field as int
        if k == 'deleted':
            data[k] = int(v)
            continue
        # Other fields
        data[k] = v
    return Task(**data)


@dataclass
class TimeLog(BaseModel):
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
    updated_at: Optional[datetime] = None
    deleted: int = 0


def time_log_from_row(row: Dict[str, Any]) -> TimeLog:
    kwargs = {}
    for field in fields(TimeLog):
        name = field.name
        val = row.get(name)
        if val is None:
            kwargs[name] = None
            continue
        if name in ("start", "end") and val:
            try:
                kwargs[name] = datetime.fromisoformat(val)
            except Exception:
                kwargs[name] = None
            continue
        if name == "distracted_minutes":
            kwargs[name] = float(val) if val is not None else 0.0
            continue
        if name == 'updated_at':
            try:
                kwargs[name] = datetime.fromisoformat(val)
            except Exception:
                kwargs[name] = None
            continue
        if name == 'deleted':
            kwargs[name] = int(val)
            continue
        # Other fields (title, duration_minutes, task_id, etc.)
        kwargs[name] = val
    return TimeLog(**kwargs)


@dataclass
class Tracker(BaseModel):
    id: Optional[int]
    title: str
    type: str
    category: Optional[str]
    created: Optional[datetime]
    tags: Optional[str] = None
    notes: Optional[str] = None
    entries: Optional[List['TrackerEntry']] = None
    goals: Optional[List['Goal']] = None
    uid: str = None
    updated_at: Optional[datetime] = None
    deleted: int = 0


def tracker_from_row(row: Dict[str, Any]) -> Tracker:
    return Tracker(
        id=row.get("id"),
        title=row.get("title", ""),
        type=row.get("type", ""),
        category=row.get("category"),
        created=None if row.get(
            "created") is None else datetime.fromisoformat(row.get("created")),
        tags=row.get("tags"),
        notes=row.get("notes"),
        entries=None,
        goals=None,
        uid=row.get("uid"),
        updated_at=None if row.get(
            "updated_at") is None else datetime.fromisoformat(row.get("updated_at")),
        deleted=int(row.get("deleted", 0))
    )


@dataclass
class TrackerEntry(BaseModel):
    id: Optional[int] = None
    tracker_id: int = None
    timestamp: str = None
    value: float = None
    uid: str = None


@dataclass
class GoalBase(BaseModel):
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
    Must match the actual database schema.
    """
    return ["uid", "title", "type", "category", "created", "tags", "notes", "updated_at", "deleted"]


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
    According to your schema, that is 
      ['uid', 'tracker_id', 'title', 'kind', 'period'].
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
class EnvironmentData(BaseModel):
    uid: str = None
    id: int = None
    timestamp: datetime = None
    weather: str = None
    air_quality: str = None
    moon: str = None
    satellite: str = None


def goal_from_row(row):
    if not isinstance(row, dict):
        row = dict(row)
    kind = row["kind"]
    base = {
        "id": row["id"],
        "tracker_id": row["tracker_id"],
        "title": row["title"],
        "kind": row["kind"],
        "period": row.get("period", "day"),
        "uid": row.get("uid"),
    }
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


@dataclass
class UserProfile(BaseModel):
    id:             int = None
    uid:            str = None
    xp:             int = 0
    level:          int = 1
    gold:           int = 0
    created_at:     datetime = None
    last_level_up:  datetime = None


@dataclass
class Badge(BaseModel):
    id:          int = None
    uid:         str = None
    name:        str = ""
    description: str = ""
    icon:        str = None


@dataclass
class ProfileBadge(BaseModel):
    profile_id:  int = None
    badge_id:    int = None
    awarded_at:  datetime = None


@dataclass
class Skill(BaseModel):
    id:          int = None
    uid:         str = None
    name:        str = ""
    description: str = ""


@dataclass
class ProfileSkill(BaseModel):
    profile_id:  int = None
    skill_id:    int = None
    level:       int = 1
    xp:          int = 0


@dataclass
class ShopItem(BaseModel):
    id:          int = None
    uid:         str = None
    name:        str = ""
    description: str = ""
    cost_gold:   int = 0


@dataclass
class InventoryItem(BaseModel):
    profile_id:  int = None
    item_id:     int = None
    quantity:    int = 1


def get_profile_fields() -> List[str]:
    return [f.name for f in UserProfile.__dataclass_fields__.values() if f.name != "id"]


def get_badge_fields() -> List[str]:
    return [f.name for f in Badge.__dataclass_fields__.values() if f.name != "id"]


def get_profile_badge_fields() -> List[str]:
    return [f.name for f in ProfileBadge.__dataclass_fields__.values()]


def get_skill_fields() -> List[str]:
    return [f.name for f in Skill.__dataclass_fields__.values() if f.name != "id"]


def get_profile_skill_fields() -> List[str]:
    return [f.name for f in ProfileSkill.__dataclass_fields__.values()]


def get_shop_item_fields() -> List[str]:
    return [f.name for f in ShopItem.__dataclass_fields__.values() if f.name != "id"]


def get_inventory_fields() -> List[str]:
    return [f.name for f in InventoryItem.__dataclass_fields__.values()]
