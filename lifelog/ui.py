# lifelog/ui.py

import curses
import os
import traceback

from lifelog.utils.db import environment_repository
from lifelog.utils.db import task_repository, time_repository, track_repository
from lifelog.ui_views.ui_helpers import (
    draw_menu,
    draw_status,
    safe_addstr,
)
from lifelog.ui_views.popups import popup_confirm, popup_error, show_help_popup
from lifelog.ui_views.reports_ui import draw_report, run_clinical_insights, run_daily_tracker, run_insights, run_summary_time, run_summary_trackers, draw_burndown
from lifelog.ui_views.tasks_ui import add_task_tui, clone_task_tui, cycle_task_filter, delete_task_tui, done_task_tui, draw_agenda,  edit_notes_tui, edit_recurrence_tui, edit_task_tui, focus_mode_tui, quick_add_task_tui, set_task_reminder_tui, start_task_tui, stop_task_tui, view_task_tui
from lifelog.ui_views.time_ui import add_manual_time_entry_tui, delete_time_entry_tui, draw_time, edit_time_entry_tui, set_time_period, start_time_tui, status_time_tui, stop_time_tui, stopwatch_tui, summary_time_tui, view_time_entry_tui
from lifelog.ui_views.trackers_ui import add_or_edit_goal_tui, add_tracker_tui, delete_goal_tui, delete_tracker_tui, draw_trackers, edit_tracker_tui, log_entry_tui, show_goals_help_tui, view_goals_list_tui, view_tracker_tui
import lifelog.config.config_manager as cf
from lifelog.first_time_run import LOGO, show_welcome
from lifelog.utils.shared_utils import log_error

SCREENS = ["H", "TSK", "TM", "TRK", "R"]


def create_main_panes(stdscr, h, w, menu_h):
    """Create and return bordered panes for each tab below the menu."""
    body_h = h - menu_h - 1
    panes = {}
    for idx, screen in enumerate(SCREENS):
        panes[screen] = curses.newwin(body_h, w, menu_h, 0)
        panes[screen].border()
    return panes


def show_tui_welcome(stdscr):
    show_welcome(stdscr)


def main(stdscr, show_status: bool = True):
    # --- Color & Cursor Setup ---
    try:
        config = cf.load_config()
        if not config.get("meta", {}).get("tui_welcome_shown", False):
            show_tui_welcome(stdscr)
            config["meta"]["tui_welcome_shown"] = True
            cf.save_config(config)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE,
                         curses.COLOR_BLUE)    # menu bar
        curses.init_pair(2, curses.COLOR_BLACK,
                         curses.COLOR_CYAN)    # selection
        curses.init_pair(3, curses.COLOR_BLACK,
                         curses.COLOR_WHITE)   # status bar
        curses.curs_set(0)
        stdscr.keypad(True)

        # --- State ---
        current = 0
        agenda_sel = 0
        tracker_sel = 0
        time_sel = 0

        menu_h = 3  # 2 lines for menu/status + 1 for padding
        h, w = stdscr.getmaxyx()
        panes = create_main_panes(stdscr, h, w, menu_h)

        MIN_HEIGHT = 8
        MIN_WIDTH = 20

        while True:
            h, w = stdscr.getmaxyx()
            if h < MIN_HEIGHT or w < MIN_WIDTH:
                stdscr.clear()
                stdscr.addstr(
                    0, 0, f"Terminal too small ({w}x{h}).", curses.A_BOLD)
                stdscr.addstr(1, 0, "Resize or lower font size.")
                stdscr.refresh()
                key = stdscr.getch()
                if key in (ord('q'), 27):  # quit or ESC
                    return
                continue

            # Draw menu bar
            try:
                draw_menu(stdscr, SCREENS, current, w, color_pair=1)
            except Exception as e:
                stdscr.addstr(0, 0, f"Menu err: {e}")

            # Erase and border all panes (optional: only border active pane)
            for pane in panes.values():
                pane.erase()
                pane.border()

            # Draw the current tab content on its pane
            active_screen = SCREENS[current]
            active_pane = panes[active_screen]
            try:
                if active_screen == "H":
                    draw_home(active_pane, h, w)
                elif active_screen == "TSK":
                    agenda_sel = draw_agenda(active_pane, h, w, agenda_sel)
                elif active_screen == "TM":
                    time_sel = draw_time(active_pane, h, w, time_sel)
                elif active_screen == "TRK":
                    tracker_sel = draw_trackers(
                        active_pane, h, w, tracker_sel, color_pair=2)
                elif active_screen == "R":
                    draw_report(active_pane, h, w)
            except Exception as e:
                safe_addstr(active_pane, 1, 1, f"Tab err: {e}")

            # Only show the active pane (you could also overlay)
            active_pane.noutrefresh()
            # Draw status/help bar
            if show_status:
                try:
                    draw_status(stdscr, h, w, current)
                except Exception as e:
                    stdscr.addstr(h-1, 0, f"Status err: {e}")

            stdscr.noutrefresh()
            curses.doupdate()

            key = stdscr.getch()

            # --- Key handling ---
            if key == ord("Q"):
                if popup_confirm(stdscr, "Exit the app? (Y/n)"):
                    break
                else:
                    continue
            if key == 27:
                current = 0
                continue
            if key == curses.KEY_RIGHT:
                current = (current + 1) % len(SCREENS)
                continue
            if key == curses.KEY_LEFT:
                current = (current - 1) % len(SCREENS)
                continue

            # Now, context-sensitive key handling per tab:
            if active_screen == "TSK":
                max_idx = len(task_repository.query_tasks(
                    status=None, show_completed=False, sort="priority")) - 1
                if key == curses.KEY_DOWN:
                    agenda_sel = min(agenda_sel + 1, max_idx)
                elif key == curses.KEY_UP:
                    agenda_sel = max(agenda_sel - 1, 0)
                elif key == ord("?"):
                    show_help_popup(stdscr, current)
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
                elif key == ord("e"):
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

            elif active_screen == "TM":
                max_idx = len(
                    time_repository.get_all_time_logs(since=None)) - 1
                if key == curses.KEY_DOWN:
                    time_sel = min(time_sel + 1, max_idx)
                elif key == curses.KEY_UP:
                    time_sel = max(time_sel - 1, 0)
                elif key == ord("?"):
                    show_help_popup(stdscr, current)
                elif key == ord("s"):
                    start_time_tui(stdscr)
                elif key == ord("a"):
                    add_manual_time_entry_tui(stdscr)
                elif key == ord("l"):
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

            elif active_screen == "TRK":
                max_idx = len(track_repository.get_all_trackers()) - 1
                if key == curses.KEY_DOWN:
                    tracker_sel = min(tracker_sel + 1, max_idx)
                elif key == curses.KEY_UP:
                    tracker_sel = max(tracker_sel - 1, 0)
                elif key == ord("?"):
                    show_help_popup(stdscr, current)
                elif key == ord("a"):
                    add_tracker_tui(stdscr)
                elif key == ord("d"):
                    delete_tracker_tui(stdscr, tracker_sel)
                elif key == ord("e"):
                    edit_tracker_tui(stdscr, tracker_sel)
                elif key == ord("l"):
                    log_entry_tui(stdscr, tracker_sel)
                elif key == ord("v"):
                    view_tracker_tui(stdscr, tracker_sel)
                elif key == ord("g"):
                    add_or_edit_goal_tui(stdscr, tracker_sel)
                elif key == ord("x"):
                    delete_goal_tui(stdscr, tracker_sel)
                elif key == ord("V"):
                    view_goals_list_tui(stdscr, tracker_sel)
                elif key == ord("h"):
                    show_goals_help_tui(stdscr)

            elif active_screen == "R":
                if key == ord("?"):
                    show_help_popup(stdscr, current)
                elif key == ord("1"):
                    run_summary_trackers(stdscr)
                elif key == ord("2"):
                    run_summary_time(stdscr)
                elif key == ord("3"):
                    run_daily_tracker(stdscr)
                elif key == ord("4"):
                    run_insights(stdscr)
                elif key == ord("C"):
                    run_clinical_insights(stdscr)
                elif key == ord("B"):
                    draw_burndown(stdscr, 0)
                elif key in (ord("q"), 27):
                    current = 0
    except Exception as e:
        tb = traceback.format_exc()
        log_error(f"UI Error: {str(e)}", tb)
        popup_error(stdscr, e)


def draw_home(pane, h, w):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Home "
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)
        y = 2
        safe_addstr(pane, y, 2, "Top Tasks:", curses.A_UNDERLINE)
        tasks = task_repository.query_tasks(sort="priority")[:3]
        for i, t in enumerate(tasks):
            if y+1+i < max_h - 1:
                safe_addstr(pane, y+1+i, 4, f"{t['title'][:max_w-8]}")
        y += len(tasks) + 2
        safe_addstr(pane, y, 2, "Time:", curses.A_UNDERLINE)
        active = time_repository.get_active_time_entry()
        if active:
            safe_addstr(pane, y+1, 4, f">> {active['title'][:max_w-10]}")
            y += 2
        else:
            logs = time_repository.get_all_time_logs()
            if logs and y+1 < max_h - 1:
                logs = sorted(logs, key=lambda l: l.get(
                    'end', l.get('start', '')), reverse=True)
                last = logs[0]
                safe_addstr(pane,
                            y+1, 4, f"Last: {last['title'][:max_w-10]} ({int(last.get('duration_minutes', 0))} min)")
                y += 2
        safe_addstr(pane, y, 2, "Recent Trackers:", curses.A_UNDERLINE)
        trackers = track_repository.get_all_trackers()[-2:]
        for i, t in enumerate(trackers):
            if y+1+i < max_h - 1:
                safe_addstr(pane, y+1+i, 4, f"{t['title'][:max_w-8]}")
        pane.noutrefresh()

        env_weather = environment_repository.get_latest_environment_data(
            'weather')
        env_air = environment_repository.get_latest_environment_data(
            'air_quality')
        env_moon = environment_repository.get_latest_environment_data('moon')

        if any([env_weather, env_air, env_moon]):
            env_text = f"Weather: {env_weather.get('summary', 'N/A')} | "
            env_text += f"AQI: {env_air.get('index', 'N/A')} | "
            env_text += f"Moon: {env_moon.get('phase', 'N/A')}"
            safe_addstr(pane, h-3, 2, env_text)

    except Exception as e:
        safe_addstr(pane, h-2, 2, f"Home err: {e}", curses.A_BOLD)
        pane.noutrefresh()
