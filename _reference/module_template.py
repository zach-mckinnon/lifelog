import typer
from datetime import datetime
from pathlib import Path
import json

app = typer.Typer(help="ModuleName: Describe this module's purpose here.")

# Define your data storage path
DATA_FILE = Path.home() / ".lifelog_modulename.json"

# Utility to load and save data
def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_entry(entry):
    data = load_data()
    data.append(entry)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Example command: Add a new log entry
@app.command()
def add(name: str, value: str, notes: str = "", tags: list[str] = typer.Option([])):
    """Add a new entry to the module log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "name": name,
        "value": value,
        "notes": notes,
        "tags": tags
    }
    save_entry(entry)
    typer.echo(f"✅ Logged {name} = {value}")

# Example command: List all entries
@app.command()
def list():
    """List all entries in the module log."""
    data = load_data()
    if not data:
        typer.echo("No entries found.")
        return
    for entry in data:
        typer.echo(f"- [{entry['timestamp']}] {entry['name']} = {entry['value']} | {entry.get('notes', '')}")

# Example command: Summary report
@app.command()
def summary():
    """Show a basic summary of this module's entries."""
    data = load_data()
    typer.echo(f"📊 Total entries: {len(data)}")
