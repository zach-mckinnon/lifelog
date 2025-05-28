# lifelog/ui_views.py

from lifelog.commands.utils.db import time_repository
from lifelog.commands.utils.db import task_repository, time_repository
from lifelog.commands.utils.shared_utils import parse_date_string
from datetime import datetime
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


def draw_status(stdscr, h, w, msg="", current_tab=0):
    """
    Draws a controls/status bar on the bottom row of the screen.
      - stdscr: the main curses window
      - h, w : height and width of stdscr
      - msg  : optional dynamic message (e.g. “Saved!”)
    """
    status_y = h - 1

    stdscr.attron(curses.A_REVERSE)
    stdscr.hline(status_y, 0, ' ', w)

    # hints differ per tab
    if current_tab == 0:  # Agenda
        hint = "←/→ Switch   ↑/↓ Move   a:Add  d:Del  Enter:Edit  v:View  s:Start  p:Pause  o:Done  f:Filter  r:Recur  n:Notes   q:Quit"
    elif current_tab == 2:  # Time
        hint = "←/→ Switch   ↑/↓ Move   s:Start  p:Stop  v:Status  y:Summary  e:Edit  x:Delete   q:Quit"
    else:
        hint = "←/→ Switch   q:Quit"

    stdscr.addstr(status_y, 1, hint[: w - 2])

    if msg:
        x = len(hint) + 3
        stdscr.addstr(status_y, x, msg[: w - x - 1], curses.A_BOLD)

    stdscr.attroff(curses.A_REVERSE)


def draw_menu(stdscr, tabs, current, w):
    menu_h = 3
    stdscr.attron(curses.A_REVERSE)
    stdscr.hline(menu_h - 1, 0, ' ', w)
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
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    n = len(tasks)
    if n == 0:
        return 0

    # clamp selection
    selected_idx = max(0, min(selected_idx, n-1))

    pane = curses.newwin(body_h, list_w, menu_h, cal_w)
    pane.border()
    pane.addstr(0, (list_w-6)//2, " Tasks ", curses.A_BOLD)

    pad_h = max(body_h-2, n)
    pad = curses.newpad(pad_h, list_w-2)
    for i, t in enumerate(tasks):
        due = t.get("due") or ""
        due_str = due.split("T")[0] if due else "-"
        recur_mark = " 🔁" if t.get("recur_interval") else ""
        line = f"{t['id']:>2}[{t['priority']}] {due_str} {t['title']}{recur_mark}"
        attr = curses.color_pair(2) if i == selected_idx else curses.A_NORMAL
        pad.addstr(i, 0, line[:list_w-3], attr)

    start = max(0, selected_idx - (body_h-3))
    pad.refresh(start, 0,
                menu_h+1, cal_w+1,
                menu_h+body_h-2, w-2)
    pane.refresh()

    return selected_idx


def add_task_tui(stdscr):
    # 1) Prompt for title
    title = popup_input(stdscr, "New Task Title:")
    if not title:
        return

    # 2) Prompt for optional due date
    due_str = popup_input(stdscr, "Due (e.g. tomorrow) [optional]:")
    due_iso = None
    if due_str:
        try:
            due_iso = parse_date_string(due_str).isoformat()
        except Exception as e:
            popup_confirm(stdscr, f"❌ Invalid date: {e}")
            return

    # 3) Build and save
    now = datetime.now().isoformat()
    task_data = {
        "title": title,
        "created": now,
        "due": due_iso,
        "status": "backlog",
        "priority": 0
    }
    task_repository.add_task(task_data)

    # 4) Confirm
    popup_confirm(stdscr, f"✅ Added task '{title}'")


def delete_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    tid = tasks[sel]["id"]
    if popup_confirm(stdscr, f"Delete task #{tid}?"):
        try:
            task_repository.delete_task(tid)
            popup_show(stdscr, [f"🗑️ Deleted #{tid}"])
        except Exception as e:
            popup_show(stdscr, [f"❌ Error: {e}"])


def edit_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    # prompt full field set…
    new_title = popup_input(stdscr, f"Title [{t['title']}]:")
    new_due = popup_input(stdscr, f"Due [{t.get('due') or '-'}]:")
    new_cat = popup_input(stdscr, f"Category [{t.get('category') or '-'}]:")
    new_prj = popup_input(stdscr, f"Project [{t.get('project') or '-'}]:")
    new_prio = popup_input(stdscr, f"Priority [{t['priority']}]:")
    updates = {}
    if new_title:
        updates["title"] = new_title
    if new_due:
        try:
            updates["due"] = parse_date_string(new_due).isoformat()
        except Exception as e:
            return popup_show(stdscr, [f"❌ Bad date: {e}"])
    if new_cat:
        updates["category"] = new_cat
    if new_prj:
        updates["project"] = new_prj
    if new_prio and new_prio.isdigit():
        updates["priority"] = int(new_prio)
    if updates:
        try:
            task_repository.update_task(t["id"], updates)
            popup_show(stdscr, [f"✏️ Updated #{t['id']}"])
        except Exception as e:
            popup_show(stdscr, [f"❌ Error: {e}"])


def edit_recurrence_tui(stdscr, sel):
    """
    Prompt the user to edit recurrence rules for the selected task.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    # Show current settings
    current = t.get("recurrence") or {}
    lines = [
        f"Current Recurrence:",
        f"  everyX: {current.get('everyX') or '-'}",
        f"  unit:   {current.get('unit') or '-'}",
        f"  daysOfWeek: {','.join(map(str, current.get('daysOfWeek', []))) or '-'}"
    ]
    popup_show(stdscr, lines, title=" Recurrence ")

    # Prompt for new values
    everyX = popup_input(stdscr, f"Every X [{current.get('everyX') or ''}]:")
    unit = popup_input(
        stdscr, f"Unit (days/weeks/months) [{current.get('unit') or ''}]:")
    days = popup_input(
        stdscr, f"DaysOfWeek (0-6 comma list) [{','.join(map(str, current.get('daysOfWeek', [])))}]:")

    # Build updates
    updates = {}
    try:
        if everyX:
            updates["everyX"] = int(everyX)
        if unit:
            updates["unit"] = unit
        if days:
            updates["daysOfWeek"] = [int(d) for d in days.split(",") if d]
    except Exception as e:
        popup_show(stdscr, [f"❌ Invalid recurrence: {e}"])
        return

    # Save
    try:
        task_repository.update_task(t["id"], {"recurrence": updates})
        popup_show(stdscr, [f"🔁 Recurrence updated"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def edit_notes_tui(stdscr, sel):
    """
    Prompt the user to view/edit notes for the selected task.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    current = t.get("notes") or ""
    # Prompt multiline notes (single-line here for simplicity)
    note = popup_input(stdscr, f"Notes [{current}]:")
    try:
        task_repository.update_task(t["id"], {"notes": note or None})
        popup_show(stdscr, ["📝 Notes updated"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])

# --- Filter Toggle ---


# Module‐level state for task filter:
TASK_FILTERS = ["backlog", "active", "done"]
current_filter_idx = 0


def cycle_task_filter(stdscr):
    """
    Cycle through TASK_FILTERS and show the new filter.
    draw_agenda() must read this state.
    """
    global current_filter_idx
    current_filter_idx = (current_filter_idx + 1) % len(TASK_FILTERS)
    popup_show(stdscr, [f"Filter: {TASK_FILTERS[current_filter_idx]}"])


def view_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    lines = [f"{k}: {v or '-'}" for k, v in t.items()]
    popup_show(stdscr, lines, title=" Task Details ")


def start_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    tid = tasks[sel]["id"]
    now_iso = datetime.now().isoformat()
    try:
        task_repository.update_task(
            tid, {"status": "active", "start": now_iso})
        time_repository.start_time_entry(
            title=tasks[sel]["title"], task_id=tid, start_time=now_iso
        )
        popup_show(stdscr, [f"▶️ Started #{tid}"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def stop_task_tui(stdscr, sel):
    active = time_repository.get_active_time_entry()
    if not active or not active.get("task_id"):
        popup_show(stdscr, ["⚠️ No active task"])
        return
    tid = active["task_id"]
    now_iso = datetime.now().isoformat()
    try:
        time_repository.stop_active_time_entry(end_time=now_iso)
        task_repository.update_task(tid, {"status": "backlog"})
        popup_show(stdscr, [f"⏸️ Paused #{tid}"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def done_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    tid = tasks[sel]["id"]
    try:
        active = time_repository.get_active_time_entry()
        if active and active.get("task_id") == tid:
            time_repository.stop_active_time_entry(
                end_time=datetime.now().isoformat())
        task_repository.update_task(
            tid, {"status": "done", "end": datetime.now().isoformat()})
        popup_show(stdscr, [f"✔️ Done #{tid}"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


# -------------------------------------------------------------------
# Trackers view: list with goals & progress
# -------------------------------------------------------------------


def draw_trackers(stdscr, h, w, color_pair=0):
    menu_h = 3
    title = " Trackers "
    pane = create_pane(stdscr, menu_h, h, w, title, color_pair=color_pair)

    data = track_repository.get_all_trackers()
    pad_h = max(len(data)+5, h)  # ensure pad is tall enough
    pad = curses.newpad(pad_h, w-4)
    selected = getattr(draw_trackers, "sel_idx", 0)

    # draw rows
    col_widths = (4, 20, 20, 10)  # ID, Title, Goal, Progress
    for i, t in enumerate(data):
        y = i
        goals = track_repository.get_goals_for_tracker(t["id"]) or [{}]
        g = goals[0]
        report = generate_goal_report(t) if goals else {}
        prog = report.get("display_format", {}).get("primary", "-")
        parts = (
            f"{t['id']}".ljust(col_widths[0]),
            t['title'][:col_widths[1]].ljust(col_widths[1]),
            g.get("title", "-")[:col_widths[2]].ljust(col_widths[2]),
            prog.ljust(col_widths[3])
        )
        line = " ".join(parts)
        attr = curses.A_REVERSE if i == selected else curses.A_NORMAL
        if color_pair:
            pad.attron(curses.color_pair(color_pair))
        pad.addstr(y, 0, line, attr)
        if color_pair:
            pad.attroff(curses.color_pair(color_pair))

    # show the pad inside the pane
    pane.refresh()
    pad.refresh(selected, 0, menu_h+1, 2, h-2, w-2)

    # capture keys for selection
    key = stdscr.getch()
    if key == curses.KEY_DOWN and selected < len(data)-1:
        selected += 1
    elif key == curses.KEY_UP and selected > 0:
        selected -= 1
    elif key in (10, 13):  # Enter to edit
        popup_confirm(stdscr, f"Edit tracker {data[selected]['title']}?")
    draw_trackers.sel_idx = selected  # persist between calls


# -------------------------------------------------------------------
# Time view: summary table (last 7 days)
# -------------------------------------------------------------------


def draw_time(stdscr, h, w, selected_idx):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(1, 2, "🕒 Time Spent (last 7 days)", curses.A_BOLD)

    # show active session if exists
    active = time_repository.get_active_time_entry()
    y = 3
    if active:
        start_dt = datetime.fromisoformat(active["start"])
        elapsed = (datetime.now() - start_dt).total_seconds()//60
        pane.addstr(
            y, 2, f"▶️ Running: {active['title']} ({int(elapsed)} min)", curses.A_BOLD)
        y += 2

    # history pad
    since = datetime.now() - timedelta(days=7)
    logs = time_repository.get_all_time_logs(since=since)
    n = len(logs)
    if n == 0:
        pane.addstr(y, 2, "(no history)")
        pane.refresh()
        return 0

    selected_idx = max(0, min(selected_idx, n-1))
    pad_h = max(body_h-y-2, n)
    pad = curses.newpad(pad_h, w-4)
    for i, r in enumerate(logs):
        m = int(r.get("duration_minutes", 0))
        line = f"{r['id']:>2} {r['title'][:20]:20} {m:>4} min"
        attr = curses.color_pair(2) if i == selected_idx else curses.A_NORMAL
        pad.addstr(i, 0, line[:w-6], attr)

    start = max(0, selected_idx - (body_h - y - 3))
    pad.refresh(start, 0,
                menu_h+y, 2,
                menu_h+body_h-2, w-2)
    pane.refresh()
    return selected_idx


# ——— Start Timer ———

def start_time_tui(stdscr):
    title = popup_input(stdscr, "Activity Title:")
    if not title:
        return

    # Optional category/project
    cat = popup_input(stdscr, "Category [optional]:")
    proj = popup_input(stdscr, "Project  [optional]:")

    # Optional past start time
    past = popup_input(stdscr, "Start time (e.g. '30m ago') [optional]:")
    try:
        start_dt = parse_date_string(past) if past else datetime.now()
    except Exception as e:
        popup_confirm(stdscr, f"❌ Invalid time: {e}")
        return

    time_repository.start_time_entry(
        title=title,
        category=cat or None,
        project=proj or None,
        start_time=start_dt.isoformat(),
    )
    popup_confirm(stdscr, f"▶️ Started '{title}'")

# ——— Stop Timer ———


def stop_time_tui(stdscr):
    active = time_repository.get_active_time_entry()
    if not active:
        popup_confirm(stdscr, "⚠️ No active timer.")
        return

    # Optional past end time
    past = popup_input(stdscr, "End time (e.g. '5m ago') [optional]:")
    try:
        end_dt = parse_date_string(past) if past else datetime.now()
    except Exception as e:
        popup_confirm(stdscr, f"❌ Invalid time: {e}")
        return

    time_repository.stop_active_time_entry(end_time=end_dt.isoformat())
    # Compute duration in minutes
    start_dt = datetime.fromisoformat(active["start"])
    mins = round((end_dt - start_dt).total_seconds() / 60, 2)
    popup_confirm(stdscr, f"⏹️ Stopped. {mins} min on '{active['title']}'")

# ——— View Status ———


def status_time_tui(stdscr):
    active = time_repository.get_active_time_entry()
    if not active:
        popup_show(stdscr, ["No active timer."], title=" Status ")
        return

    start_dt = datetime.fromisoformat(active["start"])
    elapsed = datetime.now() - start_dt
    mins = round(elapsed.total_seconds() / 60, 2)
    lines = [
        f"Title:   {active['title']}",
        f"Since:   {start_dt.strftime('%Y-%m-%d %H:%M')}",
        f"Elapsed: {mins} min",
    ]
    if active.get("category"):
        lines.insert(1, f"Category: {active['category']}")
    if active.get("project"):
        lines.insert(2, f"Project:  {active['project']}")
    popup_show(stdscr, lines, title=" Status ")

# ——— Summary ———


def summary_time_tui(stdscr):
    # Prompt grouping field
    by = popup_input(stdscr, "Group by [title/category/project]:") or "title"
    period = popup_input(stdscr, "Period [day/week/month/all]:") or "week"

    # Determine time window
    now = datetime.now()
    if period == "day":
        since = now - timedelta(days=1)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(days=365*10)

    # Fetch logs and aggregate
    logs = time_repository.get_all_time_logs(since=since)
    totals = {}
    for r in logs:
        key = r.get(by) or "(none)"
        totals[key] = totals.get(key, 0) + (r.get("duration_minutes") or 0)
    if not totals:
        popup_show(stdscr, ["No records found."], title=" Summary ")
        return

    # Build lines for popup
    lines = [f"{by.capitalize():<15}Total Min"]
    for k, v in sorted(totals.items(), key=lambda x: -x[1]):
        lines.append(f"{k[:15]:<15}{int(v)}")

    popup_show(stdscr, lines, title=" Summary ")


def edit_time_entry_tui(stdscr, sel):
    logs = time_repository.get_all_time_logs(
        since=datetime.now()-timedelta(days=365))
    entry = logs[sel]
    new_tags = popup_input(stdscr, f"Tags [{entry.get('tags') or '-'}]:")
    new_notes = popup_input(stdscr, f"Notes [{entry.get('notes') or '-'}]:")
    try:
        time_repository.update_time_entry(
            entry["id"], tags=new_tags or None, notes=new_notes or None)
        popup_show(stdscr, [f"✏️ Updated entry #{entry['id']}"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def delete_time_entry_tui(stdscr, sel):
    logs = time_repository.get_all_time_logs(
        since=datetime.now()-timedelta(days=365))
    entry = logs[sel]
    if popup_confirm(stdscr, f"Delete entry #{entry['id']}?"):
        try:
            time_repository.delete_time_entry(entry["id"])
            popup_show(stdscr, [f"🗑️ Deleted #{entry['id']}"])
        except Exception as e:
            popup_show(stdscr, [f"❌ Error: {e}"])

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


# Popups

def popup_show(stdscr, lines, title=""):
    """
    Show a centered, read-only popup window with:
      - lines: list of strings to display
      - title: optional string to render in the top border
    Waits for any key before returning.
    """
    # 1) Measure screen and compute popup size
    h, w = stdscr.getmaxyx()
    # 2 for border, 1 for title, 1 for hint
    ph = len(lines) + 4
    pw = max(len(l) for l in lines + [title]) + 4

    # 2) Center popup
    y = (h - ph) // 2
    x = (w - pw) // 2

    # 3) Create window, hide main cursor
    win = curses.newwin(ph, pw, y, x)
    curses.curs_set(0)

    # 4) Draw border and optional title
    win.border()
    if title:
        win.addstr(0, (pw - len(title)) // 2, title, curses.A_BOLD)

    # 5) Render each line inside
    for idx, line in enumerate(lines, start=1):
        win.addstr(idx, 2, line[: pw - 4])

    # 6) Add a dismiss hint
    hint = "Press any key to close"
    win.addstr(ph - 2, 2, hint[: pw - 4], curses.A_DIM)

    # 7) Refresh and wait
    win.refresh()
    win.getch()

    # 8) Clean up: clear popup and redraw underlying screen
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()


def popup_input(stdscr, prompt):
    """Show a centered box prompting the user to type a line of text."""
    h, w = stdscr.getmaxyx()
    ph, pw = 5, max(len(prompt), 20) + 4
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    win.addstr(1, 2, prompt)
    win.addstr(2, 2, "> ")
    curses.echo()
    curses.curs_set(1)
    win.refresh()
    inp = win.getstr(2, 4, pw-6).decode().strip()
    curses.noecho()
    curses.curs_set(0)
    return inp


def popup_confirm(stdscr, message):
    h, w = stdscr.getmaxyx()
    lines = [message, "", "[y] Yes    [n] No"]
    ph, pw = len(lines)+2, max(len(l) for l in lines)+4
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    for i, l in enumerate(lines, start=1):
        win.addstr(i, 2, l)
    win.refresh()

    while True:
        k = win.getch()
        if k in (ord('y'), ord('Y')):
            return True
        if k in (ord('n'), ord('N')):
            return False


def create_pane(stdscr, menu_h, h, w, title, x=0, color_pair=0):
    """Make a bordered pane under the menu, above the status line."""
    body_h = h - menu_h - 1
    win = curses.newwin(body_h, w, menu_h, x)
    if color_pair:
        win.attron(curses.color_pair(color_pair))
    win.border()
    if color_pair:
        win.attroff(curses.color_pair(color_pair))
    # title centered
    win.addstr(0, (w - len(title))//2, title, curses.A_BOLD)
    return win
