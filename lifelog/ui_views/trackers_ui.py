# -------------------------------------------------------------------
# Trackers view: list with goals & progress
# -------------------------------------------------------------------


import curses
from datetime import datetime
from lifelog.commands.utils.goal_util import get_description_for_goal_kind
from lifelog.commands.utils.db import track_repository
from lifelog.commands.utils.shared_utils import parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_show
from lifelog.ui_views.ui_helpers import log_exception


def draw_trackers(pane, h, w, selected_idx, color_pair=0):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Trackers "
        pane.addstr(0, max((max_w - len(title)) // 2, 1), title, curses.A_BOLD)
        trackers = track_repository.get_all_trackers()
        n = len(trackers)
        if n == 0:
            pane.addstr(2, 2, "(no trackers)", curses.A_DIM)
            pane.noutrefresh()
            return 0

        selected_idx = max(0, min(selected_idx, n-1))
        visible_rows = max_h - 3  # 1 for border, 1 for title, 1 for bottom border

        start = max(0, selected_idx - visible_rows // 2)
        end = min(start + visible_rows, n)

        for i, t in enumerate(trackers[start:end], start=start):
            goals = track_repository.get_goals_for_tracker(t["id"]) or [{}]
            g = goals[0]
            line = f"{t['id']:>2} {t['title'][:20]:20} {g.get('title', '-')[:15]:15}"
            attr = curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
            y = 1 + i - start + 1  # 1 for border, 1 for title
            if y < max_h - 1:
                pane.addstr(y, 2, line[:max_w-4], attr)
        pane.noutrefresh()
        return selected_idx
    except Exception as e:
        pane.addstr(h-2, 2, f"Trackers err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        return 0


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
        goal = add_or_edit_goal_tui(stdscr, ttype)
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
        log_exception("add_tracker_tui", e)


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
            log_exception("delete_tracker_tui", e)


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
        log_exception("edit_tracker_tui", e)


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
        log_exception("log_track_tui", e)


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


def add_or_edit_goal_tui(stdscr, tracker_sel, edit_goal=None):
    """
    Popup-based wizard to create or edit a goal dict matching your DB schema.
    If edit_goal is None, creates a new goal. If passed, edits existing goal.
    """
    # --- Fetch tracker and set initial fields ---
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goal = edit_goal.copy() if edit_goal else {}

    # 1. Pick kind (with help)
    kind = popup_input(
        stdscr,
        f"Kind (sum/count/bool/streak/duration/milestone/reduction/range/percentage/replacement)"
        f" [{goal.get('kind','count')}] :"
    ) or goal.get("kind", "count")
    popup_show(stdscr, [get_description_for_goal_kind(kind)],
               title="About this goal kind")

    # 2. Title
    title = popup_input(
        stdscr, f"Title [{goal.get('title','')}] :") or goal.get("title", "")
    # 3. Period (day/week/month)
    period = popup_input(
        stdscr, f"Period (day/week/month) [{goal.get('period','day')}] :") or goal.get("period", "day")

    # --- Fields by kind ---
    data = {
        "title": title,
        "kind": kind,
        "period": period,
    }
    # Numeric goals
    if kind in ("sum", "count", "reduction", "duration"):
        amt = popup_input(stdscr, f"Target amount [{goal.get('amount','')}] :")
        unit = popup_input(stdscr, f"Unit [{goal.get('unit','')}] :")
        if amt:
            data["amount"] = float(amt)
        if unit:
            data["unit"] = unit or None
    # Streak
    if kind == "streak":
        target_streak = popup_input(
            stdscr, f"Target streak [{goal.get('target_streak','')}] :")
        if target_streak:
            data["target_streak"] = int(target_streak)
    # Range
    if kind == "range":
        min_amt = popup_input(
            stdscr, f"Min amount [{goal.get('min_amount','')}] :")
        max_amt = popup_input(
            stdscr, f"Max amount [{goal.get('max_amount','')}] :")
        unit = popup_input(stdscr, f"Unit [{goal.get('unit','')}] :")
        mode = popup_input(stdscr, f"Mode [{goal.get('mode','')}] :")
        if min_amt:
            data["min_amount"] = float(min_amt)
        if max_amt:
            data["max_amount"] = float(max_amt)
        if unit:
            data["unit"] = unit or None
        if mode:
            data["mode"] = mode or None
    # Milestone
    if kind == "milestone":
        target = popup_input(stdscr, f"Target [{goal.get('target','')}] :")
        current = popup_input(stdscr, f"Current [{goal.get('current','0')}] :")
        unit = popup_input(stdscr, f"Unit [{goal.get('unit','')}] :")
        if target:
            data["target"] = float(target)
        if current:
            data["current"] = float(current)
        if unit:
            data["unit"] = unit or None
    # Percentage
    if kind == "percentage":
        target_pct = popup_input(
            stdscr, f"Target % [{goal.get('target_percentage','')}] :")
        current_pct = popup_input(
            stdscr, f"Current % [{goal.get('current_percentage','0')}] :")
        if target_pct:
            data["target_percentage"] = float(target_pct)
        if current_pct:
            data["current_percentage"] = float(current_pct)
    # Bool (habit)
    if kind == "bool":
        data["amount"] = True
    # Replacement
    if kind == "replacement":
        old = popup_input(
            stdscr, f"Old Behavior [{goal.get('old_behavior','')}] :")
        new = popup_input(
            stdscr, f"New Behavior [{goal.get('new_behavior','')}] :")
        amt = popup_input(stdscr, f"Amount [{goal.get('amount','1')}] :")
        if old:
            data["old_behavior"] = old
        if new:
            data["new_behavior"] = new
        if amt:
            data["amount"] = float(amt)

    # --- Save or Update ---
    try:
        if edit_goal:
            # Remove then re-add to update
            track_repository.delete_goal(edit_goal["id"])
            track_repository.add_goal(t["id"], {**edit_goal, **data})
            popup_show(stdscr, ["Goal updated!"])
        else:
            track_repository.add_goal(t["id"], data)
            popup_show(stdscr, [f"Goal added to '{t['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error saving goal: {e}"])


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
            log_exception("delete_goal_tui", e)
