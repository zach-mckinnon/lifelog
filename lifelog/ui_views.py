# lifelog/ui_views.py

from lifelog.commands.report import show_insights, summary_trackers, summary_time, daily_tracker
from lifelog.commands.utils.db import time_repository
from lifelog.commands.utils.db import task_repository, time_repository
from lifelog.commands.utils.shared_utils import parse_date_string
from datetime import datetime
import curses
import calendar
from datetime import datetime, timedelta
from lifelog.commands.utils.db import (
    time_repository,
    track_repository,
    task_repository,
)
from lifelog.commands.report import generate_goal_report

# ─── Shared state for task‐filter  ──────────────────────────────
TASK_FILTERS = ["backlog", "active", "done"]
current_filter_idx = 0

# ─── Popups & Helpers ─────────────────────────────────────────────────


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
    ph, pw = 5, max(len(prompt), 20)+4
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
# -------------------------------------------------------------------
# Helper: draw the top menu tabs
# -------------------------------------------------------------------


# ─── Single, contextual status‐bar ───────────────────────────────────
def draw_status(stdscr, h, w, current_tab):
    status_y = h - 1
    stdscr.attron(curses.color_pair(3))
    stdscr.hline(status_y, 0, " ", w)
    if current_tab == 0:
        hint = "←/→:Switch  ↑/↓:Move  a:Add  d:Del  Enter:Edit  v:View  s:Start  p:Pause  o:Done  f:Filter  r:Recur  n:Notes  Q:Quit"
    elif current_tab == 1:
        hint = "←/→:Switch  ↑/↓:Move  a:Add  d:Del  g:Goal  Q:Quit"
    elif current_tab == 2:
        hint = "←/→:Switch  ↑/↓:Move  s:Start  p:Stop  v:Status  y:Sum  e:Edit  x:Delete  Q:Quit"
    else:
        hint = "←/→:Switch  Q:Quit"
    stdscr.addstr(status_y, 1, hint[: w - 2])
    stdscr.attroff(curses.color_pair(3))


def draw_menu(stdscr, tabs, current, w, color_pair=0):
    stdscr.attron(curses.color_pair(color_pair))
    stdscr.hline(2, 0, ' ', w)
    stdscr.attroff(curses.color_pair(color_pair))
    x = 2
    for idx, name in enumerate(tabs):
        attr = curses.A_REVERSE if idx == current else curses.A_NORMAL
        stdscr.addstr(1, x, f" {name} ", attr)
        x += len(name)+4

# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------


def draw_agenda(stdscr, h, w, selected_idx):
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

    current_status = TASK_FILTERS[current_filter_idx]
    tasks = task_repository.query_tasks(
        status=current_status, show_completed=False, sort="priority"
    )
    n = len(tasks)
    if n == 0:
        # empty‐state UX (Fix 10)
        pane = curses.newwin(body_h, list_w, menu_h, cal_w)
        pane.border()
        pane.addstr(1, 2, "(no tasks)", curses.A_DIM)
        pane.refresh()
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
    # ── Guard: no tasks to delete
    if not tasks:
        return popup_show(stdscr, ["⚠️ No tasks to delete"])
    # ── Guard: sel out of range
    if sel < 0 or sel >= len(tasks):
        return popup_show(stdscr, ["⚠️ No task selected"])

    tid = tasks[sel]["id"]
    if popup_confirm(stdscr, f"Delete task #{tid}?"):
        try:
            task_repository.delete_task(tid)
            popup_show(stdscr, [f"🗑️ Deleted task #{tid}"])
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


def draw_trackers(stdscr, h, w, selected_idx, color_pair=0):
    """
    Renders the Trackers tab:
      - stdscr: main window
      - h,w   : terminal size
      - selected_idx: which row is highlighted
      - color_pair   : optional curses color pair for selection
    Returns the clamped selected_idx.
    """
    menu_h = 3
    body_h = h - menu_h - 1

    # 1) Create the bordered pane
    pane = create_pane(stdscr, menu_h, h, w, " Trackers ",
                       color_pair=color_pair)

    # 2) Fetch data & handle empty state
    trackers = track_repository.get_all_trackers()
    n = len(trackers)
    if n == 0:
        pane.addstr(2, 2, "(no trackers)", curses.A_DIM)
        pane.refresh()
        return 0

    # 3) Clamp selection
    selected_idx = max(0, min(selected_idx, n - 1))

    # 4) Prepare a pad for scrolling if needed
    pad_h = max(n, body_h - 2)
    pad_w = w - 4
    pad = curses.newpad(pad_h, pad_w)

    # 5) Column widths for alignment
    col_widths = (4, 20, 20, 10)  # ID, Title, Goal, Progress

    # 6) Draw each tracker row
    for i, t in enumerate(trackers):
        goals = track_repository.get_goals_for_tracker(t["id"]) or [{}]
        g = goals[0]
        report = generate_goal_report(t) if goals else {}
        prog = report.get("display_format", {}).get("primary", "-")

        parts = (
            str(t["id"]).ljust(col_widths[0]),
            t["title"][:col_widths[1]].ljust(col_widths[1]),
            g.get("title", "-")[:col_widths[2]].ljust(col_widths[2]),
            prog.ljust(col_widths[3]),
        )
        line = " ".join(parts)

        # Highlight selected row
        attr = curses.color_pair(
            color_pair) | curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
        pad.addstr(i, 0, line[:pad_w], attr)

    # 7) Calculate visible window of the pad
    top_row = max(0, selected_idx - (body_h - 3))
    pad.refresh(
        top_row, 0,               # pad upper‐left
        menu_h + 1, 2,            # screen upper‐left
        menu_h + body_h - 2, w - 2  # screen lower‐right
    )

    pane.refresh()
    return selected_idx


def add_tracker_tui(stdscr):
    # 1) Title, Category, Type
    title = popup_input(stdscr, "Title:")
    if not title:
        return
    category = popup_input(stdscr, "Category [optional]:")
    ttype = popup_input(stdscr, "Type (int/float/bool/str):")
    if ttype not in ("int", "float", "bool", "str"):
        return popup_show(stdscr, [f"❌ Invalid type '{ttype}'"])

    # 2) Tags & Notes
    tags = popup_input(stdscr, "Tags (comma-separated) [opt]:")
    notes = popup_input(stdscr, "Notes [opt]:")

    # 3) Optionally create a goal
    if popup_confirm(stdscr, "Add a goal now?"):
        goal = add_goal_tui(stdscr, ttype)
    else:
        goal = None

    # 4) Save
    try:
        tracker_id = track_repository.add_tracker(
            title=title,
            type=ttype,
            category=category or None,
            created=datetime.now().isoformat(),
            goals=[goal] if goal else None
        )
        if goal:
            track_repository.add_goal(tracker_id, goal)
        popup_show(stdscr, [f"✅ Tracker '{title}' added"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def delete_tracker_tui(stdscr, sel):
    data = track_repository.get_all_trackers()
    t = data[sel]
    if popup_confirm(stdscr, f"Delete '{t['title']}' (ID {t['id']})?"):
        try:
            track_repository.delete_tracker(t["id"])
            popup_show(stdscr, [f"🗑️ Deleted '{t['title']}'"])
        except Exception as e:
            popup_show(stdscr, [f"❌ Error: {e}"])


def edit_tracker_tui(stdscr, sel):
    data = track_repository.get_all_trackers()
    t = data[sel]
    # Prompt with defaults
    new_title = popup_input(stdscr, f"Title [{t['title']}]:")
    new_cat = popup_input(stdscr, f"Category [{t.get('category') or '-'}]:")
    new_tags = popup_input(stdscr, f"Tags [{t.get('tags') or '-'}]:")
    new_notes = popup_input(stdscr, f"Notes [{t.get('notes') or '-'}]:")

    updates = {}
    if new_title:
        updates["title"] = new_title
    if new_cat:
        updates["category"] = new_cat
    if new_tags:
        updates["tags"] = new_tags
    if new_notes:
        updates["notes"] = new_notes

    if not updates:
        return popup_show(stdscr, ["⚠️ No changes"])
    try:
        track_repository.update_tracker(t["id"], updates)
        popup_show(stdscr, [f"✏️ Updated '{t['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def log_entry_tui(stdscr, sel):
    data = track_repository.get_all_trackers()
    t = data[sel]
    val_str = popup_input(stdscr, f"Value for '{t['title']}' [{t['type']}]:")
    if not val_str:
        return
    # Validate type
    try:
        val = {
            "int":   int,
            "float": float,
            "bool": lambda s: s.lower() in ("1", "y", "yes", "true"),
            "str":   str,
        }[t["type"]](val_str)
    except Exception as e:
        return popup_show(stdscr, [f"❌ Bad value: {e}"])
    # Optional timestamp
    when = popup_input(stdscr, "Timestamp (ISO or 'now') [opt]:")
    ts = parse_date_string(when).isoformat(
    ) if when else datetime.now().isoformat()

    try:
        track_repository.add_tracker_entry(t["id"], ts, val)
        popup_show(stdscr, [f"✅ Logged {val} at {ts}"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error: {e}"])


def view_tracker_tui(stdscr, sel):
    t = track_repository.get_all_trackers()[sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    entries = track_repository.get_entries_for_tracker(t["id"])
    lines = [
        f"ID:       {t['id']}",
        f"Title:    {t['title']}",
        f"Type:     {t['type']}",
        f"Category: {t.get('category') or '-'}",
        f"Created:  {t['created']}",
        f"Tags:     {t.get('tags') or '-'}",
        f"Notes:    {t.get('notes') or '-'}",
        f"Goals:    {len(goals)}",
        f"Entries:  {len(entries)}",
    ]
    popup_show(stdscr, lines, title=" Tracker Details ")


def create_goal_tui(stdscr, tracker_type):
    """
    Popup‐based wizard to build a goal dict matching your DB schema.
    """
    kind = popup_input(stdscr, "Kind (sum/count/bool/streak/...):")
    title = popup_input(stdscr, "Title:")
    period = popup_input(stdscr, "Period (day/week/month):")
    goal = {"kind": kind, "title": title, "period": period}

    # prompt subtype fields
    if kind in ("sum", "count", "reduction"):
        amt = popup_input(stdscr, "Amount:")
        unit = popup_input(stdscr, "Unit (opt):")
        goal["amount"] = float(amt)
        goal["unit"] = unit or None
    elif kind == "streak":
        targ = popup_input(stdscr, "Target streak (# days):")
        goal["target_streak"] = int(targ)
    # … other kinds similarly …

    return goal


def add_goal_tui(stdscr, tracker_sel):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    # 1) Let user pick goal fields via curses popups
    kind = popup_input(stdscr, "Goal kind (sum/count/bool/...):")
    title = popup_input(stdscr, "Goal title:")
    period = popup_input(stdscr, "Period (day/week/month):")
    # collect any extra params based on kind
    extra = {}
    if kind in ("sum", "count", "reduction"):
        amt = popup_input(stdscr, "Target amount:")
        unit = popup_input(stdscr, "Unit (opt):")
        extra.update({"amount": float(amt), "unit": unit or None})
    # … handle other kinds similarly …

    goal = {"title": title, "kind": kind, "period": period, **extra}

    # 2) Save
    try:
        track_repository.add_goal(t["id"], goal)
        popup_show(stdscr, [f"🎯 Goal added to '{t['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error adding goal: {e}"])


def edit_goal_tui(stdscr, tracker_sel):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    if not goals:
        return popup_show(stdscr, ["⚠️ No goal to edit"])

    g = goals[0]
    # 1) Display current
    lines = [f"{k}: {v}" for k,
             v in g.items() if k not in ("id", "tracker_id")]
    popup_show(stdscr, lines, title="Current Goal")

    # 2) Prompt new values (use defaults)
    new_title = popup_input(stdscr, f"Title [{g['title']}]:") or g["title"]
    new_period = popup_input(stdscr, f"Period [{g['period']}]:") or g["period"]
    updates = {"title": new_title, "period": new_period}
    # optionally handle extra fields like amount/unit
    if "amount" in g:
        amt = popup_input(stdscr, f"Amount [{g['amount']}]:")
        if amt:
            updates["amount"] = float(amt)

    # 3) Save via delete+add or ideally an update
    try:
        # simplest: delete then add
        track_repository.delete_goal(g["id"])
        track_repository.add_goal(t["id"], {**g, **updates})
        popup_show(stdscr, ["✅ Goal updated"])
    except Exception as e:
        popup_show(stdscr, [f"❌ Error updating goal: {e}"])


def delete_goal_tui(stdscr, tracker_sel):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    if not goals:
        return popup_show(stdscr, ["⚠️ No goal to delete"])
    g = goals[0]
    if popup_confirm(stdscr, f"Delete goal '{g['title']}'?"):
        try:
            track_repository.delete_goal(g["id"])
            popup_show(stdscr, ["🗑️ Goal deleted"])
        except Exception as e:
            popup_show(stdscr, [f"❌ Error deleting goal: {e}"])

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


def run_insights(stdscr):
    """Run `llog report insights`"""
    _drop_to_console(show_insights)


def draw_report(stdscr, h, w):
    menu_h = 3
    body_h = h - menu_h - 1
    pane = curses.newwin(body_h, w, menu_h, 0)
    pane.border()
    pane.addstr(1, 2, "📊 Reports", curses.A_BOLD)

    # ← added "4) insights" here
    opts = [
        "1) summary-trackers",
        "2) summary-time",
        "3) daily-tracker",
        "4) insights",
        "q) Back",
    ]
    for i, o in enumerate(opts, start=3):
        pane.addstr(i, 4, o)
    pane.addstr(body_h - 2, 2,
                "Press key to run report → output to console.", curses.A_DIM)
    pane.refresh()
# -------------------------------------------------------------------
# Environment view: hint to dump to console
# -------------------------------------------------------------------


def draw_env(stdscr, h, w):
    pane = create_pane(stdscr, 3, h, w, " Env Data ")
    pane.addstr(2, 2, "Press 'o' to open in console…", curses.A_DIM)
    pane.refresh()


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


# ─── Helpers to run a CLI report and wait ────────────────────────────────
def _drop_to_console(func, *args):
    """
    Exit curses, run a blocking func(*args) that prints via Rich,
    then pause for Enter before returning into curses.
    """
    curses.endwin()
    try:
        func(*args)
    except Exception as e:
        print(f"[red]Error running report: {e}[/]")
    input("\nPress Enter to return to the TUI…")

# ─── Specific report runners ─────────────────────────────────────────────


def run_summary_trackers(stdscr):
    """Run `llog report summary-trackers`"""
    _drop_to_console(summary_trackers)


def run_summary_time(stdscr):
    """Run `llog report summary-time`"""
    _drop_to_console(summary_time)


def run_daily_tracker(stdscr):
    """
    Prompt for a metric name, then run `llog report daily-tracker <metric>`.
    """
    metric = popup_input(stdscr, "Metric name for daily tracker:")
    if not metric:
        return
    _drop_to_console(daily_tracker, metric)
