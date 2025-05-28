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


def draw_report(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(1, 2, "📊 Reports", curses.A_BOLD)

    # ← added "4) insights" here
    opts = [
        "1) summary-trackers",
        "2) summary-time",
        "3) daily-tracker",
        "4) insights",
        "q) Back",
    ]
    for i, o in enumerate(opts, start=3):
        pane.addstr(i, 4, o)
    pane.addstr(body_h - 2, 2,
                "Press key to run report → output to console.", curses.A_DIM)
    pane.refresh()
