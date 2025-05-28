# lifelog/ui.py

import curses

from lifelog.ui_views import (
    draw_agenda,
    draw_trackers,
    draw_time,
    draw_report,
    draw_env,
    draw_menu,
    draw_status,
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
    current = 0    # which tab
    agenda_sel = 0    # highlighted task in Agenda
    time_sel = 0    # highlighted entry in Time

    # ─── Main Loop ──────────────────────────────────────────────────────────
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()

        # 1) Top menu
        draw_menu(stdscr, SCREENS, current, w, color_pair=1)

        # 2) Active view
        if SCREENS[current] == "Agenda":
            agenda_sel = draw_agenda(stdscr, h, w, agenda_sel)
        elif SCREENS[current] == "Trackers":
            draw_trackers(stdscr, h, w)
        elif SCREENS[current] == "Time":
            time_sel = draw_time(stdscr, h, w, time_sel)
        elif SCREENS[current] == "Report":
            draw_report(stdscr, h, w)
        elif SCREENS[current] == "Environment":
            draw_env(stdscr, h, w)

        # 3) Bottom status/help bar
        if show_status:
            draw_status(stdscr, h, w, current)

        stdscr.refresh()
        key = stdscr.getch()

        # ─── Global Quit & Tab Nav ───────────────────────────────────────────
        if key in (ord("q"), 27):
            break
        elif key == curses.KEY_RIGHT:
            current = (current + 1) % len(SCREENS)
        elif key == curses.KEY_LEFT:
            current = (current - 1) % len(SCREENS)

        # ─── Agenda-Specific Nav & Commands ─────────────────────────────────
        elif SCREENS[current] == "Agenda":
            if key == curses.KEY_DOWN:
                agenda_sel += 1
            elif key == curses.KEY_UP:
                agenda_sel -= 1
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
            if key == curses.KEY_DOWN:
                time_sel += 1
            elif key == curses.KEY_UP:
                time_sel -= 1
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

        # (Other screens’ commands go here)

    # end while
