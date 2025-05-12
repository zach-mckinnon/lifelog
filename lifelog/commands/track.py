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
import json

from lifelog.commands.report import generate_goal_report
from lifelog.commands.utils.shared_utils import parse_args, safe_format_notes
import lifelog.config.config_manager as cf
from lifelog.commands.utils.shared_options import category_option
from lifelog.commands.utils.goal_util import create_goal_interactive, calculate_goal_progress


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
    help="Add a new metric definition."
)
def add(
    title: str = typer.Argument(...,
                                help="The title of the activity you're tracking."),
    category: Optional[str] = category_option,
    type: TrackerType = typer.Option(..., "-t", "--type",
                                     help="The data type (int, float, bool, str)."),
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    '''
    Add a new metric definition to the tracker.
    '''
    now = datetime.now()
    try:
        if args != None:
            tags, notes = parse_args(args)
        else:
            tags, notes = [], []
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    if not title:
        raise ValueError(
            "Please ensure you have a title! How else will you know what to do??")

    trackers = load_trackers()

    for tracker in trackers:
        if tracker.get("title") == title:
            typer.echo(
                f"Looks like a tracker called '{title}' already exists! Would you like to try a different name or update the existing one?")
            raise typer.Exit(code=1)

    valid_types = ["int", "float", "bool", "str"]
    if type not in valid_types:
        typer.echo(
            f"Invalid type: '{type}'. Type must be one of these types: {', '.join(valid_types)}.")
        raise typer.Exit(code=1)

    doc = cf.load_config()
    existing_categories = cf.get_config_section("categories").keys()

    if category not in existing_categories and category != None:
        console.print(f"[yellow]⚠️ Category '{category}' not found.[/yellow]")
        if Confirm.ask(f"[yellow]Would you like to create it now?[/yellow]"):
            try:
                doc.setdefault("categories", {})
                doc["categories"][category] = category
                cf.save_config(doc)
                console.print(
                    f"[green]✅ Category '{category}' added to your config.[/green]")
            except Exception as e:
                console.print(
                    f"[bold red]Failed to create category: {e}[/bold red]")
                raise typer.Exit(code=1)

    if Confirm.ask("Would you like to add a goal to this tracker?"):
        goal = create_goal_interactive(type)
    else:
        goal = None

    # build your definition
    tracker_def = {
        "id": next_id(trackers),
        "title": title,
        "type": type.value,
        "category": category,
        "tags": tags if tags else [],
        "notes": notes if notes else [],
        "created": now.isoformat(),
        "goals": [goal] if goal else [],
    }

    trackers.append(tracker_def)
    save_tracker(trackers)
    typer.echo(f"✅ Added metric '{title}' with type '{type}'")


@app.callback(invoke_without_command=True)
def default_track(
    ctx: typer.Context,
    title_and_value: Optional[List[str]] = typer.Argument(None),
):
    """
    Record a new value or event for a tracker if no command is given.
    """
    now = datetime.now()
    if ctx.invoked_subcommand:
        return

    if not title_and_value or len(title_and_value) == 0:
        console.print("[bold red]❌ Please provide a tracker title.[/bold red]")
        raise typer.Exit(code=1)

     # SAFETY: check if user accidentally typed a real command like "add"
    command_names = ctx.command.list_commands(ctx)
    first = title_and_value[0].lower()

    if first in command_names:
        command = ctx.command.get_command(ctx, first)
        remaining_args = title_and_value[1:]

        if first == "add":
            if len(remaining_args) < 2:
                console.print(
                    "[bold red]❌ 'add' command needs at least a title and --type.[/bold red]")
                raise typer.Exit()

            # Parse 'walk' -t float
            title = remaining_args[0]
            opts = remaining_args[1:]

            # manual parsing
            opt_args = {}
            i = 0
            while i < len(opts):
                if opts[i] in ("-t", "--type"):
                    opt_args["type"] = opts[i+1]
                    i += 2
                elif opts[i] in ("-c", "--cat"):
                    opt_args["category"] = opts[i+1]
                    i += 2
                else:
                    # treat extras as 'args'
                    opt_args.setdefault("args", []).append(opts[i])
                    i += 1

            ctx.invoke(command, title=title, **opt_args)
            raise typer.Exit()

        elif first == "modify":
            if len(remaining_args) < 2:
                console.print(
                    "[bold red]❌ 'modify' command needs at least an id and title.[/bold red]")
                raise typer.Exit()

            id_ = int(remaining_args[0])
            title = remaining_args[1]
            opts = remaining_args[2:]

            opt_args = {}
            i = 0
            while i < len(opts):
                if opts[i] in ("-c", "--cat"):
                    opt_args["category"] = opts[i+1]
                    i += 2
                else:
                    # treat extras as args (tags/notes)
                    opt_args.setdefault("args", []).append(opts[i])
                    i += 1

            ctx.invoke(command, id=id_, title=title, **opt_args)
            raise typer.Exit()

        else:
            ctx.invoke(command, *remaining_args)
            raise typer.Exit()

    title = title_and_value[0]
    value = None
    if len(title_and_value) > 1:
        try:
            value = float(title_and_value[1])
        except ValueError:
            value = title_and_value[1]  # maybe a string for STR type trackers

    trackers = load_trackers()

    tracker = next(
        (t for t in trackers if t["title"].lower() == title.lower()), None)

    if not tracker:
        console.print(
            f"[bold red]🔍 We couldn't find a tracker called '{title}'. Would you like to create it? Use track add to create a new tracker![/bold red]")
        raise typer.Exit(code=1)

    goals = tracker.get("goals", [])

    value = validate_value_against_tracker(tracker, value)
    # -------- Record the entry --------
    entry = {
        "timestamp": now.isoformat(),
        "value": value
    }

    tracker.setdefault("entries", []).append(entry)

    save_tracker(trackers)
    console.print(
        f"[green]✅ Recorded value for '{title}'![/green] ➡️ [cyan]{value}[/cyan] at {entry['timestamp']}")

    # -------- If a goal exists, generate goal report --------
    if goals:
        goal = goals[0]

        report = generate_goal_report(tracker)

        console.print()
        console.rule("[bold blue]🎯 Goal Progress[/bold blue]")

        goal_title = goal.get("title", tracker["title"])

        for line in format_goal_display(goal_title, report):
            console.print(line)

    else:
        console.print("[italic]No active goal progress to show yet.[/italic]")


@app.command("modify")
def modify(
    id: int = typer.Argument(..., help="Tracker ID to modify"),
    title: str = typer.Argument(...,
                                help="The title of the activity you're tracking."),
    category: Optional[str] = category_option,
    args: Optional[List[str]] = typer.Argument(
        None, help="Optional +tags and notes."),
):
    """
    Modify an existing tracker: only title, category, tags, and notes.
    This is a safe modification command.
    Type, goal, and other structure cannot be modified.
    """
    try:
        if args != None:
            tags, notes = parse_args(args)
        else:
            tags, notes = [], []
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(code=1)

    trackers = load_trackers()

    tracker = next((t for t in trackers if t.get("id") == id), None)

    if not tracker:
        console.print(
            f"[bold red]❌ Tracker with ID {id} not found.[/bold red]")
        raise typer.Exit(code=1)

    # ---- Apply safe modifications only ----
    changes_made = False

    if title and title != tracker.get("title"):
        tracker["title"] = title
        changes_made = True

    if category and category != tracker.get("category"):
        tracker["category"] = category
        changes_made = True

    if tags:
        current_tags = tracker.get("tags", [])
        tracker["tags"] = current_tags + tags
    if notes:
        current_notes = tracker.get("notes", [])
        tracker["notes"] = current_notes.append(notes)

    if not changes_made:
        console.print(
            "[yellow]⚠️ No changes were made - you can always come back later when you're ready! ✌️[/yellow]")
        raise typer.Exit(code=0)

    # Save
    save_tracker(trackers)
    console.print(
        f"[green]✅ Tracker [bold]{id}[/bold] updated successfully.[/green]")


@app.command("list")
def list():
    """
    List all defined trackers with details.
    """

    trackers = load_trackers()

    if not trackers:
        console.print(
            "[italic]No trackers found. Add one with 'llog track add'![/italic]")
        return

    # Create the table
    table = Table(
        show_header=True,
        box=None,
        pad_edge=False,
        collapse_padding=True,
        padding=(0, 1),
        expand=True,
    )

    table.add_column("ID", justify="right", width=2)
    table.add_column("Title", overflow="ellipsis", min_width=8)
    table.add_column("Type", overflow="ellipsis", width=6)
    table.add_column("Cat", overflow="ellipsis", width=5)
    table.add_column("Goal", overflow="ellipsis", min_width=10)
    table.add_column("Progress", overflow="ellipsis", min_width=10)
    # Sort by ID ascending
    trackers = sorted(trackers, key=lambda t: t.get("id", 0))

    for t in trackers:
        id = str(t.get("id", "-"))
        title = t.get("title", "-")
        type_ = t.get("type", "-")
        category = t.get("category", "-")

        tags_raw = t.get("tags", [])
        tags = ", ".join(tags_raw) if tags_raw else "-"

        notes_raw = t.get("notes", [])
        notes = safe_format_notes(notes_raw)

        created_raw = t.get("created")
        created = "-"
        if created_raw:
            try:
                created_dt = datetime.fromisoformat(created_raw)
                created = created_dt.strftime("%m/%d/%y")
            except Exception:
                created = created_raw  # fallback

        # Always prepare goal_str and progress_display
        goals = t.get("goals", [])
        goal_str = "-"
        progress_display = "-"

        if goals:
            goal_title = goals[0].get("title", title)
            try:
                report = generate_goal_report(t)
                goal_str = goal_title
                progress_display = "\n".join(
                    format_goal_display(goal_title, report))
            except Exception as e:
                console.print(
                    f"[yellow]⚠️ Could not generate report for {title}: {e}[/yellow]")

        # Always add a row, even if goal or report failed
        table.add_row(
            id,
            title,
            type_,
            category,
            tags,
            notes,
            created,
            goal_str,
            progress_display
        )

    console.print(table)


def next_id(trackers):
    return max([t.get("id", 0) for t in trackers] + [0]) + 1


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


def load_trackers():
    TRACK_FILE = cf.get_track_file()
    if TRACK_FILE.exists():
        with open(TRACK_FILE, "r") as f:
            data = json.load(f)
            return data.get("trackers", [])  # safely pull "trackers"
    return []


def save_tracker(tracker_list):
    TRACK_FILE = cf.get_track_file()
    TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACK_FILE, "w") as f:
        json.dump({"trackers": tracker_list}, f, indent=2)


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
            goal_kind = goal.get("kind")

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


def validate_value_against_tracker(tracker: dict, value: Any) -> Any:
    """
    Validate a value against the tracker's expected type.
    If the type doesn't match, prompt the user until a valid value is given.
    """
    tracker_type = tracker.get("type")

    def _prompt_correct_value():
        if tracker_type == "int":
            return prompt("Enter an integer value", type=int)
        elif tracker_type == "float":
            return prompt("Enter a float value", type=float)
        elif tracker_type == "bool":
            resp = prompt("Enter true/false, yes/no, 1/0").lower()
            if resp in ["true", "yes", "y", "1"]:
                return 1
            elif resp in ["false", "no", "n", "0"]:
                return 0
            else:
                console.print("[bold red]Invalid boolean input.[/bold red]")
                return _prompt_correct_value()  # recursively ask again
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
                return int(value)
            if isinstance(value, (int, float)):
                return int(bool(value))
            if isinstance(value, str):
                if value.lower() in ["true", "yes", "y", "1"]:
                    return 1
                elif value.lower() in ["false", "no", "n", "0"]:
                    return 0
            raise ValueError  # force fallback to prompt
        elif tracker_type == "str":
            return str(value)
        else:
            raise typer.BadParameter(
                f"Unsupported tracker type '{tracker_type}'.")
    except (ValueError, TypeError):
        console.print(
            f"[bold red]⚠️ '{value}' is not a valid {tracker_type}. Let's try again.[/bold red]")
        return _prompt_correct_value()
