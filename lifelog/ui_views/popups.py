# ─── Popups & Helpers ─────────────────────────────────────────────────

import curses


def show_help_popup(stdscr, current_tab):
    lines = []
    if current_tab == 0:
        lines = [
            "Agenda/Tasks Tab:",
            "a: Add Task      q: Quick Add      c: Clone      F: Focus Mode",
            "m: Custom Reminder      d: Delete      Enter: Edit      v: View",
            "s: Start Timer   p: Stop Timer     o: Mark Done   f: Cycle Filter",
            "r: Edit Recurrence    n: Edit Notes",
            "",
            "←/→: Switch Tab   Q: Quit   ?: Close Help"
        ]
    elif current_tab == 1:
        lines = [
            "Trackers Tab:",
            "a: Add Tracker    d: Delete Tracker   Enter: Edit Tracker",
            "l: Log Entry      v: View Tracker     g: Add Goal",
            "e: Edit Goal      x: Delete Goal      h: Goal Help",
            "V: View All Goals for Tracker (if implemented)",
            "",
            "↑/↓: Move   ←/→: Switch Tab   Q: Quit   ?: Close Help"
        ]
    elif current_tab == 2:
        lines = [
            "Time Tab:",
            "s: Start Timer   a: Add Manual Entry   p: Stop Timer",
            "v: Timer Status  y: Summary           e: Edit Entry",
            "x: Delete Entry  w: Stopwatch",
            "W: Week  D: Day  M: Month  A: All Time",
            "",
            "↑/↓: Move   ←/→: Switch Tab   Q: Quit   ?: Close Help"
        ]
    elif current_tab == 3:
        lines = [
            "Reports Tab:",
            "1: Trackers Summary    2: Time Summary",
            "3: Daily Tracker       4: Insights",
            "",
            "Q: Quit   ?: Close Help"
        ]
    else:
        lines = ["Q: Quit   ?: Close Help"]

    popup_show(stdscr, lines, title="Available Hotkeys")


def popup_show(stdscr, lines, title=""):
    h, w = stdscr.getmaxyx()
    ph = len(lines) + 4
    pw = max(len(l) for l in lines + [title]) + 4
    y, x = (h - ph)//2, (w - pw)//2

    win = curses.newwin(ph, pw, y, x)
    curses.curs_set(0)
    win.border()
    if title:
        win.addstr(0, (pw - len(title))//2, title, curses.A_BOLD)
    for i, l in enumerate(lines, start=1):
        win.addstr(i, 2, l[:pw-4])
    win.addstr(ph-2, 2, "Press any key to close", curses.A_DIM)
    win.refresh()
    win.getch()
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()


def popup_input(stdscr, prompt):
    h, w = stdscr.getmaxyx()
    ph, pw = 5, max(len(prompt), 20) + 4
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    win.addstr(1, 2, prompt)
    win.addstr(2, 2, "> ")
    curses.echo()
    curses.curs_set(1)
    win.refresh()
    inp = []
    while True:
        c = win.getch(2, 4 + len(inp))
        if c in (10, 13):  # Enter
            break
        if c in (27,):     # ESC
            inp = []
            break
        if c in (curses.KEY_BACKSPACE, 127, 8):
            if inp:
                inp.pop()
                win.addstr(2, 4 + len(inp), ' ')
                win.move(2, 4 + len(inp))
        else:
            if 32 <= c <= 126:  # Printable
                inp.append(chr(c))
                win.addstr(2, 4 + len(inp) - 1, chr(c))
    curses.noecho()
    curses.curs_set(0)
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()
    return "".join(inp).strip() if inp else None


def popup_confirm(stdscr, message) -> bool:
    h, w = stdscr.getmaxyx()
    ph, pw = 5, len(message)+10
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    win.addstr(1, 2, message)
    win.addstr(3, 2, "[y] Yes    [n] No")
    win.refresh()
    while True:
        c = win.getch()
        if c in (ord("y"), ord("Y")):
            return True
        if c in (ord("n"), ord("N"), 27):
            return False
