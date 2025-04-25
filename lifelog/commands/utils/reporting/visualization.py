from rich.console import Console
from lifelog.commands.utils.reporting.analytics.report_utils import (
    render_scatter_plot,
    render_calendar_heatmap,
    render_radar_chart,
)

console = Console()


def cli_scatter(x, y, xlabel="", ylabel="", title: str = None):
    """
    Display a scatter plot in CLI, with an optional title.
    """
    if title:
        console.print(f"[bold underline]{title}[/bold underline]")
    render_scatter_plot(x, y, xlabel=xlabel, ylabel=ylabel)


def cli_calendar_heatmap(data: dict, title: str = None):
    """
    Display a calendar heatmap in CLI, with an optional title.
    """
    if title:
        console.print(f"[bold underline]{title}[/bold underline]")
    render_calendar_heatmap(data)


def cli_radar(data: dict, title: str = None):
    """
    Display a radar summary in CLI, with an optional title.
    """
    if title:
        console.print(f"[bold underline]{title}[/bold underline]")
    render_radar_chart(data)
