# 🧠 CLI Input Types Reference for Lifelog

This guide provides a quick reference for **different types of command-line input methods** you can use in your Python CLI apps (like Lifelog) to make logging and interaction easier, faster, and more accessible.

---

## 🧾 1. Standard Command Line Arguments

```bash
llog mood 5 --notes "tired" +foggy
```

Use `typer` or `argparse` to define these.

```python
@app.command()
def mood(value: int, notes: str = ""):
    pass
```

---

## 🧠 2. Prompted Input (typer.prompt)

```bash
llog quick
# > Mood?
# > Sleep hours?
# > Notes?
```

```python
value = typer.prompt("What was your mood today? (1-10)")
```

---

## 🔘 3. Yes/No Confirm Prompts

```python
if typer.confirm("Did you complete your morning routine?"):
    log_habit("morning_routine")
```

---

## 📋 4. Choice Lists

```python
choice = typer.prompt("Choose an energy level", type=typer.Choice(["low", "medium", "high"]))
```

---

## 🧾 5. Repeated Prompts (Form Style)

```python
mood = typer.prompt("Mood (1-10)?")
sleep = typer.prompt("Sleep hours?")
notes = typer.prompt("Notes (optional)?")
```

Use this in `llog quick` or `llog reflect` flows.

---

## 🧮 6. Default Values

```python
mood = typer.prompt("Mood (1-10)?", default="5")
```

---

## 🧩 7. Interactive Forms (External Libs)

Use libraries like:

- `questionary`
- `InquirerPy`

Example with `questionary`:

```python
import questionary
level = questionary.select("Pick your focus level:", choices=["Low", "Medium", "High"]).ask()
```

---

## 🧼 Tips

- Keep prompts minimal (3–5 at most per flow)
- Use defaults and skip logic for burnout safety
- Structure prompts like a friendly conversation
- Validate input (numeric range, etc.)

---

## ✨ Use Cases by Type

| Use Case       | Input Type       |
| -------------- | ---------------- |
| Quick mood log | `typer.prompt()` |
| Time start     | CLI arg          |
| Habit done?    | Confirm prompt   |
| Energy level   | Choice list      |
| Med tracking   | Prompt + Confirm |
| Morning form   | Repeated prompts |
