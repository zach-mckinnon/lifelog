# lifelog/utils/report_utils.py
''' 
Lifelog CLI - Reporting Utilities Module
This module provides functionality to render various types of charts and visualizations in the command line interface (CLI).
It includes functions to render line charts, scatter plots, calendar heatmaps, radar charts, and pie charts using the Rich and Termplotlib libraries.
It is designed to enhance the user experience by providing visual representations of data directly in the terminal.
'''

import termplotlib as tpl
from collections import defaultdict
from datetime import datetime
import numpy as np
from rich.console import Console
from rich.text import Text

console = Console()


def render_line_chart(dates, values, label=""):
    """Renders a line chart using termplotlib with enhanced styling."""
    fig = tpl.figure()
    fig.plot(
        list(range(len(values))),
        values,
        xlabel=Text("Day", style="italic"),
        ylabel=Text(label, style="italic"),
        xticks=[(i, Text(d[-5:], style="bold")) for i, d in enumerate(dates)],
        width=console.width - 10,  # Adjust width for console
        height=15
    )
    console.print(fig.get_string())


def render_scatter_plot(x, y, xlabel="", ylabel=""):
    """Renders a scatter plot using termplotlib with enhanced styling."""
    fig = tpl.figure()
    fig.scatter(
        x,
        y,
        xlabel=Text(xlabel, style="italic"),
        ylabel=Text(ylabel, style="italic"),
        width=console.width - 10,  # Adjust width for console
        height=15
    )
    console.print(fig.get_string())


def render_calendar_heatmap(date_to_value):
    """Renders a basic calendar-like heatmap in the CLI."""
    day_values = defaultdict(float)
    for date_str, val in date_to_value.items():
        day = datetime.fromisoformat(date_str).strftime("%a")
        day_values[day] += val

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    max_val = max(day_values.values(), default=1)

    console.print("\n[bold blue]Calendar Heatmap:[/bold blue]")
    for day in days:
        value = day_values[day]
        normalized_value = value / max_val if max_val > 0 else 0
        bar_length = int(normalized_value * 20)
        bar = "[green]█[/green]" * bar_length
        console.print(
            f"[bold]{day}:[/bold] {bar} [italic]{round(value, 1)}[/italic]")


def render_radar_chart(metric_scores):
    """Placeholder for radar chart rendering (CLI limitation)."""
    console.print("\n[bold blue]Radar Summary:[/bold blue]")
    for k, v in metric_scores.items():
        console.print(f"- [bold cyan]{k}:[/bold cyan] [green]{v}[/green]")


def render_pie_chart(category_totals):
    """Renders a basic pie chart in the CLI using block characters."""
    total = sum(category_totals.values())
    console.print("\n[bold blue]Life Balance Pie Chart:[/bold blue]")
    for cat, val in category_totals.items():
        percent = (val / total) * 100 if total else 0
        bar_length = int(percent / 4)
        bar = "[yellow]■[/yellow]" * bar_length
        console.print(
            f"[bold]{cat:10}:[/bold] {bar} ([cyan]{round(percent)}%[/cyan])")


def correlation_score(x, y):
    """Calculates the Pearson correlation coefficient between two lists."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    try:
        corr = np.corrcoef(x, y)[0, 1]
        return round(corr, 2)
    except Exception as e:
        console.print(
            f"[bold red]Error calculating correlation:[/bold red] {e}")
        return 0.0
