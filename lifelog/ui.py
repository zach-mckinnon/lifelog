# lifelog/ui.py
import curses

# 1) import your per-module drawers:
from lifelog.ui_views import (
    draw_agenda, draw_trackers, draw_time, draw_report, draw_env, draw_menu
)

SCREENS = ["Agenda", "Trackers", "Time", "Report", "Environment"]


def main(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    current = 0  # index into SCREENS
    while True:
        stdscr.erase()
        # a) draw the top menu bar
        draw_menu(stdscr, SCREENS, current, w)
        # b) dispatch to the active view
        if SCREENS[current] == "Agenda":
            draw_agenda(stdscr, h, w)
        elif SCREENS[current] == "Trackers":
            draw_trackers(stdscr, h, w)
        elif SCREENS[current] == "Time":
            draw_time(stdscr, h, w)
        elif SCREENS[current] == "Report":
            draw_report(stdscr, h, w)
        elif SCREENS[current] == "Environment":
            draw_env(stdscr, h, w)

        stdscr.refresh()
        key = stdscr.getch()
        # ←/→ to change screen
        if key == curses.KEY_RIGHT:
            current = (current + 1) % len(SCREENS)
        elif key == curses.KEY_LEFT:
            current = (current - 1) % len(SCREENS)
        elif key in (ord('q'), 27):  # q or ESC quits
            break
