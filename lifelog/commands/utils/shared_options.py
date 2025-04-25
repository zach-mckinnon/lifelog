# lifelog/commands/utils/shared_options.py
from typing import List, Optional
import typer

tags_option = typer.Option(
    default=[],
    help="List of tags (e.g. +food +work). Use space-separated tags prefixed with +.",
    show_default=False
)

notes_option = typer.Option(
    default=None,
    help="Optional notes about this entry.",
    show_default=False
)

past_option = typer.Option(
    default=None,
    help="Optional time offset for backdating (e.g. --past -1h or -30m).",
    show_default=False
)
