# lifelog/ui.py

import curses

from lifelog.commands.utils.db import task_repository, time_repository, track_repository
from lifelog.ui_views.ui_helpers import (
    draw_env,
    draw_menu,
    draw_status,
)
from lifelog.ui_views.popups import popup_confirm, show_help_popup
from lifelog.ui_views.reports_ui import draw_report
from lifelog.ui_views.tasks_ui import add_task_tui, clone_task_tui, cycle_task_filter, delete_task_tui, done_task_tui, draw_agenda, edit_notes_tui, edit_recurrence_tui, edit_task_tui, focus_mode_tui, quick_add_task_tui, set_task_reminder_tui, start_task_tui, stop_task_tui, view_task_tui
from lifelog.ui_views.time_ui import add_manual_time_entry_tui, delete_time_entry_tui, draw_time, edit_time_entry_tui, set_time_period, start_time_tui, status_time_tui, stop_time_tui, stopwatch_tui, summary_time_tui, view_time_entry_tui
from lifelog.ui_views.trackers_ui import add_goal_tui, add_tracker_tui, delete_goal_tui, delete_tracker_tui, draw_trackers, edit_goal_tui, edit_tracker_tui, log_entry_tui, show_goals_help_tui, view_goals_list_tui, view_tracker_tui


SCREENS = ["Home", "Task", "Time", "Track", "Report"]


def main(stdscr, show_status: bool = True):
    # ─── Color & Cursor Setup ──────────────────────────────────────────────
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)    # menu bar
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)    # selection
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)   # status bar
    curses.curs_set(0)
    stdscr.keypad(True)

    # ─── State ──────────────────────────────────────────────────────────────
    current = 0   # which tab
    agenda_sel = 0   # selected row in Agenda
    tracker_sel = 0   # selected row in Trackers
    time_sel = 0   # selected row in Time

    # ─── Main Loop ──────────────────────────────────────────────────────────
    while True:
        h, w = stdscr.getmaxyx()
        MIN_HEIGHT = 8
        MIN_WIDTH = 20
        if h < MIN_HEIGHT or w < MIN_WIDTH:
            stdscr.addstr(
                0, 0, f"Terminal too small ({w}x{h}).", curses.A_BOLD)
            stdscr.addstr(1, 0, "Resize or lower font size.")
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord('q'), 27):  # quit or ESC
                return
            continue

        # Always draw the top menu
        try:
            draw_menu(stdscr, SCREENS, current, w, color_pair=1)
        except Exception as e:
            stdscr.addstr(0, 0, f"Menu err: {e}")

       # Tab content
        try:
            if SCREENS[current] == "Home":
                draw_home(stdscr, h, w)
            elif SCREENS[current] == "Task":
                agenda_sel = draw_agenda(stdscr, h, w, agenda_sel)
            elif SCREENS[current] == "Time":
                time_sel = draw_time(stdscr, h, w, time_sel)
            elif SCREENS[current] == "Track":
                tracker_sel = draw_trackers(
                    stdscr, h, w, tracker_sel, color_pair=2)
            elif SCREENS[current] == "Report":
                draw_report(stdscr, h, w)
        except Exception as e:
            stdscr.addstr(3, 2, f"Tab err: {e}")

        # Always draw the status/help bar
        if show_status:
            try:
                draw_status(stdscr, h, w, current)
            except Exception as e:
                stdscr.addstr(h-1, 0, f"Status err: {e}")

        stdscr.refresh()

        # THEN read a key
        key = stdscr.getch()

        # Quit or “back to Agenda”
        if key == ord("Q"):            # Shift+Q to quit
            if popup_confirm(stdscr, "❓ Exit the app? (Y/n)"):
                break
            else:
                continue
        if key == 27:                  # ESC = back to Agenda
            current = 0
            continue

        #  ←/→ to switch tabs
        if key == curses.KEY_RIGHT:
            current = (current + 1) % len(SCREENS)
            continue
        if key == curses.KEY_LEFT:
            current = (current - 1) % len(SCREENS)
            continue

        # ─── Agenda-Specific Nav & Commands ─────────────────────────────────
        elif SCREENS[current] == "Agenda":
            max_idx = len(task_repository.query_tasks(
                status=None, show_completed=False, sort="priority")) - 1
            if key == curses.KEY_DOWN:
                agenda_sel = min(agenda_sel + 1, max_idx)
                continue
            if key == curses.KEY_UP:
                agenda_sel = max(agenda_sel - 1, 0)
                continue
            if key == ord("?"):
                show_help_popup(stdscr, current)
                continue
            elif key == ord("a"):
                add_task_tui(stdscr)
            elif key == ord("q"):
                quick_add_task_tui(stdscr)
            elif key == ord("c"):
                clone_task_tui(stdscr, agenda_sel)
            elif key == ord("F"):
                focus_mode_tui(stdscr, agenda_sel)
            elif key == ord("m"):
                set_task_reminder_tui(stdscr, agenda_sel)
            elif key == ord("d"):
                delete_task_tui(stdscr, agenda_sel)
            elif key in (10, 13):
                edit_task_tui(stdscr, agenda_sel)
            elif key == ord("v"):
                view_task_tui(stdscr, agenda_sel)
            elif key == ord("s"):
                start_task_tui(stdscr, agenda_sel)
            elif key == ord("p"):
                stop_task_tui(stdscr)
            elif key == ord("o"):
                done_task_tui(stdscr, agenda_sel)
            elif key == ord("f"):
                cycle_task_filter(stdscr)
            elif key == ord("r"):
                edit_recurrence_tui(stdscr, agenda_sel)
            elif key == ord("n"):
                edit_notes_tui(stdscr, agenda_sel)

        # ─── Time-Specific Nav & Commands ────────────────────────────────────
        elif SCREENS[current] == "Time":
            max_idx = len(time_repository.get_all_time_logs(since=None)) - 1
            if key == curses.KEY_DOWN:
                time_sel = min(time_sel + 1, max_idx)
                continue
            if key == curses.KEY_UP:
                time_sel = max(time_sel - 1, 0)
                continue
            if key == ord("?"):
                show_help_popup(stdscr, current)
                continue
            elif key == ord("s"):
                start_time_tui(stdscr)
            elif key == ord("a"):
                add_manual_time_entry_tui(stdscr)
            elif key == ord("p"):
                stop_time_tui(stdscr)
            elif key == ord("v"):
                status_time_tui(stdscr)
            elif key == ord("t") or key in (10, 13):
                view_time_entry_tui(stdscr, time_sel)
            elif key == ord("y"):
                summary_time_tui(stdscr)
            elif key == ord("e"):
                edit_time_entry_tui(stdscr, time_sel)
            elif key == ord("x"):
                delete_time_entry_tui(stdscr, time_sel)
            elif key == ord("w"):
                stopwatch_tui(stdscr)
            elif key == ord("W"):
                set_time_period('week')
            elif key == ord("D"):
                set_time_period('day')
            elif key == ord("M"):
                set_time_period('month')
            elif key == ord("A"):
                set_time_period('all')

        elif SCREENS[current] == "Trackers":
            max_idx = len(track_repository.get_all_trackers()) - 1
            if key == curses.KEY_DOWN:
                tracker_sel = min(tracker_sel + 1, max_idx)
                continue
            if key == curses.KEY_UP:
                tracker_sel = max(tracker_sel - 1, 0)
                continue
            if key == ord("?"):
                show_help_popup(stdscr, current)
                continue
            elif key == ord("a"):
                add_tracker_tui(stdscr)
            elif key == ord("d"):
                delete_tracker_tui(stdscr, tracker_sel)
            elif key in (10, 13):
                edit_tracker_tui(stdscr, tracker_sel)
            elif key == ord("l"):
                log_entry_tui(stdscr, tracker_sel)
            elif key == ord("v"):
                view_tracker_tui(stdscr, tracker_sel)
            elif key == ord("g"):
                add_goal_tui(stdscr, tracker_sel)
            elif key == ord("e"):
                edit_goal_tui(stdscr, tracker_sel)
            elif key == ord("x"):
                delete_goal_tui(stdscr, tracker_sel)
            elif key == ord("V"):  # View goals list for tracker
                view_goals_list_tui(stdscr, tracker_sel)
            elif key == ord("h"):  # Show goal types help
                show_goals_help_tui(stdscr)

        elif SCREENS[current] == "Report":
            if key == ord("?"):
                show_help_popup(stdscr, current)
                continue
            if key == ord("1"):
                from ui_views.ui_helpers import run_summary_trackers
                run_summary_trackers(stdscr)
            elif key == ord("2"):
                from ui_views.ui_helpers import run_summary_time
                run_summary_time(stdscr)
            elif key == ord("3"):
                from ui_views.ui_helpers import run_daily_tracker
                run_daily_tracker(stdscr)
            elif key == ord("4"):   # ← new bindings for insights
                from ui_views.ui_helpers import run_insights
                run_insights(stdscr)

            elif key in (ord("q"), 27):
                current = 0
    # end while


def draw_home(stdscr, h, w):
    try:
        stdscr.addstr(1, 2, "🏠 Lifelog Home", curses.A_BOLD)
        stdscr.addstr(3, 2, "Top Tasks:", curses.A_UNDERLINE)
        tasks = task_repository.query_tasks(sort="priority")[:3]
        for i, t in enumerate(tasks):
            stdscr.addstr(4+i, 4, f"{t['title'][:w-8]}")
        stdscr.addstr(8, 2, "Time:", curses.A_UNDERLINE)
        active = time_repository.get_active_time_entry()
        if active:
            stdscr.addstr(9, 4, f"▶ {active['title'][:w-10]}")
        else:
            # Show last time entry if no active
            logs = time_repository.get_all_time_logs()
            if logs:
                last = logs[-1]
                stdscr.addstr(
                    9, 4, f"Last: {last['title'][:w-10]} ({int(last.get('duration_minutes', 0))} min)")
        stdscr.addstr(12, 2, "Recent Trackers:", curses.A_UNDERLINE)
        trackers = track_repository.get_all_trackers()[-2:]
        for i, t in enumerate(trackers):
            stdscr.addstr(13+i, 4, f"{t['title'][:w-8]}")
    except Exception as e:
        stdscr.addstr(h-2, 2, f"Err: {e}", curses.A_BOLD)
