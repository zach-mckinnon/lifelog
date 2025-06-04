# reports_ui.py

import curses
from datetime import datetime, timedelta
from lifelog.utils.db import task_repository
from lifelog.commands.report import daily_tracker, show_clinical_insights, show_insights, summary_time, summary_trackers
from lifelog.ui_views.popups import log_and_popup_error, popup_input, popup_error
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr


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
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)
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
                safe_addstr(pane, y + i, 2, line[:max_w-4])
        pane.noutrefresh()
    except Exception as e:
        safe_addstr(pane, h-2, 2, f"Report err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        log_exception("draw_report", e)


def draw_burndown(pane, h, w):
    try:
        pane.erase()
        pane.border()
        title = " Task Burndown "
        safe_addstr(pane, 0, max((w - len(title)) // 2, 1),
                    title, curses.A_BOLD)

        tasks = task_repository.get_all_tasks()
        now = datetime.now()
        start_date = now - timedelta(days=2)
        end_date = now + timedelta(days=3)

        all_dates = []
        date_labels = []
        current_date = start_date
        while current_date <= end_date:
            all_dates.append(current_date)
            date_labels.append(current_date.strftime("%m/%d"))
            current_date += timedelta(days=1)

        not_done_counts = []
        overdue_counts = []
        for d in all_dates:
            not_done = 0
            overdue = 0
            for task in tasks:
                if task and task.get("status") != "done":
                    due_str = task.get("due")
                    if due_str:
                        try:
                            due_date = datetime.fromisoformat(due_str)
                            if due_date.date() <= d.date():
                                not_done += 1
                                if due_date.date() < now.date() and d.date() >= now.date():
                                    overdue += 1
                        except Exception:
                            continue
            not_done_counts.append(not_done)
            overdue_counts.append(overdue)

        # Y-axis: max outstanding
        max_count = max(not_done_counts + [1])
        chart_height = max(5, min(h-6, max_count + 1))
        left_margin = 4

        # Draw Y-axis
        for i in range(chart_height):
            y = 2 + i
            val = max_count - i
            if y < h - 2:
                safe_addstr(pane, y, left_margin-2, f"{val:2d}|")

        # Draw bars
        for x, (count, overdue) in enumerate(zip(not_done_counts, overdue_counts)):
            bar_height = int((count / max_count) *
                             (chart_height-1)) if max_count > 0 else 0
            for i in range(bar_height):
                y = 2 + chart_height - 1 - i
                if y < h - 2:
                    safe_addstr(pane, y, left_margin + x, "#" if overdue == 0 else "!",
                                curses.A_BOLD if overdue else curses.A_NORMAL)

        # X-axis (dates)
        safe_addstr(pane, 2+chart_height, left_margin, "".join(
            date_labels[i][3:]+" " for i in range(len(date_labels)))[:w-left_margin-1])

        # Stats
        safe_addstr(pane,
                    h-3, left_margin, f"Outstanding: {not_done_counts[-1]}, Overdue: {overdue_counts[-1]}")
        safe_addstr(pane, h-2, left_margin, "Key: # = open, ! = overdue")

        pane.noutrefresh()

    except Exception as e:
        safe_addstr(pane, h-2, 2, f"Burndown err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        log_exception("burndown_tui", e)
