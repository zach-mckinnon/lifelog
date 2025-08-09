import curses
from datetime import datetime, timedelta
from lifelog.utils.db import task_repository
from lifelog.utils.reporting.comprehensive_reports import PersonalAnalytics, create_ascii_chart
from lifelog.ui_views.popups import log_and_popup_error, popup_input, popup_error, popup_show
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr
from lifelog.utils.shared_utils import now_utc

# Minimum terminal characters for good UX
MIN_ROWS = 15
MIN_COLS = 60


def _drop_to_console(func, *args):
    """Execute function in console mode then return to TUI."""
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


def run_comprehensive_summary(stdscr):
    """Run comprehensive analytics summary."""
    from lifelog.commands.report import comprehensive_summary
    _drop_to_console(comprehensive_summary, days=7, verbose=False)


def run_tracker_analysis(stdscr):
    """Run detailed tracker analysis."""
    from lifelog.commands.report import tracker_report
    _drop_to_console(tracker_report, days=7, tracker=None)


def run_time_analysis(stdscr):
    """Run time tracking analysis."""
    from lifelog.commands.report import time_report
    _drop_to_console(time_report, days=7, chart=True)


def run_goals_analysis(stdscr):
    """Run goal progress analysis."""
    from lifelog.commands.report import goals_report
    _drop_to_console(goals_report, tracker_name=None)


def run_insights_analysis(stdscr):
    """Run comprehensive insights analysis."""
    from lifelog.commands.report import comprehensive_insights
    _drop_to_console(comprehensive_insights, days=30)


def show_quick_summary(stdscr):
    """Show quick summary in a popup."""
    try:
        analytics = PersonalAnalytics(fallback_local=True)
        insights = analytics.generate_productivity_insights(7)

        # Build summary text
        lines = ["📊 Weekly Summary (Last 7 Days)", "=" * 35, ""]

        # Tasks
        task_insights = insights.get('task_insights', {})
        if 'error' not in task_insights:
            lines.extend([
                "📋 TASKS:",
                f"  Created: {task_insights.get('recent_tasks', 0)}",
                f"  Completed: {task_insights.get('completed_tasks', 0)}",
                f"  Completion Rate: {task_insights.get('completion_rate', 0)}%",
                f"  Overdue: {task_insights.get('overdue_tasks', 0)}",
                ""
            ])

        # Time
        time_insights = insights.get('time_insights', {})
        if 'error' not in time_insights:
            lines.extend([
                "⏱️ TIME TRACKING:",
                f"  Total: {time_insights.get('total_time_hours', 0):.1f} hours",
                f"  Daily Avg: {time_insights.get('avg_daily_hours', 0):.1f} hours",
                f"  Categories: {time_insights.get('category_count', 0)}",
                ""
            ])

        # Trackers
        tracker_insights = insights.get('tracker_insights', {})
        if 'error' not in tracker_insights:
            lines.extend([
                "📊 TRACKERS:",
                f"  Total Entries: {tracker_insights.get('total_entries', 0)}",
                f"  Active Trackers: {tracker_insights.get('unique_trackers', 0)}",
                f"  Entries/Day: {tracker_insights.get('avg_entries_per_day', 0):.1f}",
                ""
            ])

        # Top recommendation
        recommendations = insights.get('recommendations', [])
        if recommendations:
            lines.extend([
                "💡 TOP RECOMMENDATION:",
                f"  {recommendations[0][:60]}...",
                ""
            ])

        lines.extend([
            "Press Enter to close",
            "Use detailed reports for more insights"
        ])

        popup_show(stdscr, lines, title="📊 Quick Analytics")

    except Exception as e:
        popup_error(stdscr, f"Failed to generate summary: {e}")


def show_tracker_popup(stdscr):
    """Show tracker summary in popup."""
    try:
        analytics = PersonalAnalytics(fallback_local=True)
        insights = analytics.generate_productivity_insights(7)
        tracker_insights = insights.get('tracker_insights', {})

        if 'error' in tracker_insights:
            popup_error(
                stdscr, f"Tracker data error: {tracker_insights['error']}")
            return

        tracker_stats = tracker_insights.get('tracker_stats', {})

        if not tracker_stats:
            popup_error(stdscr, "No tracker data found for the last 7 days")
            return

        lines = ["📊 Tracker Summary (Last 7 Days)", "=" * 35, ""]

        for name, stats in list(tracker_stats.items())[:5]:  # Top 5
            trend_symbol = {"increasing": "↗", "decreasing": "↘",
                            "stable": "→"}.get(stats['trend'], "?")
            consistency = "High" if stats['consistency_score'] > 0.7 else "Med" if stats['consistency_score'] > 0.4 else "Low"

            lines.extend([
                f"📈 {name}:",
                f"  Avg: {stats['avg_value']:.1f} | Trend: {trend_symbol}",
                f"  Entries: {stats['entries']} | Consistency: {consistency}",
                ""
            ])

        popup_show(stdscr, lines, title="📊 Tracker Analysis")

    except Exception as e:
        popup_error(stdscr, f"Failed to analyze trackers: {e}")


def draw_report(pane, h, w):
    """
    Enhanced reports menu with user-friendly options.
    """
    pane.erase()
    max_h, max_w = pane.getmaxyx()
    pane.border()

    # Screen size check
    if max_h < MIN_ROWS or max_w < MIN_COLS:
        msg = f"Screen too small: need ≥{MIN_COLS}×{MIN_ROWS}"
        safe_addstr(pane, max_h//2, max((max_w - len(msg))//2, 0),
                    msg, curses.A_BOLD | curses.A_REVERSE)
        pane.noutrefresh()
        curses.doupdate()
        return

    # Title
    title = " 📊 Personal Analytics "
    safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                title, curses.A_BOLD)

    # Instructions
    safe_addstr(pane, 2, 2, "Choose an analysis option:", curses.A_UNDERLINE)

    # Menu options with descriptions
    options = [
        ("1", "📊 Quick Summary", "7-day productivity overview"),
        ("2", "📈 Comprehensive Report", "Detailed analytics with insights"),
        ("3", "📊 Tracker Analysis", "Individual tracker trends & patterns"),
        ("4", "⏱️ Time Analysis", "Time tracking breakdown & charts"),
        ("5", "🎯 Goal Progress", "Goal achievement status"),
        ("6", "🧠 Deep Insights", "Correlations & recommendations"),
        ("", "", ""),
        ("Q", "🔙 Quick Popups", ""),
        ("W", "📊 Tracker Popup", "Quick tracker overview"),
    ]

    y = 4
    for key, title_text, desc in options:
        if not key:  # Empty line
            y += 1
            continue

        if key in "QW":  # Quick options
            color = curses.A_DIM
        else:
            color = curses.A_NORMAL

        # Key
        safe_addstr(pane, y, 4, f"[{key}]", curses.A_BOLD | color)

        # Title
        safe_addstr(pane, y, 8, title_text, color)

        # Description
        if desc and max_w > 50:
            safe_addstr(pane, y, 30, f"- {desc}", curses.A_DIM)

        y += 1

    # Footer instructions
    footer_y = max_h - 3
    safe_addstr(pane, footer_y, 2,
                "Press number key to run report | Q/W for quick views | ESC to exit",
                curses.A_DIM)

    # Data freshness indicator
    try:
        analytics = PersonalAnalytics(fallback_local=True)
        insights = analytics.generate_productivity_insights(1)  # Just today

        # Show basic stats
        task_insights = insights.get('task_insights', {})
        tracker_insights = insights.get('tracker_insights', {})

        if 'error' not in task_insights and 'error' not in tracker_insights:
            stats_line = f"Today: {task_insights.get('recent_tasks', 0)} tasks, {tracker_insights.get('total_entries', 0)} tracker entries"
            if len(stats_line) < max_w - 4:
                safe_addstr(pane, footer_y - 1, 2, stats_line, curses.A_DIM)
    except:
        pass  # Don't show stats if there's an error
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
    now = now_utc()
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
