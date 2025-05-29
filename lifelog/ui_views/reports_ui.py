# -------------------------------------------------------------------
# Report view: options list
# -------------------------------------------------------------------

import curses

from lifelog.commands.report import daily_tracker, show_insights, summary_time, summary_trackers
from lifelog.ui_views.popups import popup_input

# ─── Helpers to run a CLI report and wait ────────────────────────────────


def _drop_to_console(func, *args):
    """
    Exit curses, run a blocking func(*args) that prints via Rich,
    then pause for Enter before returning into curses.
    """
    curses.endwin()
    try:
        func(*args)
    except Exception as e:
        print(f"[red]Error running report: {e}[/]")
    input("\nPress Enter to return to the TUI…")

# ─── Specific report runners ─────────────────────────────────────────────


def run_summary_trackers(stdscr):
    """Run `llog report summary-trackers`"""
    _drop_to_console(summary_trackers)


def run_summary_time(stdscr):
    """Run `llog report summary-time`"""
    _drop_to_console(summary_time)


def run_daily_tracker(stdscr):
    """
    Prompt for a metric name, then run `llog report daily-tracker <metric>`.
    """
    metric = popup_input(stdscr, "Metric name for daily tracker:")
    if not metric:
        return
    _drop_to_console(daily_tracker, metric)


def run_insights(stdscr):
    """Run `llog report insights`"""
    _drop_to_console(show_insights)


def draw_report(pane, h, w):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Reports "
        pane.addstr(0, max((max_w - len(title)) // 2, 1), title, curses.A_BOLD)
        y = 2
        lines = [
            "1. Tracker Summary",
            "2. Time Summary",
            "3. Daily Tracker",
            "4. Insights",
            "",
            "Use 1-4 to select. ESC/q to return."
        ]
        for i, line in enumerate(lines):
            if y+i < max_h - 1:
                pane.addstr(y+i, 2, line[:max_w-4])
        pane.noutrefresh()
    except Exception as e:
        pane.addstr(h-2, 2, f"Report err: {e}", curses.A_BOLD)
        pane.noutrefresh()
