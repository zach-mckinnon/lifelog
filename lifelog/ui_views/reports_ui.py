import curses
from datetime import datetime, timedelta
from lifelog.utils.db import task_repository
from lifelog.commands.report import (
    daily_tracker,
    show_clinical_insights,
    show_insights,
    summary_time,
    summary_trackers
)
from lifelog.ui_views.popups import log_and_popup_error, popup_input, popup_error
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr

# Minimum terminal characters to approximate 180×180 px (≈8×16 px per char)
MIN_ROWS = 11
MIN_COLS = 22


def _drop_to_console(func, *args):
    try:
        curses.endwin()
    except curses.error:
        pass
    try:
        func(*args)
    except Exception as e:
        print(f"\n[red]Error running report: {e}[/]")
    input("\nPress Enter to return to the TUI…")
    curses.initscr()


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
    """
    Main menu for report selection.
    """
    pane.erase()
    max_h, max_w = pane.getmaxyx()
    pane.border()

    # Screen size check
    if max_h < MIN_ROWS or max_w < MIN_COLS:
        msg = f"Screen too small: need ≥{MIN_COLS}×{MIN_ROWS} chars"
        safe_addstr(pane, max_h//2, max((max_w - len(msg))//2, 0),
                    msg, curses.A_BOLD | curses.A_REVERSE)
        pane.noutrefresh()
        curses.doupdate()
        return

    # Title
    title = " Reports "
    safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                title, curses.A_BOLD)

    # Menu items
    options = [
        "1. Tracker Summary   - Overview of all trackers",
        "2. Time Summary      - Overview of all time logs",
        "3. Daily Tracker     - Detail for a single metric",
        "4. Insights          - AI-driven insights",
        "5. Clinical Insights - Clinical/Behavioral patterns (NEW)",
        "",
        "Use 1-5 to select. ESC/q to return."
    ]
    for idx, line in enumerate(options):
        y = 2 + idx
        if y < max_h - 1:
            safe_addstr(pane, y, 2, line[:max_w-4])

    pane.noutrefresh()
    curses.doupdate()


def draw_burndown(pane, h, w):
    """
    Scaled burndown chart of outstanding vs. overdue tasks
    over a 5-day window.
    """
    pane.erase()
    max_h, max_w = pane.getmaxyx()
    pane.border()

    # Screen size check
    if max_h < MIN_ROWS or max_w < MIN_COLS:
        msg = f"Screen too small for burndown: need ≥{MIN_COLS}×{MIN_ROWS} chars"
        safe_addstr(pane, max_h//2, max((max_w - len(msg))//2, 0),
                    msg, curses.A_BOLD | curses.A_REVERSE)
        pane.noutrefresh()
        curses.doupdate()
        return

    # Title
    title = " Task Burndown "
    safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                title, curses.A_BOLD)

    # Fetch data
    tasks = task_repository.get_all_tasks()
    now = datetime.now()
    start = now - timedelta(days=2)
    end = now + timedelta(days=3)

    # Build date list
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    labels = [d.strftime("%m/%d") for d in dates]

    # Count outstanding & overdue per day
    outstanding, overdue = [], []
    for d in dates:
        not_done = overdue_count = 0
        for t in tasks:
            if t.get("status") != "done":
                due = t.get("due")
                if due:
                    try:
                        dd = datetime.fromisoformat(due)
                        if dd.date() <= d.date():
                            not_done += 1
                            if dd.date() < now.date() and d.date() >= now.date():
                                overdue_count += 1
                    except Exception:
                        pass
        outstanding.append(not_done)
        overdue.append(overdue_count)

    # Determine chart area
    top = 2
    bottom = max_h - 4
    height = bottom - top + 1
    chart_h = max(3, height)
    left = 6
    right = max_w - 2
    chart_w = right - left

    # Y-axis scaling
    max_val = max(outstanding + [1])
    for row in range(chart_h):
        y = top + row
        val = int(max_val * (chart_h - 1 - row) / (chart_h - 1))
        label = f"{val:2d}|"
        safe_addstr(pane, y, left - len(label), label)

    # X-axis positions
    step = chart_w / max(len(dates)-1, 1)

    # Draw bars
    for i, (o, ov) in enumerate(zip(outstanding, overdue)):
        bar_height = int((o / max_val) * (chart_h - 1))
        x = left + int(round(step * i))
        # Draw each segment of bar
        for hgt in range(bar_height):
            y = top + chart_h - 1 - hgt
            char = "!" if ov > 0 else "#"
            attr = curses.A_BOLD if ov > 0 else curses.A_NORMAL
            if 0 < y < max_h-1 and 0 < x < max_w-1:
                safe_addstr(pane, y, x, char, attr)

    # X-axis labels (abbreviated)
    label_row = top + chart_h
    for i, lbl in enumerate(labels):
        x = left + int(round(step * i)) - 1
        if 0 < label_row < max_h-1 and 0 < x < max_w-5:
            safe_addstr(pane, label_row, x,
                        lbl[-2:], curses.A_DIM)

    # Stats footer
    footer = f"Open: {outstanding[-1]}  Overdue: {overdue[-1]}"
    safe_addstr(pane, max_h-2, 2, footer[:max_w-4], curses.A_BOLD)

    pane.noutrefresh()
    curses.doupdate()
