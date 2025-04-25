# lifelog/commands/metric.py
from logging import config
from typing import List, Optional
import typer
from datetime import datetime
from pathlib import Path
import json
from lifelog.commands.utils.tracker_utils import sum_entries
from lifelog.config.config_manager import get_tracker_definition, load_cron_config, save_config
import lifelog.config.config_manager as cf
from lifelog.commands.utils.shared_options import tags_option, new_name_option, notes_option, min_option, max_option, description_option, unit_option, goal_option,period_option, kind_option
from lifelog.config.config_manager import get_alias_map
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Add or Log a single metric (e.g. mood, water, sleep, etc.)")
console = Console()
LOG_FILE = cf.get_log_file()

@app.command(
        help="Add a new metric definition."
    )
def add(
        name: str = typer.Argument(..., help="The name of the metric."),
        type: str = typer.Argument(..., help="The data type (int, float, bool, str)."),
        min: float = min_option,
        max: float = max_option,
        description: str = description_option,
        unit: Optional[str] = unit_option,        
        goal: Optional[float] = goal_option,
        period: str = period_option,
        kind: str = kind_option
    ):
    """
    Add a new metric definition.
    """
    cfg = cf.load_cron_config()
    tracker = cfg.setdefault("tracker", {})

    if name in cfg.get("tracker", {}):
        typer.echo(f"Metric '{name}' already exists. Use a different name or edit manually.")
        raise typer.Exit(code=1)
    
    valid_types = ["int", "float", "bool", "str"]
    if type not in valid_types:
        typer.echo(f"Invalid type: '{type}'. Type must be one of these types: {', '.join(valid_types)}.")
        raise typer.Exit(code=1)
        # normalize count-kind defaults
    if kind not in ("sum","count"):
        typer.echo("⚠️  --kind must be 'sum' or 'count'")
        raise typer.Exit(code=1)
    
    if kind not in ("sum", "count"):
        # emit exactly what pytest is looking for, no extra emoji or spaces:
        typer.echo("--kind must be 'sum' or 'count'")
    if kind == "count" and goal is None:
        goal = 1
        raise typer.Exit(code=1)
    
    # build your definition
    metric_def = {
        "type": type,
        "description": description,
        "goals": [
            {
              "type":   kind,
              "target": goal,
              "period": period,
              **({"unit": unit} if unit and kind=="sum" else {})
            }
        ]
    }
    
    if min is not None:
        metric_def["min"] = min
    if max is not None:
        metric_def["max"] = max

    tracker[name] = metric_def
    cf.save_config(config)
    typer.echo(f"✅ Added metric '{name}' with type '{type}'")

@app.command("list")
def list_tracker():
    """
    Show all trackers and their settings.
    """
    config =load_cron_config().get("tracker", {})
    if not config:
        typer.echo("No trackers defined. Try `llog track add`.")
        return

    table = table(title="📝 Your Trackers", show_lines=True)
    for col in ["Name","Type","Unit","Goal","Period","Description"]:
        table.add_column(col, no_wrap=True)
    for name, t in config.items():
        table.add_row(
            name,
            t.get("type",""),
            t.get("unit","-"),
            str(t.get("goal","-")),
            t.get("period","-"),
            t.get("description",""),
        )
    Console().print(table)

@app.callback(invoke_without_command=True)
def track(
    ctx: typer.Context,
    name: str = typer.Argument(None, help="Tracker name (e.g. mood, water)"),
    value: str = typer.Argument(None, help="Value to log for this tracker"),
    extras: list[str] = typer.Argument(None),
    tags: List[str] = tags_option,
    notes: Optional[str] = notes_option
):
    """
    Natural CLI logging: `llog track mood 5 "Tired" +tag`
    """
    
    if name is None or value is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=1)
    
    aliases = get_alias_map()
    name = aliases.get(name, name)

    notes = ""
    tags = []

    for item in extras or []:
        if item.startswith("+"):
            tags.append(item.lstrip("+"))
        else:
            notes += item + " "

    validated_value = validate_metric(name, value)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "metric": name,
        "value": validated_value,
        "notes": notes.strip(),
        "tags": tags
    }
    save_entry(entry)
    
    cfg = get_tracker_definition(name) or {}
    
    if any(g["type"] for g in cfg.get("goals", [])):
        total_today = sum_entries(name, since="today")
        typer.echo(f"✅ Logged {name} = {validated_value} {config.get('unit','')}"
                f" ({total_today}/{config['goal']} {config.get('unit','')} today)")
    else:
        typer.echo(f"✅ Logged {name} = {validated_value}")


@app.command("modify")
def modify(
    name: str = typer.Argument(..., help="Tracker to change"),
    new_name: Optional[str] = new_name_option,
    unit: Optional[str]     = unit_option,
    goal: Optional[float]   = goal_option,
    period: Optional[str]   = period_option,
    min: Optional[float]    = min_option,
    max: Optional[float]    = max_option,
    description: Optional[str] = description_option,
):
    """
    Update an existing tracker definition.
    """
    config =load_cron_config().setdefault("tracker", {})
    if name not in config:
        typer.echo(f"❌ No tracker named '{name}'")
        raise typer.Exit(code=1)

    t = config[name]
    # handle rename
    if new_name:
        config[new_name] = t
        del config[name]
        name = new_name

    # apply any provided options
    for field, val in [
        ("unit", unit), ("goal", goal), ("period", period),
        ("min", min),   ("max", max),  ("description", description)
    ]:
        if val is not None:
            t[field] = val

    save_config({"tracker": config})
    typer.echo(f"✅ Updated tracker '{name}'")

@app.command("done")
def done(
        name: str = typer.Argument(..., help="Tracker habit to mark 'done' and tally."),
        tags: List[str] = tags_option,
        notes: Optional[str] = notes_option
    ):
    """
    Mark a habit as done for now.
    """
    track(name, "1", [], tags, notes)


def save_entry(entry):
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    data.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def validate_metric(name: str, value: str):
    definition = get_tracker_definition(name)
    if not definition:
        raise typer.BadParameter(f"Metric '{name}' is not defined in the config.")

    expected_type = definition.get("type")
    min_val = definition.get("min")
    max_val = definition.get("max")

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
        raise typer.BadParameter(f"Value '{value}' is not a valid {expected_type}.")

    if isinstance(value, (int, float)):
        if min_val is not None and value < min_val:
            raise typer.BadParameter(f"Value is below the minimum allowed ({min_val}).")
        if max_val is not None and value > max_val:
            raise typer.BadParameter(f"Value is above the maximum allowed ({max_val}).")

    return value
