# -------------------------------------------------------------------
# Trackers view: list with goals & progress
# -------------------------------------------------------------------


from lifelog.ui_views.forms import TrackerForm, run_form, run_goal_form, GoalDetailForm
import curses
from datetime import datetime

import npyscreen
from lifelog.commands.report import generate_goal_report
from lifelog.utils.db.models import Tracker, TrackerEntry
from lifelog.utils.goal_util import get_description_for_goal_kind
from lifelog.utils.db import track_repository
from lifelog.utils.shared_utils import add_category_to_config, filter_entries_for_current_period, get_available_categories, get_available_tags, now_utc, parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_select_option, popup_show
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr, tag_picker_tui
from lifelog.ui_views.forms import GoalDetailForm, TrackerEntryForm, TrackerForm, run_form, run_goal_form
from lifelog.utils.hooks import run_hooks


def draw_trackers(pane, h, w, selected_idx, color_pair=None):
    """
    pane: the curses window
    h, w: pane dimensions
    selected_idx: which tracker is highlighted
    color_pair: optional curses color-pair number
    """
    pane.erase()
    max_h, max_w = pane.getmaxyx()
    pane.border()

    # Title :contentReference[oaicite:0]{index=0}
    title = " Trackers "
    safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                title, curses.A_BOLD)

    # Start drawing items two rows down
    y = 2
    # :contentReference[oaicite:1]{index=1}
    trackers = track_repository.get_all_trackers()

    for i, tracker in enumerate(trackers):
        if y >= max_h - 1:
            break  # no more room

        # Build the tracker line
        line = f"{tracker.id:>2} {tracker.title:20} {tracker.category or '-':8} {tracker.type:6}"
        # Highlight selected
        attr = curses.color_pair(color_pair) if (i == selected_idx and color_pair) else \
            curses.A_REVERSE if i == selected_idx else curses.A_NORMAL

        # Draw tracker :contentReference[oaicite:2]{index=2}
        safe_addstr(pane, y, 2, line[:max_w-4], attr)
        y += 1

        # Now fetch and render any goals for this tracker
        goals = track_repository.get_goals_for_tracker(
            tracker.id)  # :contentReference[oaicite:3]{index=3}
        if goals:
            # Fetch all entries once, then filter per goal
            entries = track_repository.get_entries_for_tracker(tracker.id)
            for goal in goals:
                if y >= max_h - 1:
                    break

                # Filter entries by the goal’s period (day/week/month/all) :contentReference[oaicite:4]{index=4}
                df = filter_entries_for_current_period(
                    [e.__dict__ for e in entries], period=goal.period
                )

                # Compute a simple progress summary
                if goal.kind == "range":
                    # assume goal.amount is upper bound
                    current = df['value'].iloc[-1] if not df.empty else 0
                    status = f"{current}/{goal.amount}"
                elif goal.kind in ("count", "percentage"):
                    count = len(df)
                    target = goal.target or goal.amount
                    status = f"{count}/{target}"
                else:
                    # fallback: show last value
                    status = df['value'].iloc[-1] if not df.empty else "-"

                goal_line = f"   • {goal.title} [{goal.kind}] → {status}"
                safe_addstr(pane, y, 4, goal_line[:max_w-6], curses.A_DIM)
                y += 1

    pane.noutrefresh()


def add_tracker_tui(stdscr):
    """Add a tracker using a form UI."""
    data = run_form(TrackerForm)
    if not data or not data.get("title"):
        return

    now = now_utc().isoformat()
    tracker = Tracker(
        id=None,
        title=data["title"],
        type=data["type"],
        category=data["category"],
        created=now,
        tags=data["tags"],
        notes=data["notes"],
        goals=[]
    )

    # Ask about adding a goal (optional)
    if npyscreen.notify_yes_no("Add a goal to this tracker?", title="Goal?"):
        goal_data = run_goal_form()
        if goal_data:
            tracker.goals = [goal_data]

    track_repository.add_tracker(tracker)
    npyscreen.notify_confirm(
        f"Tracker '{tracker.title}' added!", title="Success")


def log_entry_tui(stdscr):
    """Add a tracker entry via a form."""
    trackers = track_repository.get_all_trackers()
    if not trackers:
        npyscreen.notify_confirm(
            "No trackers found. Add a tracker first!", title="Error")
        return

    # Ask user to select a tracker (basic selection for now)
    tracker_titles = [f"{t.title} [{t.type}]" for t in trackers]
    sel_idx = npyscreen.selectOne(tracker_titles, title="Select Tracker")
    if sel_idx is None or sel_idx < 0 or sel_idx >= len(trackers):
        return

    tracker = trackers[sel_idx]
    form = TrackerEntryForm()
    form.tracker_title.value = f"{tracker.title} [{tracker.type}]"
    form.edit()
    entry_data = form.parentApp.form_data
    if not entry_data or not entry_data.get("value"):
        return

    # Parse and validate
    value = entry_data["value"]
    timestamp = entry_data.get("timestamp") or now_utc().isoformat()
    if tracker.type == "int":
        value = int(value)
    elif tracker.type == "float":
        value = float(value)
    elif tracker.type == "bool":
        value = value.lower() in ("1", "true", "yes", "y")
    # else, str

    entry = TrackerEntry(
        id=None,
        tracker_id=tracker.id,
        timestamp=timestamp,
        value=value,
    )
    entry = track_repository.add_tracker_entry(entry)
    run_hooks("tracker", "logged", entry)
    npyscreen.notify_confirm(f"Entry logged for '{tracker.title}'.")


def delete_tracker_tui(stdscr, sel):
    tracker = track_repository.get_tracker_by_id(sel)
    if not tracker:
        popup_show(stdscr, [f"Tracker ID {sel} not found."])
        return

    if popup_confirm(stdscr, f"Delete tracker '{tracker.title}'? This cannot be undone."):
        track_repository.delete_tracker(tracker.id)
        popup_show(stdscr, [f"Tracker '{tracker.title}' deleted."])


def edit_tracker_tui(stdscr, tracker_id):
    """Edit a tracker and optionally add/edit its goals."""
    tracker = track_repository.get_tracker_by_id(tracker_id)
    if not tracker:
        npyscreen.notify_confirm(
            f"Tracker ID {tracker_id} not found.", title="Error")
        return

    # --- Run the Tracker Form
    form = TrackerForm()
    form.title.value = tracker.title
    form.type.value = tracker.type
    form.category.value = tracker.category
    form.tags.value = tracker.tags
    form.notes.value = tracker.notes
    form.edit()
    data = form.parentApp.form_data
    if not data:
        return

    # Update tracker fields if changed
    updates = {}
    for key in ["title", "type", "category", "tags", "notes"]:
        if data.get(key) != getattr(tracker, key):
            updates[key] = data[key]
    if updates:
        track_repository.update_tracker(tracker.id, updates)
        npyscreen.notify_confirm(
            f"Tracker '{tracker.title}' updated!", title="Updated")
    else:
        npyscreen.notify_confirm("No changes made.")

    # --- Prompt for goal edit/add
    if npyscreen.notify_yes_no("Would you like to add or edit this tracker's goals?", title="Goals"):
        # Fetch current goals
        goals = track_repository.get_goals_for_tracker(tracker.id)
        goal_titles = [g.title for g in goals] + ["[Add new goal]", "[Done]"]
        while True:
            sel = npyscreen.selectOne(
                goal_titles, title="Select Goal to Edit/Add")
            if sel is None or sel < 0 or sel >= len(goal_titles):
                break
            # If [Add new goal]
            if sel == len(goal_titles)-2:
                goal_data = run_goal_form()
                if goal_data:
                    track_repository.add_goal(
                        tracker_id=tracker.id, goal_data=goal_data)
                    npyscreen.notify_confirm("Goal added!", title="Success")
                continue
            # If [Done]
            elif sel == len(goal_titles)-1:
                break
            # Else edit the selected goal
            else:
                goal = goals[sel]
                # Use GoalDetailForm with pre-filled data

                class EditGoalApp(npyscreen.NPSAppManaged):
                    def onStart(selfx):
                        selfx.goal_kind = goal.kind
                        form = selfx.addForm(
                            "MAIN", GoalDetailForm, name="Edit Goal")
                        form.title.value = goal.title
                        period_val = goal.period or ""
                        if period_val in [p for p in form.period.values]:
                            form.period.value = form.period.values.index(
                                period_val)
                        else:
                            form.period.value = 0
                        form.amount.value = str(
                            getattr(goal, "amount", "") or "")
                        form.unit.value = str(getattr(goal, "unit", "") or "")
                        form.min_amount.value = str(
                            getattr(goal, "min_amount", "") or "")
                        form.max_amount.value = str(
                            getattr(goal, "max_amount", "") or "")
                        form.mode.value = str(getattr(goal, "mode", "") or "")
                        form.target.value = str(
                            getattr(goal, "target", "") or "")
                        form.current.value = str(
                            getattr(goal, "current", "") or "")
                        form.target_streak.value = str(
                            getattr(goal, "target_streak", "") or "")
                        form.target_percentage.value = str(
                            getattr(goal, "target_percentage", "") or "")
                        form.current_percentage.value = str(
                            getattr(goal, "current_percentage", "") or "")
                        form.old_behavior.value = str(
                            getattr(goal, "old_behavior", "") or "")
                        form.new_behavior.value = str(
                            getattr(goal, "new_behavior", "") or "")
                        form.display()

                app = EditGoalApp()
                app.run()
                updated_data = getattr(app, 'form_data', None)
                if updated_data:
                    track_repository.update_goal(goal.id, updated_data)
                    npyscreen.notify_confirm("Goal updated!", title="Updated")
                else:
                    npyscreen.notify_confirm(
                        "No changes made.", title="Edit Goal")


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

    timestamp = now_utc().isoformat()
    entry = TrackerEntry(
        id=None,
        tracker_id=tracker.id,
        timestamp=timestamp,
        value=value,
    )
    _ent = track_repository.add_tracker_entry(entry)
    run_hooks("tracker", "logged", _ent)
    popup_show(stdscr, [f"Entry logged for '{tracker.title}'."])


def view_tracker_tui(stdscr, sel):
    t = track_repository.get_all_trackers()[sel]
    goals = track_repository.get_goals_for_tracker(t.id)
    entries = track_repository.get_entries_for_tracker(t.id)
    lines = [
        f"ID:       {t.id}",
        f"Title:    {t.title}",
        f"Type:     {t.type}",
        f"Category: {t.category or '-'}",
        f"Created:  {t.created}",
        f"Tags:     {t.tags or '-'}",
        f"Notes:    {t.notes or '-'}",
        f"Goals:    {len(goals)}",
        f"Entries:  {len(entries)}",
    ]
    popup_show(stdscr, lines, title=" Tracker Details ")


def draw_goal_progress_tui(stdscr, tracker):
    """
    For each goal of the given Tracker instance, fetch a report via generate_goal_report(tracker)
    and display summary lines (using display_format and status).
    """
    # Fetch goals as dataclass instances
    goals = track_repository.get_goals_for_tracker(tracker.id)
    if not goals:
        return

    # For each goal, generate report and display
    # Starting at row 2; we may want to clear or manage scrolling externally
    row_offset = 2
    for idx_goal, goal in enumerate(goals):
        # generate_goal_report now takes only tracker, uses first goal internally
        # If you have generate_goal_report(tracker, goal), adjust accordingly.
        report = generate_goal_report(tracker)

        # Display goal header
        header = f"Goal {idx_goal+1}: {goal.title} ({goal.kind})"
        try:
            stdscr.addstr(row_offset, 2, header, curses.A_BOLD)
        except Exception:
            # In case of width issues; ignore or trim
            stdscr.addstr(row_offset, 2, header[:max(
                0, curses.COLS - 4)], curses.A_BOLD)
        row_offset += 1

        # Use display_format for primary/secondary/tertiary
        disp = report.get("display_format", {})
        primary = disp.get("primary", "")
        secondary = disp.get("secondary", "")
        tertiary = disp.get("tertiary", "")

        # Status line
        status = report.get("status", "")

        # Display lines
        for text in (f"  {primary}", f"  {secondary}", f"  {tertiary}", f"  Status: {status}"):
            if text is None:
                continue
            try:
                stdscr.addstr(row_offset, 4, text)
            except Exception:
                stdscr.addstr(row_offset, 4, text[:max(0, curses.COLS - 6)])
            row_offset += 1

        # Add a blank line between goals
        row_offset += 1


def view_goal_tui(stdscr, tracker_sel, goal_idx=0):
    """
    Display details of a selected goal for a tracker.
    tracker_sel: index in list of trackers
    goal_idx: index in list of goals for that tracker
    """
    # Fetch tracker
    trackers = track_repository.get_all_trackers()
    if tracker_sel < 0 or tracker_sel >= len(trackers):
        return popup_show(stdscr, [f"Invalid tracker selection: {tracker_sel}"])
    t = trackers[tracker_sel]

    # Fetch goals
    goals = track_repository.get_goals_for_tracker(t.id)
    if not goals:
        return popup_show(stdscr, ["No goals found"])

    if goal_idx < 0 or goal_idx >= len(goals):
        return popup_show(stdscr, [f"Invalid goal selection: {goal_idx}"])

    g = goals[goal_idx]
    kind = g.kind  # attribute

    # Fetch detail fields via repository
    # Use generic get_goal_details if available, else call specific wrapper
    try:
        # If you implemented get_goal_details:
        details = track_repository.get_goal_details(g.id)
    except AttributeError:
        # Fallback to kind-based wrapper
        if kind == "range":
            details = track_repository.get_goal_range(g.id)
        elif kind == "sum":
            details = track_repository.get_goal_sum(g.id)
        elif kind == "count":
            details = track_repository.get_goal_count(g.id)
        elif kind == "streak":
            details = track_repository.get_goal_streak(g.id)
        elif kind == "duration":
            details = track_repository.get_goal_duration(g.id)
        elif kind == "milestone":
            details = track_repository.get_goal_milestone(g.id)
        elif kind == "reduction":
            details = track_repository.get_goal_reduction(g.id)
        elif kind == "percentage":
            details = track_repository.get_goal_percentage(g.id)
        elif kind == "replacement":
            details = track_repository.get_goal_replacement(g.id)
        else:
            details = {}
    except Exception as e:
        # Log exception if you have logging; for now, show minimal
        details = {}

    # Build lines to display
    lines = []
    lines.append(f"Title:   {g.title or '-'}")
    lines.append(f"Kind:    {kind}")
    lines.append(f"Period:  {g.period or '-'}")

    # Based on kind, add detail lines
    if kind in ("sum", "count", "reduction", "duration"):
        # common field 'amount'
        amt = details.get("amount")
        unit = details.get("unit", "")
        if kind == "sum":
            lines.append(f"Target amount: {amt if amt is not None else '-'}")
            lines.append(f"Unit:          {unit or '-'}")
        elif kind == "count":
            lines.append(f"Target count:  {amt if amt is not None else '-'}")
            lines.append(f"Unit:          {unit or '-'}")
        elif kind == "reduction":
            lines.append(f"Target amount: {amt if amt is not None else '-'}")
            lines.append(f"Unit:          {unit or '-'}")
        elif kind == "duration":
            lines.append(
                f"Target duration: {amt if amt is not None else '-'} {unit or ''}")
    elif kind == "bool":
        # No extra detail fields typically
        lines.append("Completion: Yes/No entries (True counts as done)")
    elif kind == "streak":
        tgt = details.get("target_streak")
        lines.append(f"Target streak: {tgt if tgt is not None else '-'} days")
    elif kind == "milestone":
        tgt = details.get("target")
        unit = details.get("unit", "")
        lines.append(
            f"Target:         {tgt if tgt is not None else '-'} {unit or ''}")
        # For milestone you might show current progress here, but usually via report
    elif kind == "range":
        min_amt = details.get("min_amount")
        max_amt = details.get("max_amount")
        unit = details.get("unit", "")
        mode = details.get("mode", "goal")
        lines.append(
            f"Min:            {min_amt if min_amt is not None else '-'}")
        lines.append(
            f"Max:            {max_amt if max_amt is not None else '-'}")
        lines.append(f"Unit:           {unit or '-'}")
        lines.append(f"Mode:           {mode}")
    elif kind == "percentage":
        tgt_pct = details.get("target_percentage")
        curr_pct = details.get("current_percentage")
        lines.append(
            f"Target %:       {tgt_pct if tgt_pct is not None else '-'}")
        # current_percentage stored is usually initial; actual current from report
    elif kind == "replacement":
        old_beh = details.get("old_behavior", "")
        new_beh = details.get("new_behavior", "")
        amt = details.get("amount")
        lines.append(f"Old Behavior:   {old_beh or '-'}")
        lines.append(f"New Behavior:   {new_beh or '-'}")
        lines.append(f"Amount target:  {amt if amt is not None else '1'}")
    else:
        # Unknown or no detail
        pass

    # Optionally show latest report metrics
    # For extra context, generate a fresh report and show primary/secondary/status
    try:
        report = generate_goal_report(t)
        disp = report.get("display_format", {})
        primary = disp.get("primary", "")
        secondary = disp.get("secondary", "")
        tertiary = disp.get("tertiary", "")
        status = report.get("status", "")
        lines.append("")  # blank separator
        lines.append(f"Report Summary:")
        lines.append(f"  {primary}")
        if secondary:
            lines.append(f"  {secondary}")
        if tertiary:
            lines.append(f"  {tertiary}")
        lines.append(f"  Status: {status}")
    except Exception:
        # If report generation fails, ignore
        pass

    popup_show(stdscr, lines, title=" Goal Details ")


def view_goals_list_tui(stdscr, tracker_sel):
    """
    List all goals for selected tracker and allow viewing details.
    """
    trackers = track_repository.get_all_trackers()
    if tracker_sel < 0 or tracker_sel >= len(trackers):
        return popup_show(stdscr, [f"Invalid tracker selection: {tracker_sel}"])
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t.id)
    if not goals:
        return popup_show(stdscr, ["No goals found"])

    idx = 0
    while True:
        lines = []
        # Build list of goal titles with kind
        for i, g in enumerate(goals):
            title = g.title or "-"
            kind = g.kind or "-"
            display = f"{i+1:>2}. {title[:20]:20} [{kind}]"
            if i == idx:
                display = "> " + display
            else:
                display = "  " + display
            lines.append(display)
        lines.append("")  # blank
        lines.append("Enter: view goal  ↑/↓: select  q: quit")
        popup_show(stdscr, lines, title=f"Goals for {t.title}", wait=False)
        c = stdscr.getch()
        if c in (ord('q'), 27):
            break
        elif c in (10, 13):
            # view selected goal details
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
        goal.amount = True

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
        goal.amount = float(amt) if amt else 1

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
        goal.amount = float(amt) if amt else 0
        goal["unit"] = unit

    elif kind in [GoalKind.SUM.value, GoalKind.COUNT.value, GoalKind.REDUCTION.value]:
        amt = popup_input(stdscr, "Target amount:")
        unit = popup_input(
            stdscr, "Unit (e.g. 'oz', 'times', leave blank if none):", max_length=20) or ""
        goal.amount = float(amt) if amt else 0
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


def add_goal_tui(stdscr, tracker_id):
    """Add a goal to a tracker."""
    tracker = track_repository.get_tracker_by_id(tracker_id)
    if not tracker:
        npyscreen.notify_confirm(
            f"Tracker ID {tracker_id} not found.", title="Error")
        return
    goal_data = run_goal_form()  # launches empty form
    if goal_data:
        track_repository.add_goal(tracker_id=tracker.id, goal_data=goal_data)
        npyscreen.notify_confirm(
            f"Goal added to '{tracker.title}'", title="Success")


def edit_goal_tui(stdscr, tracker_id, goal_id):
    """
    Edit an existing goal for a tracker using the npyscreen GoalDetailForm.
    """
    tracker = track_repository.get_tracker_by_id(tracker_id)
    if not tracker:
        npyscreen.notify_confirm(
            f"Tracker ID {tracker_id} not found.", title="Error")
        return
    goal = track_repository.get_goal_by_id(goal_id)
    if not goal:
        npyscreen.notify_confirm(
            f"Goal ID {goal_id} not found.", title="Error")
        return

    # Define a custom App to prefill GoalDetailForm
    class EditGoalApp(npyscreen.NPSAppManaged):
        def onStart(selfx):
            # Set kind for dynamic field logic
            selfx.goal_kind = goal.kind
            form = selfx.addForm("MAIN", GoalDetailForm, name="Edit Goal")

            # Prefill main fields
            form.title.value = goal.get("title", "")
            period_val = goal.get("period", "")
            if period_val in [p.value for p in form.period.values]:
                form.period.value = form.period.values.index(period_val)
            else:
                form.period.value = 0

            # Prefill all possible fields (only the relevant ones will be shown)
            form.amount.value = str(goal.get("amount") or "")
            form.unit.value = str(goal.get("unit") or "")
            form.min_amount.value = str(goal.get("min_amount") or "")
            form.max_amount.value = str(goal.get("max_amount") or "")
            form.mode.value = str(goal.get("mode") or "")
            form.target.value = str(goal.get("target") or "")
            form.current.value = str(goal.get("current") or "")
            form.target_streak.value = str(goal.get("target_streak") or "")
            form.target_percentage.value = str(
                goal.get("target_percentage") or "")
            form.current_percentage.value = str(
                goal.get("current_percentage") or "")
            form.old_behavior.value = str(goal.get("old_behavior") or "")
            form.new_behavior.value = str(goal.get("new_behavior") or "")

            form.display()

    # Launch form and collect result
    app = EditGoalApp()
    app.run()
    updated_data = getattr(app, 'form_data', None)
    if updated_data:
        # Overwrite goal in repo
        track_repository.update_goal(goal_id, updated_data)
        npyscreen.notify_confirm("Goal updated!", title="Updated")
    else:
        npyscreen.notify_confirm("No changes made.", title="Edit Goal")


def delete_goal_tui(stdscr, tracker_sel):
    trackers = track_repository.get_all_trackers()
    t = trackers[tracker_sel]
    goals = track_repository.get_goals_for_tracker(t.id)
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
            track_repository.delete_goal(g.id)
            popup_show(stdscr, ["Goal deleted"])
        except Exception as e:
            popup_show(stdscr, [f"Error deleting goal: {e}"])
            log_exception("delete_goal_tui", e)
