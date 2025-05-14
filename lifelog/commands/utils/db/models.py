# lifelog/models.py
from pydantic import BaseModel
from typing import Optional, List, Union
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    id: int
    title: str
    project: Optional[str]
    category: Optional[str]
    importance: int
    created: datetime
    due: Optional[datetime]
    status: str
    start: Optional[datetime]
    end: Optional[datetime]
    priority: float
    recur_interval: Optional[int]
    recur_unit: Optional[str]
    recur_days_of_week: Optional[str]
    recur_base: Optional[datetime]


@dataclass
class TimeLog:
    id: int
    title: str
    start: datetime
    end: Optional[datetime]
    duration_minutes: Optional[float]
    task_id: Optional[int]
    category: Optional[str]
    project: Optional[str]
    tags: Optional[str]
    notes: Optional[str]


class Tracker(BaseModel):
    id: int
    title: str
    type: str
    category: Optional[str]
    created: str
    goals: Optional[Union[dict, List[dict]]]


class TrackerEntry(BaseModel):
    id: int
    tracker_id: int
    timestamp: str
    value: float
