# lifelog/commands/habit.py
import typer
import json
from pathlib import Path
from datetime import datetime

app = typer.Typer(help="Track recurring habits and completions.")

HABIT_FILE = Path.home() / ".lifelog_habits.json"


def load_habits():
    if HABIT_FILE.exists():
        with open(HABIT_FILE, "r") as f:
            return json.load(f)
    return {"habits": [], "log": []}


def save_habits(data):
    with open(HABIT_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.command()
def add(name: str, description: str = ""):
    """
    Add a new habit to track.
    """
    data = load_habits()
    if name in [h["name"] for h in data["habits"]]:
        typer.echo(f"⚠️  Habit '{name}' already exists.")
        raise typer.Exit()

    data["habits"].append({"name": name, "description": description})
    save_habits(data)
    typer.echo(f"✅ Added habit: {name}")


@app.command()
def done(name: str):
    """
    Mark a habit as done for now.
    """
    data = load_habits()
    if name not in [h["name"] for h in data["habits"]]:
        typer.echo(f"❌ Habit '{name}' not found. Use 'llog habit add' to define it.")
        raise typer.Exit()

    data["log"].append({"name": name, "timestamp": datetime.now().isoformat()})
    save_habits(data)
    typer.echo(f"✅ Logged completion of habit: {name}")


@app.command()
def list():
    """
    List all habits.
    """
    data = load_habits()
    if not data["habits"]:
        typer.echo("No habits defined yet.")
        return

    for h in data["habits"]:
        typer.echo(f"🔁 {h['name']}: {h.get('description', '')}")
