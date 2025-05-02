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
from rich.console import Console, Group
import typer
import lifelog.config.config_manager as cf

console = Console()


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

def parse_date_string(time_string: str, future: bool = False, now: datetime = datetime.now()) -> datetime:
    """
    Parses a smart or relative time string into a datetime.
    Supports:
    - '1d', '2w', '1m', '1y'
    - 'today', 'todayT19:00'
    - 'tomorrow'
    - 'next week'
    - '08:30' (means today at that time)
    - combinations like '2wT15:00'
    """
    if now is None:
        now = datetime.now()

    ts = time_string.strip()
    time_part = None
    base_part = ts
    target = None

    # Handle "T" separator (e.g. 1dT18:00 or 4/5T17:00)
    if 'T' in ts:
        base_part, time_part = ts.split('T', 1)
    elif re.match(r'^\d{1,2}:\d{2}$', ts):
        base_part, time_part = '', ts

    # Handle keyword dates
    if base_part in ('today', ''):
        target = now
    elif base_part == 'yesterday':
        target = now - timedelta(days=1)
    elif base_part == 'tomorrow':
        target = now + timedelta(days=1)

    # Handle relative durations like 1d, 2w, 3m, 1h, 30min
    elif re.fullmatch(r'(\d+[dwmyh]|(\d+min))+', base_part):
        # Find all matching segments
        units = re.findall(r'(\d+)(y|m(?!in)|w|d|h|min)', base_part)
        delta = timedelta()
        for value, unit in units:
            value = int(value)
            if unit == 'y': delta += timedelta(days=365 * value)
            elif unit == 'mn': delta += timedelta(days=30 * value)
            elif unit == 'w': delta += timedelta(weeks=value)
            elif unit == 'd': delta += timedelta(days=value)
            elif unit == 'h': delta += timedelta(hours=value)
            elif unit == 'm': delta += timedelta(minutes=value)
        target = now + delta if future else now - delta

    # Handle absolute formats like 4/5, 4/5/25, 4/5/2025
    else:
        formats = ["%m/%d", "%m/%d/%y", "%m/%d/%Y"]
        for fmt in formats:
            try:
                parsed = datetime.strptime(base_part, fmt)
                # Fill in missing year if needed
                if parsed.year == 1900:
                    parsed = parsed.replace(year=now.year)
                target = parsed
                break
            except ValueError:
                continue

    # Apply time part if present
    if time_part:
        try:
            hour, minute = map(int, time_part.split(":"))
            target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            raise ValueError(f"Invalid time part '{time_part}' in '{time_string}'")

    if target is None:
        raise ValueError(f"Could not parse: '{time_string}'")

    return target

def parse_args(args: List[str]):
    """
    Parses command-line arguments into structured components:
    title/tracker, options, tags, notes
    """
    
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
        else:
            notes.append(arg)

    notes = " ".join(notes) if notes else None

    return tags, notes

def _ensure_tag_exists(tag: str):
    doc = cf.load_config()
    doc.setdefault("tags", {})  # Make sure [tags] section exists
    existing_tags = doc["tags"]
    if tag not in existing_tags:
        existing_tags[tag] = tag
            
        cf.save_config(doc)

def create_recur_schedule(recur_str: str) -> dict:
    """
    Interactively walks user through recurrence schedule creation.
    Example returns:
    { "interval": 1, "unit": "week", "days_of_week": [0,2,4] }
    """
    unit_map = {"d": "day", "w": "week", "m": "month", "y": "year"}
    
    while True:
        console.print("[cyan] Enter the interval to recur at. If you need specific weekdays, choose 'week'.")
        unit_input = typer.prompt("🗓️([d]ay, [w]eek, [m]onth, [y]ear)").lower().strip()
        if unit_input in unit_map:
            unit_full = unit_map[unit_input]
            break
        console.print("[red]Invalid unit. Enter d, w, m, or y.[/red]")

   
    while True:
        interval = typer.prompt("🔁 Enter recurrence interval number (e.g., Every # [unit from last response.])")
        if interval.isdigit() and int(interval) > 0:
            interval = int(interval)
            break
        console.print("[red]Please enter a positive integer for interval.[/red]")

   
    recur_dict = {
        "interval": interval,
        "unit": unit_full
    }

    # Step 3 (optional): Days of week for weekly interval
    if unit_full == "week":
        days_lookup = {"m": 0, "t": 1, "w": 2, "th": 3, "f": 4, "s": 5, "su": 6}
        console.print("📅 Specify days of the week for recurrence (e.g., m/t/w/th/f/s/su). Leave empty for the same weekday as today.")
        
        while True:
            days_input = typer.prompt("Days of week (separate with /)").lower().strip()
            if not days_input:
                recur_dict["days_of_week"] = [datetime.now().weekday()]  # default to today's weekday
                break
            day_parts = days_input.split("/")
            valid = True
            days_of_week = []
            for day_code in day_parts:
                if day_code not in days_lookup:
                    valid = False
                    console.print(f"[red]Invalid weekday '{day_code}'. Try again.[/red]")
                    break
                days_of_week.append(days_lookup[day_code])
            if valid:
                recur_dict["days_of_week"] = days_of_week
                break
    print(recur_dict)
    return recur_dict

def safe_format_notes(notes_raw):
    if isinstance(notes_raw, list):
        return " ".join(str(note) for note in notes_raw)
    elif isinstance(notes_raw, str):
        return notes_raw
    else:
        return "-"
