# lifelog/commands/report.py
from enum import Enum
from lifelog.utils.db.models import Tracker
from lifelog.utils.db import track_repository
import lifelog.config.config_manager as cf
from lifelog.utils.db import track_repository, time_repository
from lifelog.utils.db import report_repository
from lifelog.utils.db import environment_repository, task_repository
from rich.console import Console
from rich.table import Table
import typer
import toml
import json
from typing import Dict, Any
from datetime import datetime
_pd = None


def get_pandas():
    """Lazy load pandas only when needed for reports"""
    global _pd
    if _pd is None:
        import pandas as pd
        _pd = pd
    return _pd


app = typer.Typer(help="Generate a report for your goal progress.")
console = Console()


class ReportType(str, Enum):
    RANGE_MEASUREMENT = "range_measurement"
    SUM_ACCUMULATION = "sum_accumulation"
    COUNT_FREQUENCY = "count_frequency"
    BOOL_COMPLETION = "bool_completion"
    STREAK_CURRENT = "streak_current"
    DURATION_TIME = "duration_time"
    MILESTONE_PROGRESS = "milestone_progress"
    REDUCTION_TREND = "reduction_trend"
    PERCENTAGE_PROGRESS = "percentage_progress"
    REPLACEMENT_RATIO = "replacement_ratio"
    UNKNOWN = "unknown"


def generate_goal_report(tracker: Tracker) -> Dict[str, Any]:
    """
    Generate a structured goal progress report for a given Tracker instance.
    Pulls entries and goals from SQL.
    """
    goals = track_repository.get_goals_for_tracker(tracker.id)
    entries = track_repository.get_entries_for_tracker(tracker.id)

    pd = get_pandas()  # Lazy load pandas
    if entries:
        entry_dicts = [e.to_dict() for e in entries]
        df = pd.DataFrame(entry_dicts)
    else:
        df = pd.DataFrame(
            columns=["id", "tracker_id", "timestamp", "value", "uid"])

    if df.empty:
        return {
            "report_type": "empty",
            "status": "This tracker is ready for your first entry! 📝",
            "completed": False,
            "display_format": {
                "primary": "-",
                "secondary": "-",
                "tertiary": "-"
            },
            "metrics": {}
        }

    if not goals:
        return {
            "report_type": "no_goal",
            "status": "No goal defined.",
            "completed": False,
            "display_format": {
                "primary": "-",
                "secondary": "-",
                "tertiary": "-"
            },
            "metrics": {}
        }

    goal = goals[0]
    goal_id = goal.id
    kind = goal.kind

    if kind == "range":
        details = track_repository.get_goal_range(goal_id)
        return _report_range(tracker, goal, details, df)
    if kind == "sum":
        details = track_repository.get_goal_sum(goal_id)
        return _report_sum(tracker, goal, details, df)
    if kind == "count":
        details = track_repository.get_goal_count(goal_id)
        return _report_count(tracker, goal, details, df)
    if kind == "bool":
        return _report_bool(tracker, goal, {}, df)
    if kind == "streak":
        details = track_repository.get_goal_streak(goal_id)
        return _report_streak(tracker, goal, details, df)
    if kind == "duration":
        details = track_repository.get_goal_duration(goal_id)
        return _report_duration(tracker, goal, details, df)
    if kind == "milestone":
        details = track_repository.get_goal_milestone(goal_id)
        return _report_milestone(tracker, goal, details, df)
    if kind == "reduction":
        details = track_repository.get_goal_reduction(goal_id)
        return _report_reduction(tracker, goal, details, df)
    if kind == "percentage":
        details = track_repository.get_goal_percentage(goal_id)
        return _report_percentage(tracker, goal, details, df)
    if kind == "replacement":
        details = track_repository.get_goal_replacement(goal_id)
        return _report_replacement(tracker, goal, details, df)

    return _empty_report(f"Unknown goal kind: {kind}")


def _empty_report(status):
    return {
        "report_type": "empty",
        "status": status,
        "completed": False,
        "display_format": {
            "primary": "-",
            "secondary": "-",
            "tertiary": "-"
        },
        "metrics": {}
    }


@app.command("summary-trackers")
def summary_trackers(since_days: int = 7):
    df = report_repository.get_tracker_summary(since_days)
    print_dataframe(df)


@app.command("summary-time")
def summary_time(since_days: int = 7):
    df = report_repository.get_time_summary(since_days)
    print_dataframe(df)


@app.command("daily-tracker")
def daily_tracker(metric_name: str, since_days: int = 7):
    df = report_repository.get_daily_tracker_averages(metric_name, since_days)
    print_dataframe(df)


def print_dataframe(df):
    if df.empty:
        print("[yellow]⚠️ No data found.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold magenta")
    for col in df.columns:
        table.add_column(col)
    for _, row in df.iterrows():
        table.add_row(*[str(val) for val in row])
    console = Console()
    console.print(table)


def _report_range(tracker, goal, details, df):
    if df.empty:
        return _empty_report("No data available for range analysis")

    pd = get_pandas()  # Lazy load pandas
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    latest_value = df['value'].iloc[-1]
    min_val = details["min_amount"]
    max_val = details["max_amount"]
    mode = details.get("mode", "goal")

    if mode == "goal":
        completed = bool(min_val <= latest_value <= max_val)
        status = "✓ In range" if completed else "✗ Out of range"
    else:
        completed = False
        status = f"Scale entry logged: {latest_value} (range {min_val}-{max_val})"

    return {
        "report_type": ReportType.RANGE_MEASUREMENT.value,
        "completed": completed,
        "metrics": {
            "latest": latest_value,
            "min": min_val,
            "max": max_val
        },
        "display_format": {
            "primary": f"{latest_value} ({min_val}-{max_val})",
            "secondary": "",
            "tertiary": ""
        },
        "status": status
    }


def _report_sum(tracker, goal, details, df):
    if df.empty:
        return _empty_report("No data available for sum analysis")

    total = df['value'].sum()
    target = details['amount']

    pct = (total / target) * 100 if target else 0
    completed = bool(total >= target)
    return {
        "report_type": ReportType.SUM_ACCUMULATION.value,
        "completed": completed,
        "metrics": {
            "total": total,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{total:.1f}/{target:.1f}",
            "secondary": f"{pct:.1f}%",
            "tertiary": f"{target-total:.1f} left" if total < target else "🎉 Goal completed!"
        },
        "status": "✓ Goal reached" if total >= target else "⏳ Keep going"
    }


def _report_count(tracker, goal, details, df):
    count = len(df)
    target = details['amount']

    pct = (count / target) * 100 if target else 0

    return {
        "report_type": ReportType.COUNT_FREQUENCY.value,
        "completed": bool(count >= target),
        "metrics": {
            "count": count,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{count}/{target}",
            "secondary": f"{pct:.1f}%",
            "tertiary": f"{target-count} left" if count < target else "🎉 Completed"
        },
        "status": "✓ Goal reached" if count >= target else "⏳ Progressing"
    }


def _report_bool(tracker, goal, df):
    true_count = df['value'].sum()
    total = len(df)

    pct = (true_count / total) * 100 if total else 0

    return {
        "report_type": ReportType.BOOL_COMPLETION.value,
        "completed": bool(pct == 100.0),
        "metrics": {
            "true": true_count,
            "false": total-true_count,
            "percent": pct
        },
        "display_format": {
            "primary": f"{true_count}/{total} days",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": ""
        },
        "status": "✓ All completed" if pct == 100 else "⏳ Partial completion"
    }


def _report_streak(tracker, goal, details, df):
    pd = get_pandas()  # Lazy load pandas
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date

    dates = sorted(df['date'])
    today = datetime.today().date()

    streak = 0
    for d in reversed(dates):
        if (today - d).days == streak:
            streak += 1
        else:
            break

    target = details['target_streak']

    return {
        "report_type": ReportType.STREAK_CURRENT.value,
        "completed": bool(streak >= target),
        "metrics": {
            "streak": streak,
            "target": target
        },
        "display_format": {
            "primary": f"{streak} days",
            "secondary": f"Target: {target} days",
            "tertiary": ""
        },
        "status": "🔥 Streak growing!" if streak < target else "🏆 Target Streak Achieved"
    }


def _report_duration(tracker, goal, details, df):
    total_minutes = df['value'].sum()
    target_minutes = details['amount']
    unit = details.get('unit', 'minutes')

    pct = (total_minutes / target_minutes) * 100 if target_minutes else 0

    def format_time(minutes):
        if unit.lower() == "minutes" and minutes >= 60:
            hours = int(minutes // 60)
            mins = int(minutes % 60)
            return f"{hours}h {mins}m"
        else:
            return f"{minutes:.0f} {unit}"

    return {
        "report_type": ReportType.DURATION_TIME.value,
        "completed": bool(total_minutes >= target_minutes),
        "metrics": {
            "total_minutes": total_minutes,
            "target_minutes": target_minutes,
            "percent": pct
        },
        "display_format": {
            "primary": f"{format_time(total_minutes)} / {format_time(target_minutes)}",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": f"{target_minutes-total_minutes:.0f} minutes remaining" if total_minutes < target_minutes else "🎉 Goal done!"
        },
        "status": "✓ Goal reached!" if total_minutes >= target_minutes else "⏳ Keep going"
    }


def _report_milestone(tracker, goal, details, df):
    if df.empty:
        return _empty_report("No data available for milestone analysis")

    current = df['value'].sum()
    target = details['target']
    unit = details.get('unit', '')

    stable = len(df) >= 2 and df['value'].iloc[-1] == df['value'].iloc[-2]
    completed = bool(current >= target and stable)

    pct = (current / target) * 100 if target else 0
    remaining = max(0, target - current)

    return {
        "report_type": ReportType.MILESTONE_PROGRESS.value,
        "completed": completed,
        "metrics": {
            "current": current,
            "target": target,
            "percent": pct,
        },
        "display_format": {
            "primary": f"{current:.1f}/{target:.1f} {unit}",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": f"{remaining:.1f} {unit} remaining" if remaining else "Completed!",
        },
        "status": "🏆 Milestone achieved!" if completed else "⏳ Progressing toward milestone",
    }


def _report_percentage(tracker, goal, details, df):
    if df.empty:
        return _empty_report("No data available for percentage analysis")

    latest_pct = df['value'].iloc[-1]
    target_pct = details['target_percentage']

    completed = bool(latest_pct >= target_pct
                     )
    return {
        "report_type": ReportType.PERCENTAGE_PROGRESS.value,
        "completed": completed,
        "metrics": {
            "current_percentage": latest_pct,
            "target_percentage": target_pct
        },
        "display_format": {
            "primary": f"{latest_pct:.1f}% / {target_pct}%",
            "secondary": f"{(latest_pct/target_pct)*100:.1f}% of goal",
            "tertiary": "✓ Reached" if completed else f"{target_pct-latest_pct:.1f}% remaining"
        },
        "status": "🏆 Target percentage reached!" if completed else "⏳ Keep progressing"
    }


def _report_reduction(tracker, goal, details, df):
    if df.empty:
        return _empty_report("No data available for reduction analysis")

    latest = df['value'].iloc[-1]
    target = details['amount']
    unit = details.get('unit', '')

    improvement = "✓ Below target" if latest <= target else f"✗ Above target ({latest-target:+.1f})"

    return {
        "report_type": ReportType.REDUCTION_TREND.value,
        "completed": bool(latest <= target),
        "metrics": {
            "latest": latest,
            "target": target
        },
        "display_format": {
            "primary": f"{latest} {unit}",
            "secondary": f"Target: {target} {unit}",
            "tertiary": improvement
        },
        "status": improvement
    }


def _report_replacement(tracker, goal, details, df):
    new_behavior_count = df[df['value'] > 0].shape[0]
    old_behavior_count = df[df['value'] < 0].shape[0]
    total = new_behavior_count + old_behavior_count

    ratio = (new_behavior_count / total) * 100 if total else 0

    original = details.get('old_behavior', 'old habit')
    new = details.get('new_behavior', 'new habit')

    return {
        "report_type": ReportType.REPLACEMENT_RATIO.value,
        "completed": bool(ratio >= 75),
        "metrics": {
            "new_behavior": new_behavior_count,
            "old_behavior": old_behavior_count,
            "replacement_ratio": ratio
        },
        "display_format": {
            "primary": f"{new_behavior_count}:{old_behavior_count} replacements",
            "secondary": f"{ratio:.1f}% new behavior",
            "tertiary": f"Replacing '{original}' ➡ '{new}'"
        },
        "status": "✅ Strong replacement habit!" if ratio >= 75 else "🔄 Still replacing..."
    }


def gather_all_data():
    trackers = track_repository.get_all_trackers()
    tracker_entries = []
    for t in trackers:
        tracker_entries.extend(track_repository.get_entries_for_tracker(t.id))
    return {
        "tasks": task_repository.get_all_tasks(),
        "trackers": trackers,
        "tracker_entries": tracker_entries,
        "goals": [g for t in trackers for g in track_repository.get_goals_for_tracker(t.id)],
        "time_logs": time_repository.get_all_time_logs(),
        "environment": environment_repository.get_all_environmental_data() if hasattr(environment_repository, "get_all_environmental_data") else [],
    }
