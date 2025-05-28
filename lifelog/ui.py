# lifelog/ui.py

import curses

from commands.utils.db import task_repository, time_repository, track_repository
from lifelog.ui_views import (
    draw_agenda,
    draw_trackers,
    draw_time,
    draw_report,
    draw_env,
    draw_menu,
    draw_status,
    popup_confirm,
)

SCREENS = ["Agenda", "Trackers", "Time", "Report", "Environment"]


def main(stdscr, show_status: bool = True):
    # ─── Color & Cursor Setup ──────────────────────────────────────────────
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)    # menu bar
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)    # selection
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)   # status bar
    curses.curs_set(0)

    # ─── State ──────────────────────────────────────────────────────────────
    current = 0   # which tab
    agenda_sel = 0   # selected row in Agenda
    tracker_sel = 0   # selected row in Trackers
    time_sel = 0   # selected row in Time

    # ─── Main Loop ──────────────────────────────────────────────────────────
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()

        # 1) Top menu
        draw_menu(stdscr, SCREENS, current, w, color_pair=1)

        if SCREENS[current] == "Agenda":
            agenda_sel = draw_agenda(stdscr, h, w, agenda_sel)
        elif SCREENS[current] == "Trackers":
            tracker_sel = draw_trackers(
                stdscr, h, w, tracker_sel, color_pair=2)
        elif SCREENS[current] == "Time":
            time_sel = draw_time(stdscr, h, w, time_sel)
        elif SCREENS[current] == "Report":
            draw_report(stdscr, h, w)
        else:  # Environment
            draw_env(stdscr, h, w)

        # 3) Bottom status/help bar
        if show_status:
            draw_status(stdscr, h, w, current)

        stdscr.refresh()
        key = stdscr.getch()

        # ─── Handle resize ───────────────────────────────────────────────
        if key == curses.KEY_RESIZE:
            continue  # simply redraw everything

        # ─── Full-exit vs Back ──────────────────────────────────────────
        if key == ord("Q"):             # Shift+Q = quit
            if popup_confirm(stdscr, "❓ Exit the app? (Y/n)"):
                break
            else:
                continue
        elif key == 27:                 # ESC = back to Agenda
            current = 0
            continue

         # ─── Environment “o” (Fix 5 for draw_env) ───────────────────────
        if SCREENS[current] == "Environment" and key == ord("o"):
            curses.endwin()
            from rich.console import Console
            from lifelog.commands.utils.db import environment_repository
            console = Console()
            for sec in ("weather", "air_quality", "moon", "satellite"):
                try:
                    data = environment_repository.get_latest_environment_data(
                        sec)
                    console.rule(f"{sec}")
                    console.print(data)
                except Exception as e:
                    console.print(f"[red]Error: {e}[/]")
            input("Press Enter to return to TUI…")
            continue

         # ─── Tab navigation ──────────────────────────────────────────────
        if key == curses.KEY_RIGHT:
            current = (current + 1) % len(SCREENS)
            continue
        elif key == curses.KEY_LEFT:
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
            elif key == ord("a"):
                from lifelog.ui_views import add_task_tui
                add_task_tui(stdscr)
            elif key == ord("d"):
                from lifelog.ui_views import delete_task_tui
                delete_task_tui(stdscr, agenda_sel)
            elif key in (10, 13):
                from lifelog.ui_views import edit_task_tui
                edit_task_tui(stdscr, agenda_sel)
            elif key == ord("v"):
                from lifelog.ui_views import view_task_tui
                view_task_tui(stdscr, agenda_sel)
            elif key == ord("s"):
                from lifelog.ui_views import start_task_tui
                start_task_tui(stdscr, agenda_sel)
            elif key == ord("p"):
                from lifelog.ui_views import stop_task_tui
                stop_task_tui(stdscr, agenda_sel)
            elif key == ord("o"):
                from lifelog.ui_views import done_task_tui
                done_task_tui(stdscr, agenda_sel)
            elif key == ord("f"):
                from lifelog.ui_views import cycle_task_filter
                cycle_task_filter(stdscr)  # toggles backlog/active/done
            elif key == ord("r"):
                from lifelog.ui_views import edit_recurrence_tui
                edit_recurrence_tui(stdscr, agenda_sel)
            elif key == ord("n"):
                from lifelog.ui_views import edit_notes_tui
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
            elif key == ord("s"):
                from lifelog.ui_views import start_time_tui
                start_time_tui(stdscr)
            elif key == ord("p"):
                from lifelog.ui_views import stop_time_tui
                stop_time_tui(stdscr)
            elif key == ord("v"):
                from lifelog.ui_views import status_time_tui
                status_time_tui(stdscr)
            elif key == ord("y"):
                from lifelog.ui_views import summary_time_tui
                summary_time_tui(stdscr)
            elif key == ord("e"):
                from lifelog.ui_views import edit_time_entry_tui
                edit_time_entry_tui(stdscr, time_sel)
            elif key == ord("x"):
                from lifelog.ui_views import delete_time_entry_tui
                delete_time_entry_tui(stdscr, time_sel)

        elif SCREENS[current] == "Trackers":
            max_idx = len(track_repository.get_all_trackers()) - 1
            if key == curses.KEY_DOWN:
                tracker_sel = min(tracker_sel + 1, max_idx)
                continue
            if key == curses.KEY_UP:
                tracker_sel = max(tracker_sel - 1, 0)
                continue
            elif key == ord("a"):                  # Add new tracker
                from lifelog.ui_views import add_tracker_tui
                add_tracker_tui(stdscr)
            elif key == ord("d"):                  # Delete selected tracker
                from lifelog.ui_views import delete_tracker_tui
                delete_tracker_tui(stdscr, tracker_sel)
            elif key in (10, 13):                   # Enter → Edit tracker
                from lifelog.ui_views import edit_tracker_tui
                edit_tracker_tui(stdscr, tracker_sel)
            elif key == ord("l"):                  # l → Log a new entry
                from lifelog.ui_views import log_entry_tui
                log_entry_tui(stdscr, tracker_sel)
            elif key == ord("v"):                  # v → View details
                from lifelog.ui_views import view_tracker_tui
                view_tracker_tui(stdscr, tracker_sel)
            elif key == ord("g"):
                # g = add a new goal
                from lifelog.ui_views import add_goal_tui
                add_goal_tui(stdscr, tracker_sel)
            elif key == ord("e"):
                # e = edit goal
                from lifelog.ui_views import edit_goal_tui
                edit_goal_tui(stdscr, tracker_sel)
            elif key == ord("x"):
                # x = delete goal
                from lifelog.ui_views import delete_goal_tui
                delete_goal_tui(stdscr, tracker_sel)

        elif SCREENS[current] == "Report":
            if key == ord("1"):
                from lifelog.ui_views import run_summary_trackers
                run_summary_trackers(stdscr)
            elif key == ord("2"):
                from lifelog.ui_views import run_summary_time
                run_summary_time(stdscr)
            elif key == ord("3"):
                from lifelog.ui_views import run_daily_tracker
                run_daily_tracker(stdscr)
            elif key == ord("4"):   # ← new bindings for insights
                from lifelog.ui_views import run_insights
                run_insights(stdscr)

            elif key in (ord("q"), 27):
                current = 0
    # end while
