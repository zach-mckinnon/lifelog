# lifelog/commands/track.py
'''
Lifelog CLI Track Module - Track and Log Metrics and Habits
This module provides functionality to add, modify, and log metrics and habits.
It includes commands to define new metrics, list existing ones, and log values for them.
It also allows for modifying existing metrics and marking habits as done.
'''
from enum import Enum
from typing import Any, List, Optional
import typer
from typer import prompt
from datetime import datetime

from lifelog.utils.db import track_repository
from lifelog.commands.report import generate_goal_report
from lifelog.utils.shared_utils import now_utc, parse_args, safe_format_notes
import lifelog.config.config_manager as cf
from lifelog.utils.shared_options import category_option
from lifelog.utils.goal_util import create_goal_interactive, calculate_goal_progress
from lifelog.utils.db.models import Tracker

from rich.console import Console
from rich.prompt import Confirm
from rich import box
from rich.table import Table


app = typer.Typer(
    help="Add or Log a single metric (e.g. mood, water, sleep, etc.)")
console = Console()


class TrackerType(str, Enum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STR = "str"

# TODO: Fix Tracking to be a bit more generic but allow for goals with a specifc structure for goals object inside tracker obj.


@app.command(
    help="Add a new tracker definition."
)
def add(
    title: str = typer.Argument(...,
                                help="The title of the metric you're tracking."),
    category: Optional[str] = category_option,
    type: str = typer.Option(..., "-t", "--type",
                             help="The data type (int, float, bool, str)."),
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    '''
    Add a new tracker definition to the database.
    '''
    now = now_utc()
    try:
        tags, notes = parse_args(args) if args else ([], [])
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    # Check if tracker already exists by title (now using dataclass)
    existing_trackers = track_repository.get_all_trackers()
    for tracker in existing_trackers:
        if getattr(tracker, "title", None) == title:
            console.print(
                f"[red]⚠️ Tracker '{title}' already exists.[/red] Use a different name or modify the existing one.")
            raise typer.Exit(code=1)

    # Validate type
    valid_types = ["int", "float", "bool", "str"]
    if type not in valid_types:
        console.print(
            f"[red]Invalid type '{type}'. Must be one of: {', '.join(valid_types)}.[/red]")
        raise typer.Exit(code=1)

    # Category check (optional)
    doc = cf.load_config()
    existing_categories = cf.get_config_section("categories").keys()
    if category and category not in existing_categories:
        console.print(f"[yellow]⚠️ Category '{category}' not found.[/yellow]")
        if Confirm.ask(f"[yellow]Would you like to create it now?[/yellow]"):
            doc.setdefault("categories", {})
            doc["categories"][category] = category
            cf.save_config(doc)
            console.print(
                f"[green]✅ Category '{category}' created.[/green]")

    # Goal setup
    goal = None
    if Confirm.ask("Would you like to add a goal to this tracker?"):
        goal = create_goal_interactive(type)
        # Goal validation is handled by the repository during insertion
    # Create Tracker dataclass

    tracker = Tracker(
        id=None,  # Will be auto-assigned by database
        title=title,
        type=type,
        category=category,
        created=now,  # Pass datetime object, not ISO string
        tags=",".join(tags) if tags else None,
        notes=" ".join(notes) if notes else None,
    )

    # Add to repo
    try:
        new_tracker = track_repository.add_tracker(tracker)
        tracker_id = new_tracker.id
        if goal:
            track_repository.add_goal(tracker_id=tracker_id, goal_data=goal)
    except Exception as e:
        console.print(f"[bold red]Failed to add tracker: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]✅ Added tracker '{title}' of type '{type}'.[/green]")


@app.command("modify")
def modify(
    id: int = typer.Argument(..., help="Tracker ID to modify"),
    title: str = typer.Argument(...,
                                help="The new title of the activity you're tracking."),
    category: Optional[str] = category_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Modify an existing tracker (title, category, tags, notes only).
    Type, goal, and structure are immutable.
    """
    try:
        tags, notes = parse_args(args) if args else ([], [])
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    tracker = track_repository.get_tracker_by_id(id)
    if not tracker:
        console.print(
            f"[bold red]❌ Tracker with ID {id} not found.[/bold red]")
        raise typer.Exit(code=1)

    updates = {}
    if title and title != tracker.title:
        updates["title"] = title
    if category and category != tracker.category:
        updates["category"] = category
    if tags:
        current_tags = tracker.tags or ""
        merged_tags = ",".join(filter(None, [current_tags, *tags]))
        updates["tags"] = merged_tags
    if notes:
        current_notes = tracker.notes or ""
        merged_notes = " ".join(filter(None, [current_notes, *notes]))
        updates["notes"] = merged_notes

    if not updates:
        console.print("[yellow]⚠️ No changes were made.[/yellow]")
        raise typer.Exit(code=0)

    try:
        track_repository.update_tracker(id, updates)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to update tracker: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]✅ Tracker [bold]{id}[/bold] updated successfully.[/green]")


@app.command("list")
def list_trackers(
    title_contains: Optional[str] = typer.Option(
        None, "--title-contains", "-tc", help="Filter by title containing text."),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category."),
):
    """
    List trackers with optional filtering by title or category.
    """
    trackers = track_repository.get_all_trackers(
        title_contains=title_contains,
        category=category
    )

    if not trackers:
        console.print(
            "[italic]No trackers found. Use 'llog track add' to create one.[/italic]")
        return

    table = Table(
        show_header=True,
        box=None,
        pad_edge=False,
        collapse_padding=True,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("ID", justify="right", width=4)
    table.add_column("Title", overflow="ellipsis", min_width=8)
    table.add_column("Cat", overflow="ellipsis", width=8)
    table.add_column("Goal", overflow="ellipsis", min_width=10)
    table.add_column("Progress", overflow="ellipsis", min_width=10)

    for t in trackers:
        tracker_id = str(t.id or "-")
        title = t.title
        category_str = t.category or "-"
        goals = track_repository.get_goals_for_tracker(t.id)
        goal_str = "-"
        progress_display = "-"
        if goals:
            goal = goals[0]
            goal_str = goal.title or title
            try:
                report = generate_goal_report(t)  # pass Tracker instance
                # format_goal_display expects (goal_title, report)
                progress_display = "\n".join(
                    format_goal_display(goal_str, report))
            except Exception as e:
                console.print(
                    f"[yellow]⚠️ Could not generate report for {title}: {e}[/yellow]")
        table.add_row(tracker_id, title, category_str,
                      goal_str, progress_display)

        console.print(table)


@app.command("delete")
def delete(
    id: int = typer.Argument(..., help="Tracker ID to delete"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt.")
):
    """
    Delete a tracker and all its entries.
    """
    tracker = track_repository.get_tracker_by_id(id)
    if not tracker:
        console.print(
            f"[bold red]❌ Tracker with ID {id} not found.[/bold red]")
        raise typer.Exit(code=1)

    if not force:
        console.print(
            f"[yellow]⚠️ This will permanently delete tracker '{tracker.title}' and all its entries.[/yellow]")
        if not Confirm.ask("Are you sure?"):
            console.print("[cyan]Deletion cancelled.[/cyan]")
            raise typer.Exit(code=0)

    try:
        track_repository.delete_tracker(id)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to delete tracker: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]🗑️ Tracker '{tracker.title}' deleted successfully.[/green]")


@app.command("goals-help")
def goals_help():
    """
    Show descriptions and usage examples of all supported goal types.
    """
    table = Table(
        title="[bold blue]🎯 Lifelog Goal Types[/bold blue]",
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        padding=(0, 1)
    )

    table.add_column("Goal Kind", style="bold")
    table.add_column("Description", style="cyan")
    table.add_column("Key Fields", style="green")

    table.add_row(
        "sum",
        "Track accumulated values over time (e.g., water intake).",
        "amount, unit"
    )
    table.add_row(
        "count",
        "Track the number of times an event occurs.",
        "amount, unit"
    )
    table.add_row(
        "bool",
        "Track if something was done (yes/no) at least once per period.",
        "None (implicitly True once any entry exists)"
    )
    table.add_row(
        "streak",
        "Track consecutive days of completion (e.g., meditation streak).",
        "target_streak"
    )
    table.add_row(
        "duration",
        "Track total time spent on an activity (e.g., study hours).",
        "amount, unit (minutes/hours)"
    )
    table.add_row(
        "milestone",
        "Track progress toward a specific goal (e.g., read 100 books).",
        "target, unit"
    )
    table.add_row(
        "reduction",
        "Track decreasing a behavior (e.g., reduce smoking).",
        "amount, unit (lower is better)"
    )
    table.add_row(
        "range (goal mode)",
        "Stay within a healthy range (e.g., weight between 120-150 lbs).",
        "min_amount, max_amount, mode='goal'"
    )
    table.add_row(
        "range (tracker mode)",
        "Just log entries on a defined scale (e.g., mood 1-10), no goal.",
        "min_amount, max_amount, mode='tracker'"
    )
    table.add_row(
        "percentage",
        "Track percentage progress toward a target (e.g., body fat % goal).",
        "target_percentage"
    )
    table.add_row(
        "replacement",
        "Track replacing an old behavior with a new one (e.g., soda ➡ water).",
        "old_behavior, new_behavior"
    )

    console.print(table)

    console.print(
        "\n[bold yellow]📘 Tip:[/bold yellow] You can add goals interactively when creating a tracker using [green]'llog track add'[/green].\n")
    console.print(
        "[bold green]Use [cyan]'llog track goals-help'[/cyan] anytime to review this list.[/bold green]")


def format_goal_display(goal_title: str, report: dict) -> List[str]:
    """
    Helper to format goal display for console output.
    """
    display_format = report.get("display_format", {})
    primary = display_format.get("primary", "-")
    secondary = display_format.get("secondary", "")
    tertiary = display_format.get("tertiary", "")
    status = report.get("status", "")

    lines = []
    lines.append(f"🔹 [bold]{goal_title}[/bold]: [green]{primary}[/green]")
    if secondary:
        lines.append(f"🔹 {secondary}")
    if tertiary:
        lines.append(f"🔹 {tertiary}")
    if status:
        if report.get("completed"):
            lines.append(f"[bold green]{status}[/bold green]")
        else:
            lines.append(f"[yellow]{status}[/yellow]")

    return lines


def validate_type(title: str, value: str):
    """Validate a metric value against its definition and any associated goals"""
    definition = cf.get_tracker_definition(title)
    if not definition:
        raise typer.BadParameter(
            f"Metric '{title}' is not defined in the config.")

    expected_type = definition.get("type")
    min_val = definition.get("min")
    max_val = definition.get("max")

    # Parse the value according to the expected type
    try:
        if expected_type == "int":
            value = int(value)
        elif expected_type == "float":
            value = float(value)
        elif expected_type == "bool":
            if value.lower() in ["true", "yes", "1"]:
                value = True
            elif value.lower() in ["false", "no", "0"]:
                value = False
            else:
                raise ValueError("Expected a boolean value (true/false).")
        else:
            value = str(value)
    except ValueError:
        raise typer.BadParameter(
            f"Value '{value}' is not a valid {expected_type}.")

    # Basic validation (min/max)
    if isinstance(value, (int, float)):
        if min_val is not None and value < min_val:
            raise typer.BadParameter(
                f"Value is below the minimum allowed ({min_val}).")
        if max_val is not None and value > max_val:
            raise typer.BadParameter(
                f"Value is above the maximum allowed ({max_val}).")

    # Validate against goals if they exist
    goals = definition.get("goals", [])
    if goals:
        for goal in goals:
            goal_kind = goal.kind

            # Validate based on goal type
            if goal_kind == "range" and isinstance(value, (int, float)):
                min_amount = goal.get("min_amount")
                max_amount = goal.get("max_amount")
                if min_amount is not None and max_amount is not None:
                    if not (min_amount <= value <= max_amount):
                        # This is not an error, just information
                        console.print(
                            f"[yellow]Note: Value {value} is outside the goal range ({min_amount}-{max_amount}).[/yellow]")

            elif goal_kind in ["sum", "count", "milestone", "duration", "reduction"] and isinstance(value, (int, float)):
                target = goal.get("amount") or goal.get("target", 0)
                if goal_kind == "reduction" and value < target:
                    console.print(
                        f"[green]Great! Value {value} is below your reduction target of {target}.[/green]")
                elif goal_kind != "reduction" and value >= target:
                    console.print(
                        f"[green]Goal achieved! Value {value} meets or exceeds your target of {target}.[/green]")

    return value


def validate_value_against_tracker(tracker: Tracker, value: Any) -> Any:
    """
    Validate a value against the tracker's expected type.
    If invalid, prompt again.
    """
    tracker_type = tracker.type  # use attribute

    def _prompt_correct_value():
        if tracker_type == "int":
            return prompt("Enter an integer value", type=int)
        elif tracker_type == "float":
            return prompt("Enter a float value", type=float)
        elif tracker_type == "bool":
            resp = prompt("Enter true/false, yes/no, 1/0").lower()
            if resp in ["true", "yes", "1"]:
                return True
            elif resp in ["false", "no", "0"]:
                return False
            console.print("[bold red]Invalid boolean input.[/bold red]")
            return _prompt_correct_value()
        elif tracker_type == "str":
            return prompt("Enter a string value")
        else:
            raise typer.BadParameter(
                f"Unsupported tracker type '{tracker_type}'.")

    try:
        if tracker_type == "int":
            return int(value)
        elif tracker_type == "float":
            return float(value)
        elif tracker_type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                if value.lower() in ["true", "yes", "y", "1"]:
                    return True
                if value.lower() in ["false", "no", "n", "0"]:
                    return False
            raise ValueError
        elif tracker_type == "str":
            return str(value)
        else:
            raise typer.BadParameter(
                f"Unsupported tracker type '{tracker_type}'.")
    except (ValueError, TypeError):
        console.print(
            f"[bold red]⚠️ '{value}' is not a valid {tracker_type}. Let's try again.[/bold red]")
        return _prompt_correct_value()


@app.command("log")
def log_entry(
    tracker_identifier: str = typer.Argument(...,
                                             help="Tracker name or ID to log entry for"),
    value: str = typer.Argument(...,
                                help="Value to log (int, float, bool, or string)"),
    notes: Optional[str] = typer.Option(
        None, "--notes", "-n", help="Optional notes for this entry"),
    timestamp: Optional[str] = typer.Option(
        None, "--time", "-t", help="Custom timestamp (default: now)")
):
    """
    Log a value for an existing tracker. You can use the tracker name or ID.

    Examples:
      llog track log "Mood" 7 --notes "Feeling great after exercise"
      llog track log mood 7 -n "Post-workout mood"
      llog track log 1 7             # by ID
    """
    try:
        # Try to find tracker by name or ID
        tracker = None

        # First try as ID if it's numeric
        if tracker_identifier.isdigit():
            tracker_id = int(tracker_identifier)
            tracker = track_repository.get_tracker_by_id(tracker_id)

        # If not found or not numeric, search by name
        if not tracker:
            all_trackers = track_repository.get_all_trackers()

            # Exact match first
            for t in all_trackers:
                if t.title.lower() == tracker_identifier.lower():
                    tracker = t
                    break

            # Fuzzy match if no exact match
            if not tracker:
                matches = []
                for t in all_trackers:
                    if tracker_identifier.lower() in t.title.lower():
                        matches.append(t)

                if len(matches) == 1:
                    tracker = matches[0]
                elif len(matches) > 1:
                    console.print(
                        f"[yellow]Multiple trackers match '{tracker_identifier}':[/yellow]")
                    for i, t in enumerate(matches, 1):
                        console.print(f"  {i}. {t.title} (ID: {t.id})")

                    try:
                        choice = typer.prompt("Select number", type=int)
                        if 1 <= choice <= len(matches):
                            tracker = matches[choice - 1]
                        else:
                            console.print(
                                "[bold red]❌ Invalid selection.[/bold red]")
                            raise typer.Exit(code=1)
                    except (KeyboardInterrupt, typer.Abort):
                        console.print("[yellow]Operation cancelled.[/yellow]")
                        raise typer.Exit(code=0)

        if not tracker:
            console.print(
                f"[bold red]❌ No tracker found matching '{tracker_identifier}'.[/bold red]")
            console.print(
                "[dim]Use 'llog track list' to see available trackers.[/dim]")
            raise typer.Exit(code=1)

        # Convert value to appropriate type
        if tracker.type == "int":
            typed_value = int(value)
        elif tracker.type == "float":
            typed_value = float(value)
        elif tracker.type == "bool":
            typed_value = value.lower() in ('true', '1', 'yes', 'y', 'on')
        elif tracker.type == "str":
            typed_value = str(value)
        else:
            console.print(
                f"[bold red]❌ Unsupported tracker type: {tracker.type}[/bold red]")
            raise typer.Exit(code=1)

        # Use current time if no timestamp provided
        log_time = timestamp if timestamp else now_utc()

        # Add the entry
        entry = track_repository.add_tracker_entry(
            tracker.id, log_time, typed_value, notes)

        console.print(
            f"[green]✅ Logged {value} for '{tracker.title}' (ID: {tracker.id})[/green]")
        if notes:
            console.print(f"[dim]   Notes: {notes}[/dim]")

    except ValueError as e:
        console.print(
            f"[bold red]❌ Invalid value '{value}' for tracker type '{tracker.type}': {e}[/bold red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to log entry: {e}[/bold red]")
        raise typer.Exit(code=1)
