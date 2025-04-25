# lifelog/commands/metric.py
from typing import List, Optional
import typer
from datetime import datetime
from pathlib import Path
import json
from lifelog.config.config_manager import get_metric_definition, load_config, save_config
from lifelog.config.config_manager import get_log_file
from lifelog.commands.utils.shared_options import tags_option, notes_option

app = typer.Typer(help="Add or Log a single metric (e.g. mood, water, sleep, etc.)")


LOG_FILE = get_log_file()

@app.command(
        help="Add a new metric definition."
    )
def add(
        name: str = typer.Argument(..., help="The name of the metric."),
        type: str = typer.Argument(..., help="The data type (int, float, bool, str)."),
        min: float = typer.Option(None, "--min", help="Minimum allowed value."),
        max: float = typer.Option(None, "--max", help="Maximum allowed value."),
        description: str = typer.Option("", "--description", "-d", help="Description of the metric.")
    ):
    """
    Add a new metric definition.
    """
    config = load_config()

    if "metric" not in config:
        config["metric"] = {}

    if name in config["metric"]:
        typer.echo(f"Metric '{name}' already exists. Use a different name or edit the config manually.")
        raise typer.Exit()
    
    valid_types = ["int", "float", "bool", "str"]
    if type not in valid_types:
        typer.echo(f"Invalid type: '{type}'. Type must be one of these types: {', '.join(valid_types)}.")
        raise typer.Exit()
    
    metric_def = {
        "type": type,
        "description": description
    }
    if min is not None:
        metric_def["min"] = min
    if max is not None:
        metric_def["max"] = max

    config["metric"][name] = metric_def
    save_config(config)
    typer.echo(f"✅ Added metric '{name}' with type '{type}'")

@app.command("list")
def list_metric():
    """
    List all defined metric.
    """
    config = load_config()
    metric = config.get("metric", {})

    if not metric:
        typer.echo("No metric defined yet. Use `llog metric add` to define one.")
        return

    for name, props in metric.items():
        typer.echo(f"📊 {name} ({props.get('type')})")
        if "min" in props or "max" in props:
            typer.echo(f"    Range: {props.get('min', '-∞')} to {props.get('max', '∞')}")
        if "description" in props:
            typer.echo(f"    {props['description']}")


@app.command("entry")
def entry(
    name: str,
    value: str,
    extras: list[str] = typer.Argument(None),
    tags: List[str] = tags_option,
    notes: Optional[str] = notes_option
):
    """
    Natural CLI logging: `llog mood 5 "Tired from work" +foggy`
    """
    from lifelog.config.config_manager import get_alias_map

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
    typer.echo(f"✅ Logged {name} = {validated_value}")


@app.command("checkin")
@app.command("quick")
def quick_checkin():
    """
    Prompt-based log form for daily metrics.
    """
    mood = typer.prompt("Mood (1-10)?")
    notes = typer.prompt("Any notes?", default="")
    energy = typer.prompt("Energy Level (1-10)?")
    entry("mood", mood, [notes] if notes else [])
    entry("energy", energy)
    typer.echo("✅ Check-in logged.")


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
    definition = get_metric_definition(name)
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
