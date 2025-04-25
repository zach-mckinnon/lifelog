# 🧱 Lifelog CLI Module Development Guide

This guide walks you through the full process of **adding, changing, or removing modules and commands** in the Lifelog CLI app.

It follows the project's principles:

- Low friction
- Burnout-safe
- Natural language command style
- Consistent logging and reporting structure

---

## ✅ Adding a New Module

### 1. **Plan the Command Structure**

- Think about how the command will feel when typed:
  ```bash
  llog meds take -add
  llog journal "tired today"
  llog track posture 20min
  ```
- Keep the structure natural and readable
- Review the Usability Framework for tone and consistency

### 2. **Add Module to `llog.py`**

```python
from commands import yourmodule
app.add_typer(yourmodule.app, name="yourname", help="...description...")
```

📌 If you're using aliases that may redirect to this module, update the `@app.callback` logic to route unknown root commands.

### 3. **Create the Module File**

```bash
mkdir -p lifelog/commands
nano lifelog/commands/yourmodule.py
```

```python
import typer
app = typer.Typer(help="Describe this module's purpose")
```

---

## ✍️ Defining Commands in a Module

### 4. **Add CLI Commands**

Use `@app.command()`

```python
@app.command()
def add(name: str, description: str = ""):
    """Add a new thing"""
    # logic
```

Add:

- Help strings to every command
- Default values where possible
- Validation for inputs

---

## 💾 Storing Data

### 5. **Where to Store It**

- Use JSON files in user home directory:

  ```bash
  ~/.lifelog.json
  ~/.lifelog_time_tracking.json
  ~/.lifelog_habits.json
  ~/.config/lifelog/config.toml
  ```

- Use consistent format:

```json
{
  "timestamp": "2025-04-23T23:00:00",
  "category": "rest",
  "value": 5,
  "notes": "tired",
  "tags": ["foggy"]
}
```

Use a `save_entry()` function similar to other modules.

---

## 📊 Fetching Data for Reports

### 6. **Reporting-Compatible Entries**

To make your module's data reportable:

- Save with timestamps
- Keep key fields like `value`, `tags`, `notes`, `category`
- Ensure you can filter by `datetime.fromisoformat(entry["timestamp"])`

In `summary.py`, fetch using:

```python
with open(path) as f:
    entries = json.load(f)
```

Group by date with `defaultdict(list)` and parse timestamps

---

## 🆘 Adding Help Descriptions

### 7. **Document Your Commands**

- Add `help="..."` to every command
- Update the custom `llog help` output in `llog.py`

```python
@app.command("help")
def help_command():
    typer.echo("llog yourmodule action <args> [--options]")
```

---

## 🔄 Updating or Refactoring a Module

- Rename the module and its references in `llog.py`
- Regenerate symlinks if needed (`sudo ln -sf ...`)
- Use `git grep` to find all usages
- Validate config values exist in `.toml`

---

## ❌ Removing a Module

- Remove its import and `add_typer()` from `llog.py`
- Delete the file from `commands/`
- Clean up logs (optional)
- Remove any help entries or fallback routing

---

## 🔚 Final Tips

- Stick to one JSON log file per module unless there's a strong reason
- Keep naming simple and lowercase
- Make logs searchable (timestamp + category + value)
- Be kind to the user with errors and wording
- Use constants for shared keys like `timestamp`, `value`, `tags`

## REFERENCES:

- https://clig.dev/#philosophy
