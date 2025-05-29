# reports_ui.py

import curses
from lifelog.commands.report import daily_tracker, get_ai_credentials, show_clinical_insights, show_insights, summary_time, summary_trackers
from lifelog.ui_views.popups import log_and_popup_error, popup_input, popup_error
from ui_views.ui_helpers import log_exception


def _drop_to_console(func, *args):
    """
    Exit curses, run a blocking func(*args) that prints via Rich,
    then pause for Enter before returning into curses.
    """
    curses.endwin()
    try:
        func(*args)
    except Exception as e:
        print(f"\n[red]Error running report: {e}[/]")
    input("\nPress Enter to return to the TUI…")


def run_summary_trackers(stdscr):
    _drop_to_console(summary_trackers)


def run_summary_time(stdscr):
    _drop_to_console(summary_time)


def run_daily_tracker(stdscr):
    metric = popup_input(stdscr, "Metric name for daily tracker:")
    if not metric:
        popup_error(stdscr, "Metric name required for daily tracker.")
        return
    _drop_to_console(daily_tracker, metric)


def run_insights(stdscr):
    _drop_to_console(show_insights)


def run_clinical_insights(stdscr):
    try:
        show_clinical_insights(stdscr=stdscr)
    except Exception as e:
        log_and_popup_error(stdscr, "Error in UI clinical insights", e)


def draw_report(pane, h, w):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Reports "
        pane.addstr(0, max((max_w - len(title)) // 2, 1), title, curses.A_BOLD)
        y = 2
        lines = [
            "1. Tracker Summary   - Overview of all trackers",
            "2. Time Summary      - Overview of all time logs",
            "3. Daily Tracker     - Detail for a single metric",
            "4. Insights          - AI-driven insights",
            "5. Clinical Insights - Clinical/Behavioral patterns (NEW)",
            "",
            "Use 1-5 to select. ESC/q to return."
        ]
        for i, line in enumerate(lines):
            if y + i < max_h - 1:
                pane.addstr(y + i, 2, line[:max_w-4])
        pane.noutrefresh()
    except Exception as e:
        pane.addstr(h-2, 2, f"Report err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        log_exception("draw_report", e)
