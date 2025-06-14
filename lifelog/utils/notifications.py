# lifelog/utils/notifications.py
import curses
from rich.console import Console
from lifelog.ui_views.popups import popup_show

console = Console()


def notify_cli(message: str):
    console.print(f"[bold magenta]🔔 {message}[/]")


def notify_tui(stdscr, lines: list[str], title: str = "🔔 Notification"):
    popup_show(stdscr, lines, title=title)
