# lifelog/commands/report.py
import json
from typing import Dict, Any
from datetime import datetime, timedelta
import pandas as pd
from enum import Enum
import typer

from rich.table import Table
from rich.console import Console

from lifelog.commands.utils.db import report_repository
from lifelog.commands.utils.db import track_repository, time_repository
from lifelog.commands.utils.reporting.insight_engine import generate_insights

from lifelog.commands.utils.db import track_repository

app = typer.Typer(help="Generate a report for your goal progress.")


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


def generate_goal_report(tracker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a structured goal progress report for a tracker.
    Now pulls entries from SQL, not from embedded tracker object.
    """
    # 🆕 Safely parse goals from JSON string if needed
    goals_raw = tracker.get("goals")
    try:
        goals = json.loads(goals_raw) if isinstance(
            goals_raw, str) else goals_raw or []
    except Exception:
        goals = []

    # 🆕 Load entries directly from SQL
    entries = track_repository.get_entries_for_tracker(tracker["id"])

    df = pd.DataFrame(entries)

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

    # ✅ Use first goal for now
    goal = goals[0]
    kind = goal.get("kind")

    # Dispatch handlers (these functions stay the same)
    if kind == "range":
        return _report_range(tracker, goal, df)
    if kind == "sum":
        return _report_sum(tracker, goal, df)
    if kind == "count":
        return _report_count(tracker, goal, df)
    if kind == "bool":
        return _report_bool(tracker, goal, df)
    if kind == "streak":
        return _report_streak(tracker, goal, df)
    if kind == "duration":
        return _report_duration(tracker, goal, df)
    if kind == "milestone":
        return _report_milestone(tracker, goal, df)
    if kind == "reduction":
        return _report_reduction(tracker, goal, df)
    if kind == "percentage":
        return _report_percentage(tracker, goal, df)
    if kind == "replacement":
        return _report_replacement(tracker, goal, df)

    return {
        "report_type": "unknown",
        "status": f"Unknown goal kind: {kind}",
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


@app.command("insights")
def show_insights():
    insights = report_repository.get_correlation_insights()
    for i, ins in enumerate(insights, 1):
        print(f"{i}. {ins['note']} (Pearson: {ins['correlation']['pearson']})")


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


def _report_range(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    avg = df['value'].mean()
    min_val = df['value'].min()
    max_val = df['value'].max()
    latest = df['value'].iloc[-1]

    min_target = goal.get('min_amount')
    max_target = goal.get('max_amount')

    in_range = min_target <= latest <= max_target

    return {
        "report_type": ReportType.RANGE_MEASUREMENT.value,
        "completed": in_range,
        "metrics": {
            "avg": avg,
            "min": min_val,
            "max": max_val,
            "latest": latest
        },
        "display_format": {
            "primary": f"{latest} ({min_target}-{max_target})",
            "secondary": f"Avg: {avg:.1f}",
            "tertiary": f"Range {min_val}-{max_val}"
        },
        "status": "✓ In range" if in_range else "✗ Out of range"
    }


def _report_sum(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    total = df['value'].sum()
    target = goal.get('amount')

    pct = (total / target) * 100 if target else 0

    return {
        "report_type": ReportType.SUM_ACCUMULATION.value,
        "completed": total >= target,
        "metrics": {
            "total": total,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{total:.1f}/{target:.1f}",
            "secondary": f"{pct:.1f}%",
            "tertiary": f"{target-total:.1f} left" if total < target else "🎉 Congratulations! You've completed your goal!"
        },
        "status": "✓ Goal reached" if total >= target else "✨ You're making great progress! Keep it up!"
    }  # TODO: Add fun sayings from the json files of motivational quotes.


def _report_count(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    count = len(df)
    target = goal.get('amount')

    pct = (count / target) * 100 if target else 0

    return {
        "report_type": ReportType.COUNT_FREQUENCY.value,
        "completed": count >= target,
        "metrics": {
            "count": count,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{count}/{target}",
            "secondary": f"{pct:.1f}%",
            "tertiary": f"{target-count} left" if count < target else "🎉 Congratulations! You've completed your goal!"
        },
        "status": "✓ Goal reached" if count >= target else "⏳ Progressing"
    }


def _report_bool(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    true_count = df['value'].sum()
    total = len(df)

    pct = (true_count / total) * 100 if total else 0

    return {
        "report_type": ReportType.BOOL_COMPLETION.value,
        "completed": pct == 100.0,
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
        "status": "✓ All completed" if pct == 100 else "Partial completion"
    }


def _report_streak(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date

    dates = sorted(df['date'])
    today = datetime.today().date()

    # Calculate streak
    streak = 0
    for d in reversed(dates):
        if (today - d).days == streak:
            streak += 1
        else:
            break

    target = goal.get('target_amount', goal.get('target_streak', 0))

    return {
        "report_type": ReportType.STREAK_CURRENT.value,
        "completed": streak >= target,
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


def _report_duration(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    total_minutes = df['value'].sum()
    target_minutes = goal.get('target_amount', goal.get('amount', 0))
    unit = goal.get('unit', 'minutes')

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
        "completed": total_minutes >= target_minutes,
        "metrics": {
            "total_minutes": total_minutes,
            "target_minutes": target_minutes,
            "percent": pct
        },
        "display_format": {
            "primary": f"{format_time(total_minutes)} / {format_time(target_minutes)}",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": f"{target_minutes-total_minutes:.0f} minutes remaining" if total_minutes < target_minutes else "🎉 Congratulations! You've completed your goal!"
        },
        "status": "✓ Time goal reached!" if total_minutes >= target_minutes else "⏳ Keep accumulating"
    }


def _report_milestone(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    current = df['value'].sum()
    target = goal.get('target_amount', goal.get('target', 0))
    unit = goal.get('unit', '')

    pct = (current / target) * 100 if target else 0
    remaining = max(0, target - current)

    return {
        "report_type": ReportType.MILESTONE_PROGRESS.value,
        "completed": current >= target,
        "metrics": {
            "current": current,
            "target": target,
            "percent": pct
        },
        "display_format": {
            "primary": f"{current:.1f}/{target:.1f} {unit}",
            "secondary": f"{pct:.1f}% complete",
            "tertiary": f"{remaining:.1f} {unit} remaining" if remaining else "Completed!"
        },
        "status": "🏆 Milestone achieved!" if current >= target else "⏳ Progressing toward milestone"
    }


def _report_percentage(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    latest_pct = df['value'].iloc[-1]
    target_pct = goal.get('target_percentage', 100)

    completed = latest_pct >= target_pct

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


def _report_reduction(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    latest = df['value'].iloc[-1]
    target = goal.get('target_amount', goal.get('amount', 0))
    unit = goal.get('unit', '')

    improvement = "✓ Below target" if latest <= target else f"✗ Above target ({latest-target:+.1f})"

    return {
        "report_type": ReportType.REDUCTION_TREND.value,
        "completed": latest <= target,
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


def _report_replacement(tracker: Dict[str, Any], goal: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:

    # Here we assume positive values mean "new habit", negative = "old habit" if you log it this way
    new_behavior_count = df[df['value'] > 0].shape[0]
    old_behavior_count = df[df['value'] < 0].shape[0]
    total = new_behavior_count + old_behavior_count

    if total == 0:
        ratio = 0
    else:
        ratio = (new_behavior_count / total) * 100

    original = goal.get('original_habit', 'old habit')
    new = goal.get('new_habit', 'new habit')

    return {
        "report_type": ReportType.REPLACEMENT_RATIO.value,
        "completed": ratio >= 75,  # Assume 75% new behavior means "good replacement"
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
