import typer
import json
from enum import Enum
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from datetime import datetime
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
    }
    return descriptions.get(kind, "No description available")


def create_goal_interactive(type: str) -> Dict[str, Any]:
    """Guide the user through creating a goal interactively"""
    console.print(Panel("[bold blue]Create a New Goal[/bold blue]", expand=False))
    
    if type in ["int", "float"]:
        allowed_kinds = [GoalKind.SUM, GoalKind.COUNT, GoalKind.MILESTONE, GoalKind.RANGE, GoalKind.DURATION, GoalKind.PERCENTAGE, GoalKind.REDUCTION]
    elif type == "bool":
        allowed_kinds = [GoalKind.COUNT, GoalKind.BOOL, GoalKind.STREAK]
    elif type == "str":
        allowed_kinds = [GoalKind.COUNT, GoalKind.REPLACEMENT]
    else:
        console.print("[bold red]Unsupported metric type for goals.[/bold red]")
        return None
    
    # Show goal kinds with descriptions
    console.print("[bold]Available Goal Types:[/bold]")
    for kind in allowed_kinds:
        console.print(f"[green]{kind.value}[/green]: {get_description_for_goal_kind(kind)}")
    
    # Get goal kind
    goal_kind_str = typer.prompt(
        "What type of goal would you like to create?",
        type=str,
        default=GoalKind.COUNT.value
    )
    try:
        goal_kind = GoalKind(goal_kind_str.lower())
    except ValueError:
        console.print(f"[bold red]Invalid goal type: {goal_kind_str}. Using default: {allowed_kinds[0].value}[/bold red]")
        goal_kind = allowed_kinds[0]
    
    if goal_kind not in allowed_kinds:
        console.print(f"[bold red]❌ That goal type is not allowed for a {type} tracker.[/bold red]")
        raise typer.Exit(code=1)
    
    # Get goal title
    title = typer.prompt("Enter a title for your goal (e.g., 'Drink water', 'Exercise')")
    
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
        console.print(f"[bold red]Invalid period: {period_str}. Using default: {Period.DAY.value}[/bold red]")
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
        goal["min_amount"] = float(typer.prompt("Enter minimum value", type=float))
        goal["max_amount"] = float(typer.prompt("Enter maximum value", type=float))
        goal["unit"] = typer.prompt("Enter unit (e.g., 'hours', 'miles', leave blank if none)", default="")
    elif goal_kind == GoalKind.REPLACEMENT:
        goal["old_behavior"] = typer.prompt("Enter behavior to replace")
        goal["new_behavior"] = typer.prompt("Enter replacement behavior")
        goal["amount"] = True
    elif goal_kind == GoalKind.PERCENTAGE:
        goal["target_percentage"] = float(typer.prompt("Enter target percentage (0-100)", type=float))
        goal["current_percentage"] = 0.0
    elif goal_kind == GoalKind.MILESTONE:
        goal["target"] = float(typer.prompt("Enter target value", type=float))
        goal["current"] = 0.0
        goal["unit"] = typer.prompt("Enter unit (e.g., 'books', 'miles', leave blank if none)", default="")
    elif goal_kind == GoalKind.STREAK:
        goal["current_streak"] = 0
        goal["best_streak"] = 0
        goal["target_streak"] = int(typer.prompt("Enter target streak length", type=int))
    elif goal_kind == GoalKind.DURATION:
        goal["amount"] = float(typer.prompt("Enter duration amount", type=float))
        goal["unit"] = typer.prompt("Enter time unit (e.g., 'minutes', 'hours')", default="minutes")
    elif goal_kind in [GoalKind.SUM, GoalKind.COUNT, GoalKind.REDUCTION]:
        goal["amount"] = float(typer.prompt("Enter target amount", type=float))
        goal["unit"] = typer.prompt("Enter unit (e.g., 'oz', 'times', 'pages', leave blank if none)", default="")

    
    return goal


def calculate_goal_progress(tracker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a tracker object, calculate its goal progress and return a summary
    including a formatted string for display.
    """
    entries = tracker.get("entries", [])
    if not entries:
        return {"progress": 0, "status": "This tracker is ready for your first entry! 📝"}

    goals = tracker.get("goals")
    if not goals:
        return {"progress": None, "status": "No goal set for this tracker."}

    goal = goals if isinstance(goals, dict) else goals[0]  # assume first goal if list
    goal_kind = goal.get("kind")
    progress = {}

    now = datetime.now()

    # SUM goal: accumulated total
    if goal_kind == GoalKind.SUM.value:
        total = sum(entry["value"] for entry in entries)
        progress.update({
            "progress": total,
            "target": goal["amount"],
            "completed": total >= goal["amount"]
        })

    # COUNT goal: count of entries
    elif goal_kind == GoalKind.COUNT.value:
        count = len(entries)
        progress.update({
            "progress": count,
            "target": goal["amount"],
            "completed": count >= goal["amount"]
        })

    # BOOL goal: number of distinct days with a True value
    elif goal_kind == GoalKind.BOOL.value:
        completed_days = {entry["timestamp"][:10] for entry in entries if entry["value"]}
        progress.update({
            "progress": len(completed_days),
            "target": 1,
            "completed": bool(completed_days)
        })

    # STREAK goal (placeholder implementation)
    elif goal_kind == GoalKind.STREAK.value:
        progress.update({
            "progress": 0,  # Implement real streak logic if needed
            "target": goal["target_streak"],
            "completed": False
        })

    # MILESTONE goal
    elif goal_kind == GoalKind.MILESTONE.value:
        current = goal.get("current", 0)
        progress.update({
            "progress": current,
            "target": goal["target"],
            "completed": current >= goal["target"]
        })

    # RANGE goal
    elif goal_kind == GoalKind.RANGE.value:
        latest_value = entries[-1]["value"]
        min_val = goal["min_amount"]
        max_val = goal["max_amount"]
        progress.update({
            "progress": latest_value,
            "target": f"{min_val}–{max_val}",
            "completed": min_val <= latest_value <= max_val
        })

    # REDUCTION goal
    elif goal_kind == GoalKind.REDUCTION.value:
        latest_value = entries[-1]["value"]
        target = goal["amount"]
        progress.update({
            "progress": latest_value,
            "target": target,
            "completed": latest_value <= target
        })

    # PERCENTAGE goal
    elif goal_kind == GoalKind.PERCENTAGE.value:
        current_pct = goal.get("current_percentage", 0)
        progress.update({
            "progress": current_pct,
            "target": goal["target_percentage"],
            "completed": current_pct >= goal["target_percentage"]
        })

    else:
        progress.update({"progress": "Unknown Goal Kind", "completed": False})

    # Add formatted summary to progress for CLI display
    progress["summary"] = format_goal_progress_for_list_view(tracker, progress)
    return progress


def format_goal_progress_for_list_view(tracker: dict, progress: dict) -> str:
    """
    Nicely format the progress report for a tracker in the list view.
    """
    goal = tracker.get("goals", [{}])[0]
    goal_kind = goal.get("kind")
    value = progress.get("progress")
    target = progress.get("target")
    completed = progress.get("completed")
    check = "✓" if completed else "✗"

    if goal_kind == "range":
        return f"Now: {value} / Target: {target} {check}"

    if goal_kind == "sum":
        pct = round((value / target) * 100) if target else 0
        return f"{value} / {target} ({pct}%) {check}"

    if goal_kind == "count":
        remaining = int(target) - int(value)
        return f"{value} / {target} ({remaining} left) {check}"

    if goal_kind == "bool":
        return f"{value} day(s) completed {check}"

    if goal_kind == "streak":
        return f"🔥 Streak: {value} / {target}"

    if goal_kind == "milestone":
        pct = round((value / target) * 100) if target else 0
        return f"{value} / {target} ({pct}%)"

    if goal_kind == "reduction":
        status = "✓ Below target" if completed else f"✗ {value} > {target}"
        return f"Now: {value} | Target: < {target} {status}"

    if goal_kind == "percentage":
        return f"{value}% of {target}% goal"

    if goal_kind == "replacement":
        old = goal.get("old_behavior", "?")
        new = goal.get("new_behavior", "?")
        return f"Replacing '{old}' ➡ '{new}' | {value}"

    return str(value)



