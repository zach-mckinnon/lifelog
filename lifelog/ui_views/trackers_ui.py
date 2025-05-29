# -------------------------------------------------------------------
# Trackers view: list with goals & progress
# -------------------------------------------------------------------


import curses
from datetime import datetime
from lifelog.commands.utils.goal_util import get_description_for_goal_kind
from lifelog.commands.report import generate_goal_report
from lifelog.commands.utils.db import track_repository
from lifelog.commands.utils.shared_utils import parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_show
from lifelog.ui_views.ui_helpers import create_pane


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
        return popup_show(stdscr, [f"Invalid type '{ttype}'"])

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
        popup_show(stdscr, [f"Tracker '{title}' added"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


def delete_tracker_tui(stdscr, sel):
    data = track_repository.get_all_trackers()
    t = data[sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    entries = track_repository.get_entries_for_tracker(t["id"])
    msg = f"Delete '{t['title']}' (ID {t['id']})?"
    if goals or entries:
        msg = (
            f"'{t['title']}' has {len(goals)} goals and {len(entries)} entries!\n"
            "This cannot be undone.\n"
            "Are you sure you want to delete?"
        )
    if popup_confirm(stdscr, msg):
        if (goals or entries) and not popup_confirm(stdscr, "Really delete? This will permanently remove all related data."):
            popup_show(stdscr, ["Cancelled"])
            return
        try:
            track_repository.delete_tracker(t["id"])
            popup_show(stdscr, [f"Deleted '{t['title']}'"])
        except Exception as e:
            popup_show(stdscr, [f"Error: {e}"])


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
        return popup_show(stdscr, ["No changes"])
    try:
        track_repository.update_tracker(t["id"], updates)
        popup_show(stdscr, [f"Updated '{t['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


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
        return popup_show(stdscr, [f"Bad value: {e}"])
    # Optional timestamp
    when = popup_input(stdscr, "Timestamp (ISO or 'now') [opt]:")
    ts = parse_date_string(when).isoformat(
    ) if when else datetime.now().isoformat()

    try:
        track_repository.add_tracker_entry(t["id"], ts, val)
        popup_show(stdscr, [f"Logged {val} at {ts}"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


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


def view_goal_tui(stdscr, tracker_sel, goal_idx=0):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    if not goals:
        return popup_show(stdscr, ["No goals found"])
    g = goals[goal_idx]
    kind = g.get('kind')
    lines = [
        f"Title:   {g.get('title', '-')}",
        f"Kind:    {kind}",
        f"Period:  {g.get('period', '-')}"
    ]
    # Show fields based on kind
    if kind == "sum" or kind == "count":
        lines += [
            f"Target:  {g.get('amount', '-')}",
            f"Unit:    {g.get('unit', '-')}"
        ]
    elif kind == "bool":
        lines += [f"Amount:  {g.get('amount', '-') or 'True'}"]
    elif kind == "streak":
        lines += [
            f"Target Streak:   {g.get('target_streak', '-')}",
            f"Current Streak:  {g.get('current_streak', '-')}",
            f"Best Streak:     {g.get('best_streak', '-')}"
        ]
    elif kind == "duration":
        lines += [
            f"Duration: {g.get('amount', '-')}",
            f"Unit:     {g.get('unit', '-')}"
        ]
    elif kind == "milestone":
        lines += [
            f"Target:   {g.get('target', '-')}",
            f"Current:  {g.get('current', '-')}",
            f"Unit:     {g.get('unit', '-')}"
        ]
    elif kind == "reduction":
        lines += [
            f"Target:   {g.get('amount', '-')}",
            f"Unit:     {g.get('unit', '-')}"
        ]
    elif kind == "range":
        lines += [
            f"Min:      {g.get('min_amount', '-')}",
            f"Max:      {g.get('max_amount', '-')}",
            f"Unit:     {g.get('unit', '-')}",
            f"Mode:     {g.get('mode', '-')}"
        ]
    elif kind == "percentage":
        lines += [
            f"Target %: {g.get('target_percentage', '-')}",
            f"Current %:{g.get('current_percentage', '-')}"
        ]
    elif kind == "replacement":
        lines += [
            f"Old Behavior:    {g.get('old_behavior', '-')}",
            f"New Behavior:    {g.get('new_behavior', '-')}",
            f"Amount:          {g.get('amount', '-') or '1'}"
        ]
    # General progress field (if present)
    if "progress" in g:
        lines += [f"Progress: {g['progress']}"]
    popup_show(stdscr, lines, title=" Goal Details ")


def view_goals_list_tui(stdscr, tracker_sel):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    if not goals:
        return popup_show(stdscr, ["No goals found"])
    # List all goals and allow selection
    idx = 0
    while True:
        lines = []
        for i, g in enumerate(goals):
            line = f"{i+1:>2}. {g.get('title','-')[:20]:20} [{g.get('kind','-')}]"
            if i == idx:
                line = "> " + line
            lines.append(line)
        lines.append("")
        lines.append("Enter: view goal  ↑/↓: select  q: quit")
        popup_show(stdscr, lines, title=f"Goals for {t['title']}", wait=False)
        c = stdscr.getch()
        if c in (ord('q'), 27):
            break
        elif c in (10, 13):
            view_goal_tui(stdscr, tracker_sel, idx)
        elif c == curses.KEY_DOWN:
            idx = min(idx + 1, len(goals) - 1)
        elif c == curses.KEY_UP:
            idx = max(idx - 1, 0)


def show_goals_help_tui(stdscr):
    lines = [
        "Goal Kinds:",
        "sum       - Track total (e.g. water, pages)",
        "count     - # times something happened",
        "bool      - Yes/no (habit done)",
        "streak    - Consecutive days",
        "duration  - Time spent",
        "milestone - Progress to big target",
        "reduction - Lower is better (e.g. smoking)",
        "range     - Stay within bounds (e.g. weight)",
        "percentage- Percent toward target",
        "replacement - Swap behavior (soda→water)",
        "",
        "Press any key to return"
    ]
    popup_show(stdscr, lines, title=" Goal Types ")


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
    popup_show(stdscr, [get_description_for_goal_kind(kind)],
               title="About this goal kind")
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
        popup_show(stdscr, [f"Goal added to '{t['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error adding goal: {e}"])


def edit_goal_tui(stdscr, tracker_sel, goal_idx=0):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    if not goals:
        return popup_show(stdscr, ["No goal to edit"])
    g = goals[goal_idx]
    kind = g.get('kind')

    updates = {}
    # Show/edit all fields per type
    new_title = popup_input(stdscr, f"Title [{g.get('title', '')}]:")
    if new_title:
        updates["title"] = new_title
    new_period = popup_input(stdscr, f"Period [{g.get('period', '')}]:")
    if new_period:
        updates["period"] = new_period
    # Kind-specific edits
    if kind in ("sum", "count"):
        amt = popup_input(stdscr, f"Target [{g.get('amount', '')}]:")
        unit = popup_input(stdscr, f"Unit [{g.get('unit', '')}]:")
        if amt:
            updates["amount"] = float(amt)
        if unit:
            updates["unit"] = unit
    elif kind == "bool":
        pass  # nothing extra to edit
    elif kind == "streak":
        for field in ("target_streak", "current_streak", "best_streak"):
            val = popup_input(
                stdscr, f"{field.replace('_', ' ').title()} [{g.get(field, '')}]:")
            if val:
                updates[field] = int(val)
    elif kind == "duration":
        amt = popup_input(stdscr, f"Duration [{g.get('amount', '')}]:")
        unit = popup_input(stdscr, f"Unit [{g.get('unit', '')}]:")
        if amt:
            updates["amount"] = float(amt)
        if unit:
            updates["unit"] = unit
    elif kind == "milestone":
        targ = popup_input(stdscr, f"Target [{g.get('target', '')}]:")
        cur = popup_input(stdscr, f"Current [{g.get('current', '')}]:")
        unit = popup_input(stdscr, f"Unit [{g.get('unit', '')}]:")
        if targ:
            updates["target"] = float(targ)
        if cur:
            updates["current"] = float(cur)
        if unit:
            updates["unit"] = unit
    elif kind == "reduction":
        amt = popup_input(stdscr, f"Target [{g.get('amount', '')}]:")
        unit = popup_input(stdscr, f"Unit [{g.get('unit', '')}]:")
        if amt:
            updates["amount"] = float(amt)
        if unit:
            updates["unit"] = unit
    elif kind == "range":
        min_amt = popup_input(stdscr, f"Min [{g.get('min_amount', '')}]:")
        max_amt = popup_input(stdscr, f"Max [{g.get('max_amount', '')}]:")
        unit = popup_input(stdscr, f"Unit [{g.get('unit', '')}]:")
        mode = popup_input(stdscr, f"Mode [{g.get('mode', '')}]:")
        if min_amt:
            updates["min_amount"] = float(min_amt)
        if max_amt:
            updates["max_amount"] = float(max_amt)
        if unit:
            updates["unit"] = unit
        if mode:
            updates["mode"] = mode
    elif kind == "percentage":
        tgt = popup_input(
            stdscr, f"Target % [{g.get('target_percentage', '')}]:")
        cur = popup_input(
            stdscr, f"Current % [{g.get('current_percentage', '')}]:")
        if tgt:
            updates["target_percentage"] = float(tgt)
        if cur:
            updates["current_percentage"] = float(cur)
    elif kind == "replacement":
        old = popup_input(
            stdscr, f"Old Behavior [{g.get('old_behavior', '')}]:")
        new = popup_input(
            stdscr, f"New Behavior [{g.get('new_behavior', '')}]:")
        amt = popup_input(stdscr, f"Amount [{g.get('amount', '') or 1}]:")
        if old:
            updates["old_behavior"] = old
        if new:
            updates["new_behavior"] = new
        if amt:
            updates["amount"] = float(amt)
    # Save update
    try:
        track_repository.delete_goal(g["id"])
        track_repository.add_goal(t["id"], {**g, **updates})
        popup_show(stdscr, ["Goal updated"])
    except Exception as e:
        popup_show(stdscr, [f"Error updating goal: {e}"])


def delete_goal_tui(stdscr, tracker_sel):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t["id"])
    if not goals:
        return popup_show(stdscr, ["No goal to delete"])
    g = goals[0]
    # Optionally, check if this goal has any linked tracker entries, and warn.
    msg = f"Delete goal '{g['title']}'?"
    if popup_confirm(stdscr, msg):
        if not popup_confirm(stdscr, "Really delete this goal? This cannot be undone."):
            popup_show(stdscr, ["Cancelled"])
            return
        try:
            track_repository.delete_goal(g["id"])
            popup_show(stdscr, ["Goal deleted"])
        except Exception as e:
            popup_show(stdscr, [f"Error deleting goal: {e}"])
