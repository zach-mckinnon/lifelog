# lifelog/commands/utils/shared_options.py
from typing import List, Optional
import typer

# ─── Core Task Options ───────────────────────────────────────────────────────────

category_option = typer.Option(
    "-c", "--cat",
    default=None,
    help="New category name",
    show_default=False,
)

project_option = typer.Option(
    "-p", "--proj",
    default=None,
    help="New project name",
    show_default=False,
)

due_option = typer.Option(
    "-d", "--due",
    default=None,
    help="New due date/time in ISO or relative format",
    show_default=False,
)

impt_option = typer.Option(
    "-i", "--impt",
    default=None,
    help="Importance from 1 (low) to 5 (high)",
    show_default=False,
)

recur_option = typer.Option(
    "-r", "--recur",
    default=None,
    help="Recurrence rule, e.g. daily, weekly, every:7d",
    show_default=False,
)

# ─── Shared Utilities ───────────────────────────────────────────────────────────

tags_option = typer.Option(
    "-t", "--tags",
    default=[],
    help="List of tags (e.g. +food +work). Space-separated, prefixed with +.",
    show_default=False,
)

notes_option = typer.Option(
    "-n", "--notes",
    default=None,
    help="Optional notes about this entry.",
    show_default=False,
)

past_option = typer.Option(
    "--past",
    default=None,
    help="Backdate by offset (e.g. -1h or -30m).",
    show_default=False,
)

# ─── Metric Definition Options ──────────────────────────────────────────────────

min_option = typer.Option(
    "--min",
    default=None,
    help="Minimum allowed value.",
    show_default=False,
)

max_option = typer.Option(
    "--max",
    default=None,
    help="Maximum allowed value.",
    show_default=False,
)

description_option = typer.Option(
    "-d", "--description",
    default="",
    help="Description of the metric.",
    show_default=False,
)

unit_option = typer.Option(
    "-u", "--unit",
    default=None,
    help="Unit of measure (e.g., oz, hrs).",
    show_default=False,
)

goal_option = typer.Option(
    "-g", "--goal",
    default=None,
    help="Target (sum) or count (occurrences).",
    show_default=False,
)

period_option = typer.Option(
    "--period",
    default="day",
    help="Period for goal: day|week|month|hour.",
    show_default=False,
)

kind_option = typer.Option(
    "-k", "--kind",
    default="sum",
    help="Goal type: sum (volume) or count (occurrences).",
    show_default=False,
)

new_name_option = typer.Option(
    "--name",
    default=None,
    help="Rename the tracker.",
    show_default=False,
)