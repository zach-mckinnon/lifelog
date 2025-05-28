# lifelog/ui_views.py

import curses
import calendar
from datetime import datetime, timedelta
from rich.console import Console
from lifelog.commands.utils.db import (
    environment_repository,
    time_repository,
    track_repository,
    task_repository,
)
from lifelog.commands.report import generate_goal_report

# -------------------------------------------------------------------
# Helper: draw the top menu tabs
# -------------------------------------------------------------------


def draw_status(stdscr, h, w, msg=""):
    """
    Draws a controls/status bar on the bottom row of the screen.
      - stdscr: the main curses window
      - h, w : height and width of stdscr
      - msg  : optional dynamic message (e.g. “Saved!”)
    """
    status_y = h - 1                       # bottom line index

    # 1) Reverse-video background for the entire line
    stdscr.attron(curses.A_REVERSE)
    stdscr.hline(status_y, 0, ' ', w)      # fill line with spaces

    # 2) Core control hints
    hint = "←/→:Switch  ↑/↓:Move  a:Add  d:Del  Enter:Edit  q:Quit"
    # start at col 1 to give a 1-col margin
    stdscr.addstr(status_y, 1, hint[: w - 2])

    # 3) Optional message to the right of hints (bold)
    if msg:
        x = len(hint) + 3                  # 2 spaces + 1 margin
        stdscr.addstr(status_y, x, msg[: w - x - 1], curses.A_BOLD)

    # 4) Turn off reverse attribute so other text isn’t reversed
    stdscr.attroff(curses.A_REVERSE)


def draw_menu(stdscr, tabs, current, w):
    menu_h = 3
    stdscr.attron(curses.A_REVERSE)
    stdscr.hline(menu_h - 1, 0, ' ', w)       # fill menu background
    stdscr.attroff(curses.A_REVERSE)

    x = 2
    for idx, name in enumerate(tabs):
        attr = curses.A_REVERSE if idx == current else curses.A_NORMAL
        stdscr.addstr(1, x, f" {name} ", attr)
        x += len(name) + 4
    stdscr.refresh()

# -------------------------------------------------------------------
# Helper: draw the bottom status/help line
# -------------------------------------------------------------------


def draw_status(stdscr, h, w, msg=""):
    status_y = h - 1
    stdscr.hline(status_y, 0, ' ', w, curses.A_REVERSE)
    hint = "←/→:Switch  q:Quit  a:Add  d:Del  Enter:Edit"
    stdscr.addstr(status_y, 2, hint[: w - 4], curses.A_REVERSE)
    if msg:
        stdscr.addstr(status_y, len(hint) + 4,
                      msg[: w - len(hint) - 6], curses.A_REVERSE)
    stdscr.refresh()

# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------


def draw_agenda(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1   # leave bottom line for status
    cal_w = int(w * 0.6)
    list_w = w - cal_w

    # Calendar pane
    cal_win = curses.newwin(body_h, cal_w, menu_h, 0)
    cal_win.border()
    now = datetime.now()
    title = f"{calendar.month_name[now.month]} {now.year}"
    cal_win.addstr(0, (cal_w - len(title)) // 2, title, curses.A_BOLD)
    cal_win.addstr(1, 2, "Su Mo Tu We Th Fr Sa")
    for row_i, week in enumerate(calendar.monthcalendar(now.year, now.month), start=2):
        for col_i, day in enumerate(week):
            x, y = 2 + col_i * 3, row_i
            text = f"{day:2}" if day else "  "
            attr = curses.A_REVERSE if day == now.day else curses.A_NORMAL
            cal_win.addstr(y, x, text, attr)
    cal_win.refresh()

    # Tasks pane
    list_win = curses.newwin(body_h, list_w, menu_h, cal_w)
    list_win.border()
    list_win.addstr(0, 2, " Top Tasks ", curses.A_BOLD)
    tasks = task_repository.query_tasks(
        show_completed=False, sort="priority")[:3]
    for i, t in enumerate(tasks, start=2):
        if i >= body_h - 1:
            break
        due = t.get("due", "")
        due_str = due.split("T")[0] if due else "-"
        line = f"{t['id']:>2} [{t['priority']}] {due_str} {t['title']}"
        list_win.addstr(i, 2, line[: list_w - 4])
    list_win.refresh()

# -------------------------------------------------------------------
# Trackers view: list with goals & progress
# -------------------------------------------------------------------


def draw_trackers(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(
        1, 2, "ID  Title               Goal                Progress", curses.A_BOLD)

    trackers = track_repository.get_all_trackers()
    for idx, t in enumerate(trackers, start=2):
        if idx >= body_h - 1:
            break
        goals = track_repository.get_goals_for_tracker(t["id"])
        if goals:
            goal = goals[0]
            report = generate_goal_report(t)
            prog = report["display_format"]["primary"]
            goal_title = goal["title"]
        else:
            goal_title, prog = "-", "-"
        line = f"{t['id']:>2}  {t['title'][:18]:18}  {goal_title[:18]:18}  {prog}"
        pane.addstr(idx, 2, line[: w - 4])
    pane.refresh()

# -------------------------------------------------------------------
# Time view: summary table (last 7 days)
# -------------------------------------------------------------------


def draw_time(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(1, 2, "🕒 Time Spent (last 7 days)", curses.A_BOLD)
    pane.addstr(2, 2, "Title               Minutes")

    since = datetime.now() - timedelta(days=7)
    logs = time_repository.get_all_time_logs(since=since)
    totals = {}
    for r in logs:
        key = r.get("title") or "(none)"
        totals[key] = totals.get(key, 0) + r.get("duration_minutes", 0)

    for idx, (title, mins) in enumerate(sorted(totals.items(), key=lambda x: -x[1]), start=3):
        if idx >= body_h - 1:
            break
        line = f"{title[:18]:18}  {int(mins):>7}"
        pane.addstr(idx, 2, line)
    pane.refresh()

# -------------------------------------------------------------------
# Report view: options list
# -------------------------------------------------------------------


def draw_report(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(1, 2, "📊 Reports", curses.A_BOLD)

    opts = ["1) summary-trackers", "2) summary-time",
            "3) daily-tracker", "q) Back"]
    for i, o in enumerate(opts, start=3):
        pane.addstr(i, 4, o)
    pane.addstr(body_h - 2, 2,
                "Press key to run report → output to console.", curses.A_DIM)
    pane.refresh()

# -------------------------------------------------------------------
# Environment view: hint to dump to console
# -------------------------------------------------------------------


def draw_env(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(1, 2, "🌡️ Env Data", curses.A_BOLD)
    pane.addstr(
        3, 2, "Press 'o' to open latest Env data in console…", curses.A_DIM)
    pane.refresh()

    key = pane.getch()
    if key == ord("o"):
        curses.endwin()
        console = Console()
        for sec in ("weather", "air_quality", "moon", "satellite"):
            data = environment_repository.get_latest_environment_data(sec)
            console.rule(f"{sec}")
            console.print(data)
        input("Press Enter to return to TUI…")
