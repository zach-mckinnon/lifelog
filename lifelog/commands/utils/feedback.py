import json
from pathlib import Path
import random

FEEDBACK_FILE = Path.home() / ".lifelog" / "feedback_sayings.json"

def load_feedback_sayings():
    """Loads the feedback sayings from the JSON file."""
    if FEEDBACK_FILE.exists():
        try:
            with open(FEEDBACK_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[yellow]⚠️ Warning[/yellow]: Could not decode feedback sayings.")
    return {}

def get_feedback_saying(context):
    """Retrieves a random feedback saying for a given context."""
    sayings = load_feedback_sayings()
    if context in sayings and sayings[context]:
        return random.choice(sayings[context])
    return None

# Example of how to create the JSON file (you'd do this manually)
if __name__ == "__main__":
    default_sayings = {
        "task_added": ["Got it!", "New task added."],
        "task_completed": ["Well done!", "Task completed successfully."],
        # ... add other contexts
    }
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(default_sayings, f, indent=2)
    print(f"Created default feedback sayings file at: {FEEDBACK_FILE}")