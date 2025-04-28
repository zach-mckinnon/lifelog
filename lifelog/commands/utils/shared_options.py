# lifelog/commands/utils/shared_options.py
'''
Lifelog Shared Options Module
This module provides shared options for various commands in the Lifelog CLI.
It includes options for task management, metric definitions, and time tracking.
These options are used to standardize command-line arguments across different commands.
'''

import re
from typing import List, Optional
import typer

task_schema = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "project": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
        "tags": {
            "type": "array",
            "items": {"type": "string"}
        },
        "impt": {"type": "integer"},
        "created": {"type": "string"},  # ISO datetime
        "due": {"type": ["string", "null"]},  # ISO datetime or None
        "status": {"type": "string"},
        "start": {"type": ["string", "null"]},
        "end": {"type": ["string", "null"]},
        "recur": {
            "oneOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "interval": {"type": "integer"},
                        "unit": {"type": "string"},
                        "days_of_week": {
                            "type": "array",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["interval", "unit"]
                }
            ]
        },
        "notes": {"type": ["string", "null"]},
        "tracking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "duration_minutes": {"type": "number"},
                    "notes": {"type": ["string", "null"]}
                },
                "required": ["start", "end", "duration_minutes"]
            }
        },
        "priority": {"type": "number"}
    },
    "required": ["id", "title", "created", "status"]
}

time_schema = {
    "type":"object",
    "properties":{
        "id": {"type":"string"},
        "name": {"type":"string"},
        "category": {"type":"string"},
        "project": {"type":"string"},
        "created": {"type":"string"},
        "start": {"type":"string"},
        "end": {"type":"string"},
        "duration": {"type":"integer"},
        "tags": {
            "type":"array",
            "items":{"type":"string"}
        },
        "notes": {"type":"string"}
    },
    "required": ["id", "name", "created"],
}

# ─── Core Task Options ───────────────────────────────────────────────────────────

category_option = typer.Option(
    None,
    "-c", "--cat",
    help="Category name (e.g. work, rest, personal_projects, socialEvents).",
    show_default=False,
)

project_option = typer.Option(
    None,
    "-pr", "--proj",
    help="Project name (e.g. client_followups, buildPythonApp).",
    show_default=False,
)

due_option = typer.Option(
    None,
    "-d", "--due",
    help="New due date/time in ISO or natural language format (e.g. 2023-10-01, tomorrow, next week, 1d, 2w, 1m, 5y)"
     "also set to today at specific time with 24 hour clock time: e.g. -d 18:00 (today at 6:00pm).",
    show_default=False,
)

impt_option = typer.Option(
    None,
    "-i", "--impt",
    help="Importance from 1 (low) to 5 (high)",
    show_default=False,
)

recur_option = typer.Option(
    None,
    "-r", "--recur",
    help="Recurrence rule, e.g. daily, weekly, every:7d",
    show_default=False,
)

# ─── Shared Utilities ───────────────────────────────────────────────────────────

tags_option = typer.Option(
    [],
    "-t", "--tags",
    help="List of tags (e.g. +food +work). Space-separated, prefixed with +.",
    show_default=False,
)

notes_option = typer.Option(
    None,
    help="Optional notes about this entry."
    "Must come before any other arguments that start with a dash (-) or after entire command, preceeded by (--).",
    show_default=False,
)

past_option = typer.Option(
    None,
    "--past",
    help="Backdate by offset (e.g. 1h, 2d or 30m).",
    show_default=False,
)

# ─── Metric Definition Options ──────────────────────────────────────────────────
# TODO: Better the goal definition options to be more user friendly and less verbose.

min_option = typer.Option(
    None,
    "--min",
    help="Minimum allowed value.",
    show_default=False,
)

max_option = typer.Option(
    None,
    "--max",
    help="Maximum allowed value.",
    show_default=False,
)

description_option = typer.Option(
    "",
    "-dsc", "--description",
    help="Description of the metric.",
    show_default=False,
)

unit_option = typer.Option(
    None,
    "-u", "--unit",
    help="Unit of measure (e.g., oz, hrs).",
    show_default=False,
)

goal_option = typer.Option(
    None,
    "-g", "--goal",
    help="Target (sum) or count (occurrences).",
    show_default=False,
)

period_option = typer.Option(
    "day",
    "--period",
    help="Period for goal: day|week|month|hour.",
    show_default=False,
)

kind_option = typer.Option(
    "sum",
    "-k", "--kind",
    help="Goal type: sum (volume) or count (occurrences).",
    show_default=False,
)

new_name_option = typer.Option(
    None,
    "--name",
    help="Rename the tracker.",
    show_default=False,
)