# lifelog/commands/utils/shared_options.py
'''
Lifelog Shared Options Module
This module provides shared options for various commands in the Lifelog CLI.
It includes options for task management, metric definitions, and time tracking.
These options are used to standardize command-line arguments across different commands.
'''


import typer

from commands.utils.shared_utils import category_autocomplete, project_autocomplete, tag_autocomplete


def get_option(options: dict, key: str, default=None):
    """
    Helper to safely get an option from parsed args.
    Returns the value if exists, otherwise returns default.
    """
    return options.get(key, default)
# ─── Core Task Options ───────────────────────────────────────────────────────────


category_option = typer.Option(
    None,
    "-c", "--cat",
    help="Task category (e.g., work, rest, personal_projects, social_events). Organizes tasks into meaningful groups.",
    autocompletion=category_autocomplete,
    show_choices=True,
    show_default=False,
)

project_option = typer.Option(
    None,
    "-p", "--pro",
    help="Associated project name (e.g., client_followups, python_app). Useful for grouping related tasks.",
    autocompletion=project_autocomplete,
    show_choices=True,
    show_default=False,
)

due_option = typer.Option(
    None,
    "-d", "--due",
    help="Due date/time for the task. Accepts ISO format (YYYY-MM-DD), natural language (tomorrow, next week), "
          "offsets (1d, 2w, 3m), or specific times today (18:00 for today at 6 PM).",
    show_default=False,
)

impt_option = typer.Option(
    None,
    "-i", "--impt",
    help="Importance level of task from 1 (lowest priority) to 5 (highest priority). Used in the priority calculation to prioritize tasks.",
    show_default=False,
)

recur_option = typer.Option(
    False,
    "-r", "--recur",
    help="Task recurrence schedule (e.g., daily, weekly, monthly, every:7d). Automatically regenerates recurring tasks.",
    show_default=False,
)

# ─── Shared Utilities ───────────────────────────────────────────────────────────

tags_option = typer.Option(
    [],
    help="Tags to quickly filter tasks or entries. Use space-separated format prefixed with '+', e.g., +work +urgent",
    autocompletion=tag_autocomplete,
    show_choices=True,
    show_default=False,
)

notes_option = typer.Option(
    None,
    help="Optional notes or additional context. Must precede any argument starting with a dash (-), "
    "or place after '--' to separate from command options.",
    show_default=False,
)

past_option = typer.Option(
    None,
    "--past",
    help="Backdate the task or entry by a specific offset (e.g., 1h for one hour ago, 2d for two days ago).",
    show_default=False,
)
