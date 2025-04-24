#!/usr/bin/env llog-python
# lifelog/llog.py
import typer
from commands import log, summary, time, habit, metric


app = typer.Typer(help="Lifelog CLI: Track your habits, health, time, and tasks.")

# Add subcommands
app.add_typer(log.app, name="log", help="Log individual metric like mood, sleep, water, etc.")
app.add_typer(metric.app, name="metric", help="Manage and list defined metric.")
app.add_typer(summary.app, name="summary", help="Generate CLI-based reports and visualizations.")
app.add_typer(time.app, name="time", help="Track time in categories like resting, working, socializing.")
app.add_typer(habit.app, name="habit", help="Track recurring habits and completions.")

@app.command("help")
def help_command():
    """
    Show a categorized list of available commands.
    """
    typer.echo("\n🧠 Lifelog CLI - Available Commands\n")
    typer.echo("🔹 Metric Tracking")
    typer.echo("  llog metric add <name> --type <int|float|bool|str> [--min N] [--max N] --description \"...\"  Add a metric")
    typer.echo("  llog metric list                                             List all defined metric\n")

    typer.echo("🔹 Metric Logging")
    typer.echo("  llog log metric <name> <value> [--notes \"...\"] [--tags tag1 tag2]     Log a single metric\n")
    
    typer.echo("🔹 Low-Effort Logging")
    typer.echo("  llog entry <alias or name> <value> [\"optional notes\"] [+tags...]")
    typer.echo("  llog quick                        Run a prompt-based mood + sleep logger\n")

    typer.echo("🔹 Time Tracking")
    typer.echo("  llog time start <category>          Start timing a category")
    typer.echo("  llog time stop                      Stop current timing and save it")
    typer.echo("  llog time status                    Show active timer\n")

    typer.echo("🔹 Habit Tracking")
    typer.echo("  llog habit add <name> [--description \"...\"]     Add a new habit")
    typer.echo("  llog habit done <name>              Mark a habit as completed")
    typer.echo("  llog habit list                     List all habits\n")

    typer.echo("🔹 Reports")
    typer.echo("  llog summary metric <name> [--period day|week|month]         View a metric trend chart")
    typer.echo("  llog summary time [--period day|week|month]                  View time spent per category")
    typer.echo("  llog summary habits [--period day|week|month]                View habit completions by habit")
    typer.echo("  llog summary daily                                           View a full daily recap\n")

    typer.echo("(More categories like 'form' and 'task' coming soon!)\n")
    typer.echo("ℹ️  You can also run any command with --help for details. Example: `llog log --help`\n")

if __name__ == "__main__":
    app()
