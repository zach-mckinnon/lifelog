# # lifelog.utils/shared_utils.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
The module uses JSON files for data storage and integrates with a cron job system for scheduling report generation.
'''

import base64
import json
from datetime import datetime, date, time, timedelta
import logging
import lifelog.config.config_manager as cf
from dateutil.relativedelta import relativedelta

import re
from typing import List
import pandas as pd
from rich.console import Console
import typer
import lifelog.config.config_manager as cf

console = Console()


def setup_logging():
    """Initialize logging to lifelog directory"""
    log_dir = cf.BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "llog.log"

    logging.basicConfig(
        filename=str(log_file),
        level=logging.ERROR,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger("llog")


def log_error(error_msg, traceback=None):
    """Log error with optional traceback"""
    logger = setup_logging()
    if traceback:
        logger.error(f"{error_msg}\n{traceback}")
    else:
        logger.error(error_msg)


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


def count_entries(name: str, since: str = "today") -> int:
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

    return sum(1 for e in entries if e["metric"] == name and entry_ts >= cutoff)


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
    is_time_only = False
    if "." in time_string:
        time_string = time_string.split(".")[0]
    # Handle "T" separator (e.g. 1dT18:00 or 4/5T17:00)
    if 'T' in ts:
        base_part, time_part = ts.split('T', 1)
    elif re.match(r'^\d{1,2}:\d{2}$', ts):
        base_part, time_part = '', ts
        is_time_only = True

    # Handle keyword dates
    if base_part in ('today', ''):
        target = now
    elif base_part == 'yesterday':
        target = now - timedelta(days=1)
    elif base_part == 'tomorrow':
        target = now + timedelta(days=1)

    # Handle relative durations like 1d, 2w, 3m, 1h, 30min
    elif re.fullmatch(r'(\d+(y|mn|w|d|h|m))+', base_part):
        # Find all matching segments
        units = re.findall(r'(\d+)(y|mn|w|d|h|m)', base_part)
        delta = timedelta()
        for value, unit in units:
            value = int(value)
            if unit == 'y':
                delta += relativedelta(years=value)
            elif unit == 'mn':
                delta = relativedelta(months=value)
            elif unit == 'w':
                delta += timedelta(weeks=value)
            elif unit == 'd':
                delta += timedelta(days=value)
            elif unit == 'h':
                delta += timedelta(hours=value)
            elif unit == 'm':
                delta += timedelta(minutes=value)
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
            target = target.replace(
                hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            raise ValueError(
                f"Invalid time part '{time_part}' in '{time_string}'")

    if is_time_only:
        if future:
            # if they want the next occurrence but we ended up in the past…
            if target < now:
                target = target + timedelta(days=1)
        else:
            # if they want the most recent but we ended up in the future…
            if target > now:
                target = target - timedelta(days=1)
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
        console.print(
            "[cyan] Enter the interval to recur at. If you need specific weekdays, choose 'week'.[/cyan]")
        unit_input = typer.prompt(
            "🗓️([d]ay, [w]eek, [m]onth, [y]ear)").lower().strip()
        if unit_input in unit_map:
            unit_full = unit_map[unit_input]
            break
        console.print("[red]Invalid unit. Enter d, w, m, or y.[/red]")

    while True:
        interval = typer.prompt(
            "🔁 Enter recurrence interval number (e.g., Every # [unit from last response.])")
        if interval.isdigit() and int(interval) > 0:
            interval = int(interval)
            break
        console.print(
            "[red]Please enter a positive integer for interval.[/red]")

    recur_dict = {
        "interval": interval,
        "unit": unit_full
    }

    # Step 3 (optional): Days of week for weekly interval
    if unit_full == "week":
        days_lookup = {"m": 0, "t": 1, "w": 2,
                       "th": 3, "f": 4, "s": 5, "su": 6}
        console.print(
            "📅 Specify days of the week for recurrence (e.g., m/t/w/th/f/s/su). Leave empty for the same weekday as today.")

        while True:
            days_input = typer.prompt(
                "Days of week (separate with /)").lower().strip()
            if not days_input:
                # default to today's weekday
                recur_dict["days_of_week"] = [datetime.now().weekday()]
                break
            day_parts = days_input.split("/")
            valid = True
            days_of_week = []
            for day_code in day_parts:
                if day_code not in days_lookup:
                    valid = False
                    console.print(
                        f"[red]Invalid weekday '{day_code}'. Try again.[/red]")
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


def user_friendly_empty_message(module="insights"):
    return f"No usable {module} data available yet. Please track more to generate valuable insights."


def filter_entries_for_current_period(entries, period: str):
    now = datetime.now()
    df = pd.DataFrame(entries)
    if df.empty:
        return df

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # If unknown period, return all entries
        return df

    return df[df['timestamp'] >= start]


def validate_task_inputs(title: str, importance: int = None, priority: float = None):
    if not title or len(title) > 60:
        raise ValueError("Task title must be 1-60 characters long.")
    if importance is not None and (not isinstance(importance, int) or importance < 0 or importance > 10):
        raise ValueError("Importance must be an integer between 0 and 10.")
    if priority is not None and (not isinstance(priority, (int, float)) or priority < 0 or priority > 10):
        raise ValueError("Priority must be a number between 0 and 10.")


def category_autocomplete(ctx: typer.Context, incomplete: str):
    # Show all available plus the incomplete if not in list
    options = get_available_categories()
    return [c for c in options if c.startswith(incomplete)]


def project_autocomplete(ctx: typer.Context, incomplete: str):
    options = get_available_projects()
    return [p for p in options if p.startswith(incomplete)]


def tag_autocomplete(ctx: typer.Context, incomplete: str):
    options = get_available_tags()
    return [t for t in options if t.startswith(incomplete)]


def get_available_categories() -> list:
    config = cf.load_config()
    return list(config.get("categories", {}).keys())


def add_category_to_config(category: str, description: str = ""):
    config = cf.load_config()
    cats = config.get("categories", {})
    cat_importances = config.get("category_importance", {})

    if category not in cats:
        cats[category] = description

        # Prompt for importance multiplier
        multiplier = typer.prompt(
            f"Enter importance multiplier for '{category}' (1.0 = normal)",
            default=1.0,
            type=float
        )
        cat_importances[category] = multiplier

        config["categories"] = cats
        config["category_importance"] = cat_importances
        cf.save_config(config)


def get_available_projects() -> list:
    config = cf.load_config()
    return list(config.get("projects", {}).keys())


def add_project_to_config(project: str, description: str = ""):
    config = cf.load_config()
    projs = config.get("projects", {})
    if project not in projs:
        projs[project] = description
        config["projects"] = projs
        cf.save_config(config)


def get_available_tags() -> list:
    config = cf.load_config()
    return list(config.get("tags", {}).keys())


def add_tag_to_config(tag: str, description: str = ""):
    config = cf.load_config()
    tags = config.get("tags", {})
    if tag not in tags:
        tags[tag] = description
        config["tags"] = tags
        cf.save_config(config)


def get_available_statuses() -> list:
    config = cf.load_config()
    return config.get("statuses", ["backlog", "active", "done"])


def get_available_priorities() -> list:
    config = cf.load_config()
    return config.get("priorities", [str(x) for x in range(0, 11)])
