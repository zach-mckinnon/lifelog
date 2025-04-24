#!/usr/bin/env python3
# lifelog/llog.py
import typer
from commands import log, summary, metrics

app = typer.Typer(help="Lifelog CLI: Track your habits, health, time, and tasks.")

# Add subcommands
app.add_typer(log.app, name="log", help="Log individual metrics like mood, sleep, water, etc.")
app.add_typer(metrics.app, name="metrics", help="Manage and list defined metrics.")
app.add_typer(summary.app, name="summary", help="Generate CLI-based reports and visualizations.")

@app.command("help")
def help_command():
    """
    Show a categorized list of available commands.
    """
    typer.echo("\n🧠 Lifelog CLI - Available Commands\n")
    typer.echo("🔹 Metric Tracking")
    typer.echo("  llog metrics add <name> --type <int|float|bool|str> [--min N] [--max N] --description \"...\"  Add a metric")
    typer.echo("  llog metrics list                                             List all defined metrics\n")

    typer.echo("🔹 Logging")
    typer.echo("  llog log metric <name> <value> [--notes \"...\"] [--tags tag1 tag2]     Log a single metric\n")

    typer.echo("🔹 Reports")
    typer.echo("  llog summary metric <name> [--period day|week|month]         View a metric trend chart\n")

    typer.echo("(More categories like 'form', 'task', and 'habit' coming soon!)\n")
    typer.echo("ℹ️  You can also run any command with --help for details. Example: `llog log --help`\n")

if __name__ == "__main__":
    app()