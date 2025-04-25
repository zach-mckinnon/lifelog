import json
from datetime import datetime, date, time, timedelta
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
    LOG_FILE = cf.get_log_file()
    with open(LOG_FILE, "r") as f:
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
    LOG_FILE = cf.get_log_file()

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

    with open(LOG_FILE, "r") as f:
        entries = json.load(f)
    
    for e in entries:
        if e.get("tracker") == name:
             entry_ts = datetime.fromisoformat(e["timestamp"])

    return sum(1 for e in entries if e["metric"]==name and entry_ts>=cutoff)
