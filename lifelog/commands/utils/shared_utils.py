# # lifelog/commands/utils/shared_utils.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
The module uses JSON files for data storage and integrates with a cron job system for scheduling report generation.
'''

import json
from datetime import datetime, date, time, timedelta
import re
from typing import List
import lifelog.config.config_manager as cf


# TODO: Add more general functions for aggregating data and mathmatics for metrics, habits, etc. 

# TODO: Improve this by making it more generalized for csumming and aggregating different values and to be more resilient to missing data.
def sum_entries(name: str, since: str = "today") -> float:
    """
    Sum all entries for `name` in the log file that are
    timestamped since the start of the given period.
    Supported `since` values: "today", "week", "month".
    """
    # 1. Determine cutoff datetime
    now = datetime.now()
    if since == "today":
        cutoff = datetime.combine(date.today(), time.min)
    elif since == "week":
        # 7 days ago at midnight
        cutoff = datetime.combine(date.today(), time.min) - timedelta(days=7)
    elif since == "month":
        # first day of this month at midnight
        cutoff = datetime.combine(date.today().replace(day=1), time.min)
    else:
        raise ValueError(f"Unsupported period: {since}")

    # 2. Load all log entries
    TRACK_FILE = cf.get_track_file()
    with open(TRACK_FILE, "r") as f:
        entries = json.load(f)

    # 3. Filter + sum
    total = 0.0
    for e in entries:
        if e.get("tracker") == name:
            # parse ISO timestamp
            entry_ts = datetime.fromisoformat(e["timestamp"])
            if entry_ts >= cutoff:
                total += float(e["value"])
    return total

def count_entries(name: str, since: str="today") -> int:
    TRACK_FILE = cf.get_track_file()

    if since == "today":
        cutoff = datetime.combine(date.today(), time.min)
    elif since == "week":
        # 7 days ago at midnight
        cutoff = datetime.combine(date.today(), time.min) - timedelta(days=7)
    elif since == "month":
        # first day of this month at midnight
        cutoff = datetime.combine(date.today().replace(day=1), time.min)
    else:
        raise ValueError(f"Unsupported period: {since}")

    with open(TRACK_FILE, "r") as f:
        entries = json.load(f)
    
    for e in entries:
        if e.get("tracker") == name:
             entry_ts = datetime.fromisoformat(e["timestamp"])

    return sum(1 for e in entries if e["metric"]==name and entry_ts>=cutoff)

def serialize_task(task):
    task_copy = task.copy()
    for key in ["due", "created", "start", "end"]:
        if isinstance(task_copy.get(key), datetime):
            task_copy[key] = task_copy[key].isoformat()
    return task_copy

def parse_date_string(time_string: str, future: bool = False) -> datetime:
    """
    Parses a relative time string like '1d', '2h', '1dT16:00' into a datetime.
    If the string contains 'T', it is treated as a time part.
    If `future` is True, it calculates the future date; otherwise, it calculates the past date.
    """

    if "T" in time_string:
        duration_part, time_part = time_string.split("T")
    else:
        duration_part, time_part = time_string, None

    regex = re.compile(
        r"((?P<years>\d+)y)?"
        r"((?P<months>\d+)mn)?"
        r"((?P<weeks>\d+)w)?"
        r"((?P<days>\d+)d)?"
        r"((?P<hours>\d+)h)?"
        r"((?P<minutes>\d+)m)?"
    )
    match = regex.match(duration_part)

    if match:
        parts = match.groupdict()
        time_delta_kwargs = {}
        if parts.get("years"):
            time_delta_kwargs["days"] = int(parts["years"]) * 365
        if parts.get("months"):
            time_delta_kwargs["days"] = time_delta_kwargs.get("days", 0) + int(parts["months"]) * 30
        if parts.get("weeks"):
            time_delta_kwargs["weeks"] = int(parts["weeks"])
        if parts.get("days"):
            time_delta_kwargs["days"] = time_delta_kwargs.get("days", 0) + int(parts["days"])
        if parts.get("hours"):
            time_delta_kwargs["hours"] = int(parts["hours"])
        if parts.get("minutes"):
            time_delta_kwargs["minutes"] = int(parts["minutes"])

        now = datetime.now()
        delta = timedelta(**time_delta_kwargs)
        target = now + delta if future else now - delta

        if time_part:
            try:
                hour, minute = map(int, time_part.split(":"))
                target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                return None  # invalid time part like bad format

        return target
    return None
    
def parse_args(args: List[str]):
    """
    Parses command-line arguments into structured components:
    title/tracker, options, tags, notes
    """
    
    title_parts = []
    past = False
    tags = []
    notes = []

    time_pattern = re.compile(
        r"^(\d+y)?(\d+mn)?(\d+w)?(\d+d)?(\d+h)?(\d+m)?$"
    )
    
    for arg in args:
        if arg.startswith("+"):
            tags.append(arg[1:])  # Strip '+'
            parsed_tags = [tag.lstrip("+").lower() for tag in tags]
            for tag in parsed_tags:
                _ensure_tag_exists(tag) 
        elif time_pattern.match(arg) and arg.startswith("-p"):
            past = arg
        elif not tags and not past:
            title_parts.append(arg)
        else:
            notes.append(arg)

    title = " ".join(title_parts) if title_parts else None
    notes = " ".join(notes) if notes else None

    return title, tags, notes, past

def _ensure_tag_exists(tag: str):
    doc = cf.load_config()
    doc.setdefault("tags", {})  # Make sure [tags] section exists
    existing_tags = doc["tags"]
    if tag not in existing_tags:
        existing_tags[tag] = tag
            
        cf.save_config(doc)

def parse_recur_string(recur_str: str) -> dict:
    """
    Parses recurrence input like '1w m/w/f' into structured recurrence.
    Example returns:
    { "interval": 1, "unit": "week", "days_of_week": [0,2,4] }
    """

    parts = recur_str.split()
    if not parts:
        return None

    interval_part = parts[0]
    days_part = parts[1] if len(parts) > 1 else None

    # Interval part: number + unit
    interval_match = re.match(r"(\d+)([dwmy])", interval_part)
    if not interval_match:
        return None

    number, unit = interval_match.groups()
    unit_map = {
        "d": "day",
        "w": "week",
        "m": "month",
        "y": "year",
    }
    unit_full = unit_map.get(unit, None)

    if not unit_full:
        return None

    # Days part: m/w/f
    days_lookup = {
        "m": 0, "t": 1, "w": 2, "th": 3, "f": 4, "s": 5, "su": 6
    }
    days_of_week = []
    if days_part:
        for day_code in days_part.split("/"):
            day_code = day_code.lower()
            if day_code in days_lookup:
                days_of_week.append(days_lookup[day_code])

    return {
        "interval": int(number),
        "unit": unit_full,
        "days_of_week": days_of_week
    }

