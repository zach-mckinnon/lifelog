# lifelog/commands/log.py
import typer
from datetime import datetime
from pathlib import Path
import json
from config.config_manager import get_metric_definition


app = typer.Typer(help="Log a single metric (e.g. mood, water, sleep, etc.)")

LOG_FILE = Path.home() / ".lifelog.json"

@app.command("entry")
def log_entry(
    name: str,
    value: str,
    extras: list[str] = typer.Argument(None)
):
    """
    Natural CLI logging: `llog mood 5 "Tired from work" +foggy`
    """
    from config.config_manager import get_alias_map

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

@app.command()
def quick():
    """
    Prompt-based logging for low-energy check-ins.
    """
    mood = typer.prompt("Mood (1-10)", default="")
    sleep = typer.prompt("Sleep Hours", default="")
    notes = typer.prompt("Notes (optional)", default="")

    entries = []
    if mood:
        entries.append({"name": "mood", "value": mood})
    if sleep:
        entries.append({"name": "sleep", "value": sleep})

    for e in entries:
        try:
            validated = validate_metric(e["name"], e["value"])
            save_entry({
                "timestamp": datetime.now().isoformat(),
                "metric": e["name"],
                "value": validated,
                "notes": notes,
                "tags": []
            })
            typer.echo(f"✅ Logged {e['name']} = {validated}")
        except Exception as err:
            typer.echo(f"❌ {e['name']} failed: {err}")


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

@app.command()
def metric(name: str, value: str, notes: str = "", tags: list[str] = typer.Option([])):
    """
    Log a single metric entry with optional notes and tags.
    """
    validated_value = validate_metric(name, value)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "metric": name,
        "value": validated_value,
        "notes": notes,
        "tags": tags
    }
    save_entry(entry)
    typer.echo(f"✅ Logged {name} = {value}")
