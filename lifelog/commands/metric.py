# lifelog/commands/metric.py
import typer
from config.config_manager import load_config, save_config

app = typer.Typer(help="Manage metric definitions.")

@app.command(
    help="""
Add a new metric definition.

Usage:
  llog metric add NAME TYPE [--min N] [--max N] [--description "..."]

Arguments:
  NAME            The name of the metric to track (e.g. mood, energy)
  TYPE            One of: int, float, bool, str

Options:
  --min FLOAT     Minimum allowed value (e.g. 0)
  --max FLOAT     Maximum allowed value (e.g. 10)
  --description   A short description of what this metric represents

Example:
  llog metric add energy int --min 0 --max 10 --description "Energy level from tired to hyper"
"""
)
def add(name: str, type: str, min: float = None, max: float = None, description: str = ""):
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