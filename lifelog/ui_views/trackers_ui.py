# -------------------------------------------------------------------
# Trackers view: list with goals & progress
# -------------------------------------------------------------------


import curses
from datetime import datetime
from lifelog.commands.report import generate_goal_report
from lifelog.utils.db.models import Tracker, TrackerEntry
from lifelog.utils.goal_util import get_description_for_goal_kind
from lifelog.utils.db import track_repository
from lifelog.utils.shared_utils import add_category_to_config, get_available_categories, get_available_tags, parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_select_option, popup_show
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr, tag_picker_tui


def draw_trackers(pane, h, w, selected_idx, color_pair=None):
    trackers = track_repository.get_all_trackers()
    pane.erase()
    max_h, max_w = pane.getmaxyx()
    pane.border()
    title = " Trackers "
    y = 1
    for i, tracker in enumerate(trackers):
        line = f"{tracker.id:>2} {tracker.title:20} {tracker.category or '-':8} {tracker.type:6}"
        if i == selected_idx:
            # Use color_pair if set, otherwise reverse
            attr = curses.color_pair(
                color_pair) if color_pair else curses.A_REVERSE
        else:
            attr = curses.A_NORMAL
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)
    pane.noutrefresh()


def add_tracker_tui(stdscr):
    title = popup_input(stdscr, "Tracker title:")
    if not title:
        return

    type_ = popup_select_option(
        stdscr, "Data type (int, float, bool, str):", ["int", "float", "bool", "str"])
    if not type_:
        return

    cat = popup_select_option(
        stdscr, "Category:", get_available_categories(), allow_new=True)
    if cat and cat not in get_available_categories():
        add_category_to_config(cat)

    tags = tag_picker_tui(stdscr, get_available_tags())
    notes = popup_input(stdscr, "Notes (optional):")

    now = datetime.now().isoformat()

    # Goal setup (optional)
    goal = None
    if popup_confirm(stdscr, "Add a goal to this tracker?"):
        goal = create_goal_interactive_tui(stdscr, type_)

    tracker = Tracker(
        id=None,
        title=title,
        type=type_,
        category=cat,
        created=now,
        tags=tags,
        notes=notes,
        goals=[goal] if goal else None,
    )
    track_repository.add_tracker(tracker)
    if goal:
        track_repository.add_goal(tracker_id=tracker.id, goal_data=goal)
    popup_show(stdscr, [f"Tracker '{title}' added!"])


def log_entry_tui(stdscr):
    """
    TUI for logging a new tracker entry.
    """
    from lifelog.utils.shared_utils import (
        get_available_categories,
        popup_select_option,
        popup_input,
        popup_show
    )
    import datetime

    # 1. Select tracker
    trackers = track_repository.get_all_trackers()
    if not trackers:
        popup_show(stdscr, ["No trackers found. Add a tracker first!"])
        return

    # Make display list for selection
    tracker_titles = [f"{t.title} [{t.type}]" for t in trackers]
    sel_idx = 0
    tracker_sel = popup_select_option(
        stdscr, "Select tracker:", tracker_titles
    )
    if not tracker_sel:
        return

    # Figure out which tracker was picked
    tracker_idx = tracker_titles.index(tracker_sel)
    tracker = trackers[tracker_idx]

    # 2. Prompt for value
    if tracker.type == "bool":
        value = popup_select_option(stdscr, "Value:", ["True", "False"])
        value = 1 if value == "True" else 0
    elif tracker.type in ("int", "float"):
        unit = getattr(tracker, "unit", "")
        value_prompt = f"Value ({unit}):" if unit else "Value:"
        while True:
            val = popup_input(stdscr, value_prompt)
            try:
                value = float(val)
                if tracker.type == "int":
                    value = int(value)
                break
            except (ValueError, TypeError):
                popup_show(stdscr, ["Invalid number, try again."])
    elif tracker.type == "str":
        value = popup_input(stdscr, "Value (string):")
    else:
        popup_show(stdscr, [f"Unknown tracker type: {tracker.type}"])
        return

    # 3. Timestamp (default now, allow override)
    timestamp_str = popup_input(
        stdscr, "Timestamp (YYYY-MM-DD HH:MM, blank for now):")
    if timestamp_str:
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
        except Exception:
            popup_show(stdscr, ["Invalid date format, using now."])
            timestamp = datetime.datetime.now()
    else:
        timestamp = datetime.datetime.now()

    # 4. Save entry
    try:
        track_repository.add_tracker_entry(
            tracker_id=tracker.id,
            timestamp=timestamp.isoformat(),
            value=value
        )
        popup_show(stdscr, [f"Entry logged for {tracker.title}!"])
    except Exception as e:
        popup_show(stdscr, [f"Failed to log entry: {e}"])


def delete_tracker_tui(stdscr, sel):
    tracker = track_repository.get_tracker_by_id(sel)
    if not tracker:
        popup_show(stdscr, [f"Tracker ID {sel} not found."])
        return

    if popup_confirm(stdscr, f"Delete tracker '{tracker.title}'? This cannot be undone."):
        track_repository.delete_tracker(tracker.id)
        popup_show(stdscr, [f"Tracker '{tracker.title}' deleted."])


def edit_tracker_tui(stdscr, sel):
    tracker = track_repository.get_tracker_by_id(sel)
    if not tracker:
        popup_show(stdscr, [f"Tracker ID {sel} not found."])
        return

    new_title = popup_input(
        stdscr, f"Title [{tracker.title}]:") or tracker.title
    cat = popup_select_option(
        stdscr, f"Category [{tracker.category or '-'}]:",
        get_available_categories(), allow_new=True) or tracker.category
    if cat and cat not in get_available_categories():
        add_category_to_config(cat)
    tags = tag_picker_tui(stdscr, get_available_tags()) or tracker.tags
    notes = popup_input(
        stdscr, f"Notes [{tracker.notes or ''}]:") or tracker.notes

    updates = {}
    if new_title != tracker.title:
        updates["title"] = new_title
    if cat != tracker.category:
        updates["category"] = cat
    if tags != tracker.tags:
        updates["tags"] = tags
    if notes != tracker.notes:
        updates["notes"] = notes

    if updates:
        track_repository.update_tracker(tracker.id, updates)
        popup_show(stdscr, [f"Tracker '{new_title}' updated!"])
    else:
        popup_show(stdscr, ["No changes made."])


def log_tracker_entry_tui(stdscr, sel):
    tracker = track_repository.get_tracker_by_id(sel)
    if not tracker:
        popup_show(stdscr, [f"Tracker ID {sel} not found."])
        return

    value_str = popup_input(
        stdscr, f"Enter value for '{tracker.title}' ({tracker.type}):")
    # Validate type
    if tracker.type == "int":
        try:
            value = int(value_str)
        except ValueError:
            popup_show(stdscr, ["Invalid integer value."])
            return
    elif tracker.type == "float":
        try:
            value = float(value_str)
        except ValueError:
            popup_show(stdscr, ["Invalid float value."])
            return
    elif tracker.type == "bool":
        value = value_str.lower() in ("1", "true", "yes", "y")
    else:
        value = value_str

    timestamp = datetime.now().isoformat()
    entry = TrackerEntry(
        id=None,
        tracker_id=tracker.id,
        timestamp=timestamp,
        value=value,
    )
    track_repository.add_tracker_entry(entry)
    popup_show(stdscr, [f"Entry logged for '{tracker.title}'."])


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


def draw_goal_progress_tui(stdscr, tracker):
    # tracker: Tracker dataclass
    goals = track_repository.get_goals_for_tracker(tracker.id)
    if not goals:
        return
    for goal in goals:
        report = generate_goal_report(
            tracker, goal)  # use your reporting logic
        lines = [
            f"Goal: {goal.title} ({goal.kind})",
            f"Progress: {report['progress']}",
            f"Target: {report['target']}",
            f"Current: {report['current']}"
        ]
        for idx, line in enumerate(lines):
            stdscr.addstr(idx + 2, 2, line)


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


def create_goal_interactive_tui(stdscr, tracker_type: str):
    """
    TUI (popup-based) wizard for creating a goal.
    Returns a goal dict ready to attach to a tracker.
    """
    from lifelog.utils.goal_util import GoalKind, get_description_for_goal_kind
    from lifelog.utils.goal_util import Period

    # Determine allowed goal kinds
    if tracker_type in ["int", "float"]:
        allowed_kinds = [
            GoalKind.SUM.value, GoalKind.COUNT.value, GoalKind.MILESTONE.value,
            GoalKind.RANGE.value, GoalKind.DURATION.value, GoalKind.PERCENTAGE.value,
            GoalKind.REDUCTION.value
        ]
    elif tracker_type == "bool":
        allowed_kinds = [
            GoalKind.COUNT.value, GoalKind.BOOL.value, GoalKind.STREAK.value
        ]
    elif tracker_type == "str":
        allowed_kinds = [
            GoalKind.COUNT.value, GoalKind.REPLACEMENT.value
        ]
    else:
        popup_show(stdscr, [f"Unsupported type for goals: {tracker_type}"])
        return None

    # 1. Pick kind
    kind = popup_select_option(
        stdscr,
        "Goal kind:",
        [f"{k}: {get_description_for_goal_kind(GoalKind(k))}" for k in allowed_kinds]
    )
    if not kind:
        return None
    # Extract just the kind value
    kind = kind.split(":")[0].strip()

    # 2. Title
    title = popup_input(stdscr, "Goal Title:")
    if not title:
        return None

    # 3. Period
    period = popup_select_option(
        stdscr,
        "Period:",
        [p.value for p in Period],
        allow_new=False
    ) or Period.DAY.value

    goal = {
        "title": title,
        "kind": kind,
        "period": period
    }

    # 4. Additional fields by goal kind
    if kind == GoalKind.BOOL.value:
        goal["amount"] = True

    elif kind == GoalKind.RANGE.value:
        min_amt = popup_input(stdscr, "Minimum value:")
        max_amt = popup_input(stdscr, "Maximum value:")
        unit = popup_input(
            stdscr, "Unit (leave blank if none):", max_length=20) or ""
        goal["min_amount"] = float(min_amt) if min_amt else 0
        goal["max_amount"] = float(max_amt) if max_amt else 0
        goal["unit"] = unit

    elif kind == GoalKind.REPLACEMENT.value:
        old = popup_input(stdscr, "Old behavior to replace:")
        new = popup_input(stdscr, "New behavior:")
        amt = popup_input(
            stdscr, "Number of replacements to target (default 1):")
        goal["old_behavior"] = old
        goal["new_behavior"] = new
        goal["amount"] = float(amt) if amt else 1

    elif kind == GoalKind.PERCENTAGE.value:
        target_pct = popup_input(stdscr, "Target percentage (0-100):")
        goal["target_percentage"] = float(target_pct) if target_pct else 100
        goal["current_percentage"] = 0.0

    elif kind == GoalKind.MILESTONE.value:
        target = popup_input(stdscr, "Target value:")
        unit = popup_input(
            stdscr, "Unit (leave blank if none):", max_length=20) or ""
        goal["target"] = float(target) if target else 0
        goal["current"] = 0.0
        goal["unit"] = unit

    elif kind == GoalKind.STREAK.value:
        streak = popup_input(stdscr, "Target streak length:")
        goal["current_streak"] = 0
        goal["best_streak"] = 0
        goal["target_streak"] = int(streak) if streak else 1

    elif kind == GoalKind.DURATION.value:
        amt = popup_input(stdscr, "Target duration amount (number):")
        unit = popup_input(
            stdscr, "Time unit (e.g. minutes, hours):", max_length=20) or "minutes"
        goal["amount"] = float(amt) if amt else 0
        goal["unit"] = unit

    elif kind in [GoalKind.SUM.value, GoalKind.COUNT.value, GoalKind.REDUCTION.value]:
        amt = popup_input(stdscr, "Target amount:")
        unit = popup_input(
            stdscr, "Unit (e.g. 'oz', 'times', leave blank if none):", max_length=20) or ""
        goal["amount"] = float(amt) if amt else 0
        goal["unit"] = unit

    # For other goal types, add logic as needed.

    return goal


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
    try:
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
            amt = popup_input(
                stdscr, f"Target amount [{goal.get('amount','')}] :")
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
            current = popup_input(
                stdscr, f"Current [{goal.get('current','0')}] :")
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
    except ValueError as e:
        popup_show(stdscr, [f"Error: {e}"])
    except Exception as e:
        popup_show(stdscr, [f"Unexpected error: {e}"])


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
