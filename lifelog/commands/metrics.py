# lifelog/commands/metric.py
import typer
from config.config_manager import load_config, save_config

app = typer.Typer(help="Manage metric definitions.")

@app.command()
def add(name: str, type: str, min: float = None, max: float = None, description: str = ""):
    """
    Add a new metric definition.
    """
    config = load_config()

    if "metrics" not in config:
        config["metrics"] = {}

    if name in config["metrics"]:
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

    config["metrics"][name] = metric_def
    save_config(config)
    typer.echo(f"✅ Added metric '{name}' with type '{type}'")

@app.command("list")
def list_metrics():
    """
    List all defined metrics.
    """
    config = load_config()
    metrics = config.get("metrics", {})

    if not metrics:
        typer.echo("No metrics defined yet. Use `llog metric add` to define one.")
        return

    for name, props in metrics.items():
        typer.echo(f"📊 {name} ({props.get('type')})")
        if "min" in props or "max" in props:
            typer.echo(f"    Range: {props.get('min', '-∞')} to {props.get('max', '∞')}")
        if "description" in props:
            typer.echo(f"    {props['description']}")