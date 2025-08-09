import typer
from enum import Enum
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from datetime import datetime
import pandas as pd
from lifelog.utils.db import track_repository
from lifelog.utils.shared_utils import filter_entries_for_current_period
from lifelog.utils.db.models import Tracker, Goal
app = typer.Typer()
console = Console()


class GoalKind(str, Enum):
    SUM = "sum"
    COUNT = "count"
    BOOL = "bool"
    STREAK = "streak"
    DURATION = "duration"
    MILESTONE = "milestone"
    REDUCTION = "reduction"
    RANGE = "range"
    PERCENTAGE = "percentage"
    REPLACEMENT = "replacement"
    AVERAGE = "average"


class Period(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


def get_description_for_goal_kind(kind: GoalKind) -> str:
    """Return a description for each goal kind to help users understand what it is"""
    descriptions = {
        GoalKind.SUM: "Track accumulated values over time (e.g., oz of water, pages read)",
        GoalKind.COUNT: "Track frequency of events (e.g., workouts per week)",
        GoalKind.BOOL: "Track yes/no completion (e.g., made bed today)",
        GoalKind.STREAK: "Track consecutive days of completion",
        GoalKind.DURATION: "Track time spent on activities",
        GoalKind.MILESTONE: "Track progress toward specific achievement points",
        GoalKind.REDUCTION: "Track decreasing specific behaviors",
        GoalKind.RANGE: "Track values within specific upper and lower bounds",
        GoalKind.PERCENTAGE: "Track completion percentage toward a larger objective",
        GoalKind.REPLACEMENT: "Track substitution of one behavior for another",
        GoalKind.AVERAGE: "Calculate averages with outlier detection and notes (e.g., mood analysis with context)",
    }
    return descriptions.get(kind, "No description available")


def create_goal_interactive(type: str) -> Dict[str, Any]:
    """Guide the user through creating a goal interactively"""
    console.print(
        Panel("[bold blue]Create a New Goal[/bold blue]", expand=False))

    if type in ["int", "float"]:
        allowed_kinds = [GoalKind.SUM, GoalKind.COUNT, GoalKind.MILESTONE,
                         GoalKind.RANGE, GoalKind.DURATION, GoalKind.PERCENTAGE,
                         GoalKind.REDUCTION, GoalKind.AVERAGE]
    elif type == "bool":
        allowed_kinds = [GoalKind.COUNT, GoalKind.BOOL, GoalKind.STREAK]
    elif type == "str":
        allowed_kinds = [GoalKind.COUNT, GoalKind.REPLACEMENT]
    else:
        console.print(
            "[bold red]Unsupported metric type for goals.[/bold red]")
        return None

    # Show goal kinds with descriptions
    console.print("[bold]Available Goal Types:[/bold]")
    for kind in allowed_kinds:
        console.print(
            f"[green]{kind.value}[/green]: {get_description_for_goal_kind(kind)}")

    # Get goal kind
    goal_kind_str = typer.prompt(
        "What type of goal would you like to create?",
        type=str,
        default=GoalKind.COUNT.value
    )
    try:
        goal_kind = GoalKind(goal_kind_str.lower())
    except ValueError:
        console.print(
            f"[bold red]Invalid goal type: {goal_kind_str}. Using default: {allowed_kinds[0].value}[/bold red]")
        goal_kind = allowed_kinds[0]

    if goal_kind not in allowed_kinds:
        console.print(
            f"[bold red]❌ That goal type is not allowed for a {type} tracker.[/bold red]")
        raise typer.Exit(code=1)

    # Get goal title
    title = typer.prompt(
        "Enter a title for your goal (e.g., 'Drink water', 'Exercise')")

    # Get period
    period_str = typer.prompt(
        "How often do you want to track this goal?",
        type=str,
        default=Period.DAY.value,
        show_choices=True,
        show_default=True
    )
    try:
        period = Period(period_str.lower())
    except ValueError:
        console.print(
            f"[bold red]Invalid period: {period_str}. Using default: {Period.DAY.value}[/bold red]")
        period = Period.DAY

    # Initialize goal
    goal: Dict[str, Any] = {
        "title": title,
        "kind": goal_kind.value,
        "period": period.value,
    }

    # Additional fields based on goal kind
    if goal_kind == GoalKind.BOOL:
        goal["amount"] = True
    elif goal_kind == GoalKind.RANGE:
        goal["min_amount"] = float(typer.prompt(
            "Enter minimum value", type=float))
        goal["max_amount"] = float(typer.prompt(
            "Enter maximum value", type=float))
        goal["unit"] = typer.prompt(
            "Enter unit (e.g., 'hours', 'miles', leave blank if none)", default="")
    elif goal_kind == GoalKind.REPLACEMENT:
        goal["old_behavior"] = typer.prompt("Enter behavior to replace")
        goal["new_behavior"] = typer.prompt("Enter replacement behavior")
        goal["amount"] = True
    elif goal_kind == GoalKind.PERCENTAGE:
        goal["target_percentage"] = float(typer.prompt(
            "Enter target percentage (0-100)", type=float))
        goal["current_percentage"] = 0.0
    elif goal_kind == GoalKind.MILESTONE:
        goal["target"] = float(typer.prompt("Enter target value", type=float))
        goal["current"] = 0.0
        goal["unit"] = typer.prompt(
            "Enter unit (e.g., 'books', 'miles', leave blank if none)", default="")
    elif goal_kind == GoalKind.STREAK:
        goal["current_streak"] = 0
        goal["best_streak"] = 0
        goal["target_streak"] = int(typer.prompt(
            "Enter target streak length", type=int))
    elif goal_kind == GoalKind.DURATION:
        goal["amount"] = float(typer.prompt(
            "Enter duration amount", type=float))
        goal["unit"] = typer.prompt(
            "Enter time unit (e.g., 'minutes', 'hours')", default="minutes")
    elif goal_kind in [GoalKind.SUM, GoalKind.COUNT, GoalKind.REDUCTION]:
        goal["amount"] = float(typer.prompt("Enter target amount", type=float))
        goal["unit"] = typer.prompt(
            "Enter unit (e.g., 'oz', 'times', 'pages', leave blank if none)", default="")
    elif goal_kind == GoalKind.AVERAGE:
        console.print(
            "[yellow]Average goals help analyze trends and identify outliers with context.[/yellow]")
        goal["min_expected"] = None
        goal["max_expected"] = None

        # Optional: Set expected range for outlier detection
        if typer.confirm("Do you want to set an expected range for outlier detection?", default=False):
            goal["min_expected"] = float(typer.prompt(
                "Enter minimum expected value", type=float))
            goal["max_expected"] = float(typer.prompt(
                "Enter maximum expected value", type=float))

        goal["outlier_threshold"] = float(typer.prompt(
            "Enter outlier threshold (standard deviations)", default=1.5, type=float))
        goal["unit"] = typer.prompt(
            "Enter unit (e.g., 'points', 'rating', leave blank if none)", default="")

    return goal


def calculate_goal_progress(tracker: Tracker) -> Dict[str, Any]:
    """
    Given a Tracker dataclass, calculate its first-goal progress summary.
    """
    # Fetch entries as dataclass instances
    entries = track_repository.get_entries_for_tracker(tracker.id)
    # If no entries, early return
    if not entries:
        return {
            "progress": 0,
            "status": "This tracker is ready for your first entry! 📝"
        }

    # Fetch goals (list of Goal dataclasses)
    goals = tracker.goals or track_repository.get_goals_for_tracker(tracker.id)
    if not goals:
        return {"progress": None, "status": "No goal set for this tracker."}

    # Use first goal
    goal = goals[0]
    kind = goal.kind
    period = getattr(goal, "period", None)

    # Build DataFrame from entries
    df_all = pd.DataFrame([e.to_dict() for e in entries])
    # Filter by period if needed
    if period:
        # filter_entries_for_current_period should accept DataFrame and return DataFrame
        df_filtered = filter_entries_for_current_period(df_all, period)
    else:
        df_filtered = df_all

    if df_filtered.empty:
        return {"progress": 0, "status": f"No entries yet for this {period} period."}

    progress: Dict[str, Any] = {}
    # Now handle each kind, using attribute access on goal and DataFrame columns
    if kind == "sum":
        total = df_filtered["value"].sum()
        target = getattr(goal, "amount", None)
        completed = (total >= target) if target is not None else False
        progress.update({
            "progress": total,
            "target": target,
            "completed": completed
        })
    elif kind == "count":
        count = len(df_filtered)
        target = getattr(goal, "amount", None)
        completed = (count >= target) if target is not None else False
        progress.update({
            "progress": count,
            "target": target,
            "completed": completed
        })
    elif kind == "bool":
        # Count distinct days where value True
        # Ensure timestamp parsed
        df_filtered["date"] = pd.to_datetime(df_filtered["timestamp"]).dt.date
        true_days = df_filtered[df_filtered["value"]].date.unique()
        num = len(true_days)
        progress.update({
            "progress": num,
            "target": 1,
            "completed": bool(num >= 1)
        })
    elif kind == "streak":
        # Example streak logic: count consecutive days up to today
        df_filtered["date"] = pd.to_datetime(df_filtered["timestamp"]).dt.date
        dates = sorted(df_filtered["date"].unique())
        today = datetime.today().date()
        streak = 0
        for d in reversed(dates):
            if (today - d).days == streak:
                streak += 1
            else:
                break
        target_streak = getattr(goal, "target_streak", None)
        completed = (
            streak >= target_streak) if target_streak is not None else False
        progress.update({
            "progress": streak,
            "target": target_streak,
            "completed": completed
        })
    elif kind == "duration":
        total = df_filtered["value"].sum()
        target = getattr(goal, "amount", None)
        completed = (total >= target) if target is not None else False
        progress.update({
            "progress": total,
            "target": target,
            "completed": completed
        })
    elif kind == "milestone":
        # Assume 'current' stored or sum entries?
        # If your model stores current separately, use that; else sum:
        current = df_filtered["value"].sum()
        target = getattr(goal, "target", None)
        completed = (current >= target) if target is not None else False
        progress.update({
            "progress": current,
            "target": target,
            "completed": completed
        })
    elif kind == "range":
        # Latest entry value
        latest = df_filtered["value"].iloc[-1]
        min_amt = getattr(goal, "min_amount", None)
        max_amt = getattr(goal, "max_amount", None)
        in_range = False
        if min_amt is not None and max_amt is not None:
            in_range = (min_amt <= latest <= max_amt)
        progress.update({
            "progress": latest,
            "target": (min_amt, max_amt),
            "completed": in_range
        })
    elif kind == "reduction":
        latest = df_filtered["value"].iloc[-1]
        target = getattr(goal, "amount", None)
        completed = (latest <= target) if target is not None else False
        progress.update({
            "progress": latest,
            "target": target,
            "completed": completed
        })
    elif kind == "percentage":
        # If entries store percent over time? Otherwise use stored current_percentage?
        latest_pct = df_filtered["value"].iloc[-1]
        target_pct = getattr(goal, "target_percentage", None)
        completed = (
            latest_pct >= target_pct) if target_pct is not None else False
        progress.update({
            "progress": latest_pct,
            "target": target_pct,
            "completed": completed
        })
    elif kind == "replacement":
        # E.g., positive values count new behavior, negative old
        new_count = (df_filtered["value"] > 0).sum()
        old_count = (df_filtered["value"] < 0).sum()
        total = new_count + old_count
        ratio = (new_count / total * 100) if total else 0
        completed = ratio >= 75
        progress.update({
            "progress": ratio,
            "target": 75,
            "completed": completed,
            "new_count": new_count,
            "old_count": old_count
        })
    elif kind == "average":
        import numpy as np

        # Calculate basic statistics
        values = df_filtered["value"]
        mean_val = values.mean()
        std_val = values.std()
        median_val = values.median()
        count = len(values)

        # Outlier detection using standard deviations
        outlier_threshold = getattr(goal, "outlier_threshold", 1.5)
        z_scores = np.abs((values - mean_val) /
                          std_val) if std_val > 0 else np.zeros(len(values))
        outlier_mask = z_scores > outlier_threshold

        # Get outliers with their context (notes, timestamps)
        outliers = []
        if outlier_mask.any():
            outlier_df = df_filtered[outlier_mask].copy()
            for _, row in outlier_df.iterrows():
                outlier_entry = {
                    "value": row["value"],
                    "timestamp": row["timestamp"],
                    "notes": row.get("notes", ""),
                    "z_score": z_scores[outlier_df.index.get_loc(row.name)]
                }
                outliers.append(outlier_entry)

        # Range validation if expected bounds are set
        min_expected = getattr(goal, "min_expected", None)
        max_expected = getattr(goal, "max_expected", None)
        in_expected_range = True

        if min_expected is not None and max_expected is not None:
            in_expected_range = min_expected <= mean_val <= max_expected

        # Trend analysis (simple: comparing first half vs second half)
        trend = "stable"
        if count >= 4:
            mid_point = count // 2
            first_half_mean = values.iloc[:mid_point].mean()
            second_half_mean = values.iloc[mid_point:].mean()
            diff_pct = ((second_half_mean - first_half_mean) /
                        first_half_mean * 100) if first_half_mean != 0 else 0

            if diff_pct > 10:
                trend = "increasing"
            elif diff_pct < -10:
                trend = "decreasing"

        progress.update({
            "progress": mean_val,
            "target": (min_expected, max_expected) if min_expected and max_expected else None,
            "completed": in_expected_range,
            "mean": mean_val,
            "median": median_val,
            "std_dev": std_val,
            "count": count,
            "outliers": outliers,
            "outlier_count": len(outliers),
            "trend": trend,
            "in_expected_range": in_expected_range
        })
    else:
        progress.update(
            {"progress": None, "status": "Unknown goal kind", "completed": False})

    # Add summary formatting if desired
    progress["summary"] = format_goal_progress_for_list_view(
        tracker, progress, goal)
    return progress


def format_goal_progress_for_list_view(tracker: Tracker, progress: Dict[str, Any], goal) -> str:
    """
    Format progress summary for display in CLI list.
    """
    kind = goal.kind
    value = progress.get("progress")
    target = progress.get("target")
    completed = progress.get("completed", False)
    check = "✓" if completed else "✗"

    if kind == "range":
        min_val, max_val = target if isinstance(
            target, tuple) else (None, None)
        return f"Now: {value} (range {min_val}-{max_val}) {check}"
    if kind == "sum":
        pct = round((value / target) * 100) if target else 0
        return f"{value} / {target} ({pct}%) {check}"
    if kind == "count":
        remaining = int(target) - int(value) if target is not None else None
        rem_str = f" ({remaining} left)" if remaining not in (None, 0) else ""
        return f"{value} / {target}{rem_str} {check}"
    if kind == "bool":
        return f"{value} day(s) completed {check}"
    if kind == "streak":
        return f"🔥 Streak: {value} / {target} {check}"
    if kind == "milestone":
        pct = round((value / target) * 100) if target else 0
        return f"{value} / {target} ({pct}%) {check}"
    if kind == "reduction":
        status = "Below target ✓" if completed else f"{value} > {target} ✗"
        return f"Now: {value} | Target: ≤{target} | {status}"
    if kind == "percentage":
        return f"{value}% of {target}% {check}"
    if kind == "replacement":
        new_count = progress.get("new_count", 0)
        old_count = progress.get("old_count", 0)
        return f"Replacing: {new_count} new / {old_count} old ({value:.1f}%) {check}"
    if kind == "average":
        mean_val = progress.get("mean", 0)
        outlier_count = progress.get("outlier_count", 0)
        trend = progress.get("trend", "stable")
        count = progress.get("count", 0)

        trend_icon = {"increasing": "📈", "decreasing": "📉",
                      "stable": "➡️"}.get(trend, "➡️")
        outlier_str = f", {outlier_count} outliers" if outlier_count > 0 else ""

        return f"Avg: {mean_val:.1f} ({count} entries{outlier_str}) {trend_icon} {check}"
    # Unknown
    return str(value)
