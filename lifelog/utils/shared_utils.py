# # lifelog.utils/shared_utils.py
'''
Lifelog Report Generation Module
This module provides functionality to generate various reports based on the user's data.
It includes features for generating daily, weekly, and monthly reports, as well as custom date range reports.
'''

from datetime import datetime, timedelta, timezone
from dateutil import tz
import logging
from dateutil.relativedelta import relativedelta

import re
from typing import List
import pandas as pd
from rich.console import Console
import typer
import lifelog.config.config_manager as cf
from lifelog.utils.db.models import Task

console = Console()


def now_utc() -> datetime:
    """
    Return current time as UTC-aware datetime.
    """
    return datetime.now(timezone.utc)


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


def calculate_priority(task: Task) -> float:
    if isinstance(task, dict):
        importance = task.get("importance", 3)
        due_val = task.get("due", None)
    else:  # assume Task instance
        importance = getattr(task, "importance", 3) or 3
        due_val = getattr(task, "due", None)
    urgency = 0.0
    if due_val:
        # due_val is likely a datetime already (repository parsed ISO into datetime)
        if isinstance(due_val, str):
            try:
                due_date = datetime.fromisoformat(due_val)
            except Exception:
                due_date = None
        else:
            due_date = due_val
        if due_date:
            days_left = (due_date - now_utc()).days
            urgency = max(0.0, 1.0 - days_left / 10)
    return (importance * 0.6) + (urgency * 0.4)


def parse_date_string(time_string: str, future: bool = False, now: datetime = now_utc()) -> datetime:
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
        now = now_utc()

    ts = time_string.strip()
    time_part = None
    base_part = ts
    target = None
    is_time_only = False

    if "." in ts:
        ts = ts.split(".", 1)[0]

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
    if time_part is None and not is_time_only:
        if target.tzinfo:
            local_dt = target.astimezone(get_user_timezone())
            target = local_dt.replace(
                hour=23, minute=59, second=0, microsecond=0)
            # then convert back to UTC if needed:
            target = target.astimezone(timezone.utc)
        else:
            target = target.replace(
                hour=23, minute=59, second=0, microsecond=0)

    if future and target < now:
        raise ValueError(
            f"Due date {target.strftime('%Y-%m-%d %H:%M')} is in the past")

    if target is None:
        raise ValueError(f"Could not parse: '{time_string}'")

    return target


def get_user_timezone():
    """
    Return a tzinfo object for the user’s configured timezone.
    - Reads config["location"]["timezone"] (IANA name, e.g., "America/Los_Angeles").
    - If missing or invalid, falls back to system local timezone.
    """
    try:
        cfg = cf.load_config()
        loc = cfg.get("location", {})
        tz_name = loc.get("timezone")
        if tz_name:
            user_tz = tz.gettz(tz_name)
            if user_tz is not None:
                return user_tz
            else:
                console.print(
                    f"[yellow]Warning: Unknown timezone '{tz_name}' in config; using system local.[/yellow]")
        # fallback
        return tz.tzlocal()
    except Exception as e:
        # If config load fails or other error, fallback to system local
        console.print(
            f"[yellow]Warning: Could not determine user timezone, defaulting to system local: {e}[/yellow]")
        return tz.tzlocal()


def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC-aware datetime.
    - If dt is naïve, interpret it as in user’s local timezone.
    - If dt is aware, convert from its tzinfo to UTC.
    Returns a datetime with tzinfo=datetime.timezone.utc.
    """
    if dt.tzinfo is None:
        # Interpret naïve dt as user-local
        user_tz = get_user_timezone()
        dt = dt.replace(tzinfo=user_tz)
    # Convert to UTC
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime) -> datetime:
    """
    Convert a datetime to the user’s local timezone.
    - If dt is naïve, interpret as UTC.
    - If dt is aware, convert from its tzinfo to user local.
    Returns a datetime with tzinfo set to user’s tz.
    """
    if dt.tzinfo is None:
        # Interpret naïve as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    user_tz = get_user_timezone()
    return dt.astimezone(user_tz)


def now_local() -> datetime:
    """
    Return current time in user’s local timezone (aware datetime).
    """
    # Generate now in UTC, then convert
    return now_utc().astimezone(get_user_timezone())


def local_to_utc_iso(dt_local: datetime) -> str:
    """
    Convert a datetime in user’s local timezone to an ISO-format UTC string.
    - If dt_local is naïve, interprets as local.
    - Returns ISO string with 'Z' (or +00:00).
    """
    dt_utc = to_utc(dt_local)
    # Use .isoformat(); for UTC you can append 'Z' if desired, but isoformat includes '+00:00'
    return dt_utc.isoformat()


def utc_iso_to_local(iso_str: str) -> datetime:
    """
    Parse an ISO-format UTC datetime string and convert to user’s local timezone.
    - If string has no tzinfo, assume UTC.
    - Returns a datetime with tzinfo=user local.
    """
    try:
        # datetime.fromisoformat can parse offsets: e.g. "2025-06-13T17:00:00+00:00"
        dt = datetime.fromisoformat(iso_str)
    except Exception as e:
        raise ValueError(f"Invalid ISO datetime string '{iso_str}': {e}")
    # If parsed dt is naïve, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return to_local(dt)


def format_datetime_for_user(dt: datetime) -> str:
    """
    Convert any datetime (naïve=assumed UTC, or aware) to the user's local tz,
    then format as MM/DD/YY HH:MM (24-hour).
    """
    # 1) If naïve, assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # 2) Convert to user-local tz
    local_dt = to_local(dt)
    # 3) Format
    return local_dt.strftime("%m/%d/%y %H:%M")


def parse_offset_to_timedelta(offset_str: str) -> timedelta:
    """
    Parse an offset string like '120' (minutes), '1d', '2h', '30m', '1w' into a timedelta.
    Raises ValueError if format unrecognized.
    """
    s = offset_str.strip().lower()
    if not s:
        raise ValueError("Empty offset")
    # Pure digits => minutes
    if s.isdigit():
        minutes = int(s)
        return timedelta(minutes=minutes)
    # Patterns: e.g. '1d', '2h', '30m', '1w'
    m = re.fullmatch(r'(\d+)([dhmw])', s)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        if unit == 'd':
            return timedelta(days=val)
        elif unit == 'h':
            return timedelta(hours=val)
        elif unit == 'm':
            return timedelta(minutes=val)
        elif unit == 'w':
            return timedelta(weeks=val)
    # Maybe allow 'Xm' or 'Xmin'?
    m2 = re.fullmatch(r'(\d+)(min|mins|minute|minutes)', s)
    if m2:
        val = int(m2.group(1))
        return timedelta(minutes=val)
    # Possibly allow 'Xh' already covered. If more complex needed, you could
    # try parse_date_string(s, future=True) - now, but that can be confusing
    # if parse_date_string interprets e.g. "tomorrow" as absolute date.
    raise ValueError(f"Unrecognized offset format: '{offset_str}'")


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
                recur_dict["days_of_week"] = [now_utc().weekday()]
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
    now = now_utc()
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
    if importance is not None and (not isinstance(importance, int) or importance < 0 or importance > 5):
        raise ValueError("Importance must be an integer between 0 and 5.")


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
