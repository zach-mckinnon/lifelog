#!/usr/bin/env python3
# lifelog/llog.py
import typer
from commands import log, summary

app = typer.Typer(help="Lifelog CLI: Track your habits, health, time, and tasks.")

# Add subcommands
app.add_typer(log.app, name="log")
# app.add_typer(form.app, name="form")
# app.add_typer(habit.app, name="habit")
# app.add_typer(metric.app, name="metric")
# app.add_typer(task.app, name="task")
# app.add_typer(time.app, name="time")
app.add_typer(summary.app, name="summary")

if __name__ == "__main__":
    app()
