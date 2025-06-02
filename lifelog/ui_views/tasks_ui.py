# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------


import curses
from dataclasses import asdict
from datetime import datetime
from lifelog.commands.utils.db.models import Task, get_task_fields
from task_module import calculate_priority
from lifelog.commands.utils.db import task_repository, time_repository
from lifelog.commands.utils.shared_utils import add_category_to_config, add_project_to_config, add_tag_to_config, get_available_categories, get_available_projects, get_available_statuses, get_available_tags, validate_task_inputs
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_multiline_input, popup_select_option, popup_show


import calendar
import re
from datetime import datetime

from lifelog.ui_views.ui_helpers import log_exception, safe_addstr, tag_picker_tui


def draw_agenda(pane, h, w, selected_idx):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Agenda "
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)
        now = datetime.now()

        # --- CALENDAR PANEL ---
        cal = calendar.TextCalendar(firstweekday=0)
        month_lines = cal.formatmonth(now.year, now.month).splitlines()
        tasks = task_repository.query_tasks(
            show_completed=False, sort="priority")
        due_days = {
            datetime.fromisoformat(t["due"]).day
            for t in tasks if t.get("due")
            and datetime.fromisoformat(t["due"]).month == now.month
            and datetime.fromisoformat(t["due"]).year == now.year
        }
        calendar_pad_top = 2
        calendar_pad_left = 2
        for i, line in enumerate(month_lines):
            y = calendar_pad_top + i
            if y < max_h - 1 and len(line) < max_w - 2:
                for match in re.finditer(r'\b(\d{1,2})\b', line):
                    day = int(match.group(1))
                    x = calendar_pad_left + match.start()
                    if day == now.day:
                        safe_addstr(pane, y, x, f"{day:>2}", curses.A_REVERSE)
                    elif day in due_days:
                        safe_addstr(
                            pane, y, x, f"{day:>2}", curses.A_UNDERLINE)
                    else:
                        safe_addstr(pane, y, x, f"{day:>2}")
                # For non-numeric lines (month/year/header)
                if re.fullmatch(r"\D+", line.strip()):
                    safe_addstr(pane, y, calendar_pad_left, line[:max_w-4])
        cal_panel_height = calendar_pad_top + len(month_lines) + 1

        # --- TASK LIST ---
        tasks = task_repository.query_tasks(
            show_completed=False, sort="priority")
        n = len(tasks)
        visible_rows = max_h - cal_panel_height - 5
        if visible_rows < 1:
            visible_rows = 1

        safe_addstr(pane, cal_panel_height, 2, "Tasks:", curses.A_UNDERLINE)
        task_win_left = 2
        task_win_top = cal_panel_height + 1

        if n == 0:
            safe_addstr(pane, task_win_top, task_win_left,
                        "(no tasks)", curses.A_DIM)
        else:
            # Scroll logic for task list
            selected_idx = max(0, min(selected_idx, n-1))
            start = max(0, selected_idx - visible_rows // 2)
            end = min(start + visible_rows, n)
            # Draw box for scroll area
            for i in range(visible_rows):
                y = task_win_top + i
                if y < max_h - 2:
                    safe_addstr(pane, y, task_win_left, " " * (max_w//2-4))
            for i, t in enumerate(tasks[start:end], start=start):
                is_sel = (i == selected_idx)
                attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
                id_str = f"{t['id']:>2}"
                title = t.get("title", "-")
                line = f"{id_str}: {title}"
                y = task_win_top + i - start
                if y < max_h - 2:
                    safe_addstr(pane, y, task_win_left,
                                line[:max_w//2-8], attr)

            # --- TASK DETAIL PREVIEW (right side, if enough space) ---
            if max_w > 40:
                preview_left = max_w//2 + 2
                detail_y = cal_panel_height
                t = tasks[selected_idx]
                preview_lines = [
                    f"ID: {t['id']}",
                    f"Title: {t.get('title', '-')}",
                    f"Due: {t.get('due', '-')}",
                    f"Status: {t.get('status', '-')}",
                    f"Category: {t.get('category', '-')}",
                    f"Project: {t.get('project', '-')}",
                    f"Priority: {t.get('priority', '-')}",
                    f"Notes: {(t.get('notes', '-') or '-')[:max_w//2-6]}",
                ]
                for idx, line in enumerate(preview_lines):
                    if detail_y + idx < max_h - 2:
                        safe_addstr(pane, detail_y + idx, preview_left,
                                    line[:max_w//2-6])

        pane.noutrefresh()
        return selected_idx
    except Exception as e:
        log_exception("draw_agenda", e)
        max_h, _ = pane.getmaxyx()
        safe_addstr(pane, max_h-2, 2, f"Agenda err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        return 0


def popup_recurrence(stdscr):
    # Define prompts
    prompt = "Add recurrence rule?"
    options = "[y] Yes    [n] No"
    info_line = "Enter the interval to recur at. If you need specific weekdays, choose 'week'."
    input_prompt = "[(d)ay, (w)eek, (m)onth, (y)ear]: "

    # Calculate window size
    content_lines = [prompt, options, info_line, input_prompt]
    max_line = max(len(l) for l in content_lines)
    win_w = max(60, max_line + 4)
    win_h = 7
    h, w = stdscr.getmaxyx()
    starty = max((h - win_h) // 2, 0)
    startx = max((w - win_w) // 2, 0)

    win = curses.newwin(win_h, win_w, starty, startx)
    win.keypad(True)
    win.border()
    win.addstr(1, 2, prompt[:win_w-4], curses.A_BOLD)
    win.addstr(2, 2, options[:win_w-4])
    win.addstr(3, 2, info_line[:win_w-4])
    win.addstr(4, 2, input_prompt[:win_w-4])
    win.refresh()

    curses.echo()
    inp = ""
    while True:
        c = win.getch(4, 2 + len(input_prompt) + len(inp))
        if c in (10, 13):  # Enter
            break
        if c in (27,):  # ESC
            inp = ""
            break
        if c in (curses.KEY_BACKSPACE, 127, 8):
            if inp:
                inp = inp[:-1]
                win.addstr(4, 2 + len(input_prompt) + len(inp), ' ')
                win.move(4, 2 + len(input_prompt) + len(inp))
        elif 32 <= c <= 126 and len(inp) < win_w - len(input_prompt) - 4:
            inp += chr(c)
            win.addstr(4, 2 + len(input_prompt) + len(inp) - 1, chr(c))
        # Prevent typing past the window edge!
        win.refresh()

    curses.noecho()
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()
    return inp.strip() if inp else None


def add_task_tui(stdscr):
    """Prompt for all task fields using the dataclass model, with validation and dropdowns."""
    fields = get_task_fields()
    input_data = {}

    for field in fields:
        if field == "created":
            continue
        if field == "title":
            val = popup_input(stdscr, "Title (max 60 chars):", max_length=60)
        elif field == "category":
            val = popup_select_option(
                stdscr, "Category:", get_available_categories(), allow_new=True)
            if val and val not in get_available_categories():
                add_category_to_config(val)
        elif field == "project":
            val = popup_select_option(
                stdscr, "Project:", get_available_projects(), allow_new=True)
            if val and val not in get_available_projects():
                add_project_to_config(val)
        elif field == "status":
            val = popup_select_option(
                stdscr, "Status:", get_available_statuses())
        elif field == "priority":
            val = 0
        elif field == "tags":
            tag_list = tag_picker_tui(stdscr, get_available_tags())
            val = tag_list
            if val:
                for tag in (val.split(",") if isinstance(val, str) else val):
                    add_tag_to_config(tag)
        elif field == "notes":
            val = popup_multiline_input(stdscr, "Notes (multi-line allowed):")
        else:
            val = popup_input(stdscr, f"{field.capitalize()}:")
        input_data[field] = val if val else None

    input_data["created"] = datetime.now().isoformat()
    input_data["priority"] = calculate_priority(input_data)
    try:
        validate_task_inputs(
            title=input_data.get("title", ""),
            importance=int(input_data.get("importance")
                           or 0) if input_data.get("importance") else None,
            priority=float(input_data.get("priority")
                           or 0) if input_data.get("priority") else None,
        )
        task = Task(**input_data)
    except Exception as e:
        popup_show(stdscr, [f"Invalid input: {e}"])
        return
    task_repository.add_task(task)
    popup_show(stdscr, [f"Task '{task.title}' added!"])


def quick_add_task_tui(stdscr):
    """Add a task with just a title."""
    title = popup_input(stdscr, "Quick Task Title:", max_length=60)
    if not title:
        popup_show(stdscr, ["Title required."])
        return

    now = datetime.now().isoformat()
    task = Task(title=title, created=now)
    task_repository.add_task(task)
    popup_show(stdscr, [f"Quick Task '{title}' added!"])


def clone_task_tui(stdscr, sel):
    tasks = task_repository.get_all_tasks()
    t = tasks[sel]
    new_title = popup_input(stdscr, f"Clone Title [{t.title}]:") or t.title
    new_due = popup_input(stdscr, f"Due [{t.due or '-'}]:") or t.due
    now = datetime.now().isoformat()
    task_dict = asdict(t)
    task_dict["title"] = new_title
    task_dict["due"] = new_due
    task_dict["created"] = now
    task_dict.pop("id", None)
    try:
        task = Task(**task_dict)
        task_repository.add_task(task)
        popup_show(stdscr, [f"Task cloned as '{new_title}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


def focus_mode_tui(stdscr, sel):
    """
    Robust distraction-free focus mode for a task.
    - Locks keys so only pause or mark done will exit.
    - Shows total time spent.
    - Supports Pomodoro timer cycles.
    """
    import time
    from datetime import datetime
    from lifelog.commands.utils.db import time_repository

    # --- Get task
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]

    # --- Start timer if not running for this task
    active = time_repository.get_active_time_entry()
    if not (active and active.get("task_id") == t["id"]):
        time_repository.start_time_entry(
            title=t["title"],
            category=t.get("category"),
            project=t.get("project"),
            tags=t.get("tags"),
            notes=t.get("notes"),
            task_id=t["id"]
        )
        timer_started = True
    else:
        timer_started = False

    # --- Total time spent on task
    def get_total_task_time():
        logs = time_repository.get_all_time_logs()
        return int(sum(e['duration_minutes'] for e in logs if e.get('task_id') == t['id'] and e.get('duration_minutes')))

    # --- Pomodoro settings
    pomodoro_mode = False
    pomo_length = 25 * 60  # 25min focus
    break_length = 5 * 60  # 5min break
    in_break = False

    session_start = time.time()
    session_mode_start = session_start
    stdscr.nodelay(True)  # Non-blocking input

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        elapsed = int(time.time() - session_mode_start)
        mins, secs = divmod(elapsed, 60)

        # Display total task time (accumulated, plus current if timer running)
        total_minutes = get_total_task_time()
        # Add current session time if active and running for this task
        active = time_repository.get_active_time_entry()
        if active and active.get("task_id") == t["id"] and active.get("start"):
            dt_start = datetime.fromisoformat(active["start"])
            now = datetime.now()
            total_minutes += int((now - dt_start).total_seconds() // 60)

        timer_str = f"{mins:02}:{secs:02}"
        lines = [
            "FOCUS MODE - Pomodoro ON" if pomodoro_mode else "FOCUS MODE",
            "",
            f"Title: {t['title']}",
            f"Project: {t.get('project', '-')}",
            f"Category: {t.get('category', '-')}",
            f"Due: {t.get('due', '-')}",
            f"Total time: {total_minutes} min",
            f"Session: [{timer_str}]",
            "",
        ]
        if pomodoro_mode:
            lines.append("Work" if not in_break else "Break")
            if not in_break:
                lines.append(
                    "Press 'P' to toggle Pomodoro, 'p' to pause, 'd' to mark done.")
            else:
                lines.append("Break! Press any key to resume work.")
        else:
            lines.append(
                "Press 'P' for Pomodoro, 'p' to pause, 'd' to mark done.")

        lines.append("You must pause or complete the task to exit focus mode.")

        for idx, line in enumerate(lines):
            stdscr.addstr(h//2 - len(lines)//2 + idx,
                          max(2, (w - len(line))//2), line)

        stdscr.refresh()
        c = stdscr.getch()
        if c == ord("p"):
            stop_task_tui(stdscr)
            break
        if c == ord("d"):
            done_task_tui(stdscr, sel)
            break
        if c == ord("P"):
            pomodoro_mode = not pomodoro_mode
            in_break = False
            session_mode_start = time.time()
            continue
        if c in (ord("q"), 27):  # Try to quit: prompt instead

            popup_show(stdscr, [
                "You must pause ('p') or mark done ('d') to exit focus mode.",
                "Pomodoro: 'P' to toggle, stay focused!"
            ])
            continue

        if pomodoro_mode:
            if not in_break and elapsed >= pomo_length:

                popup_show(stdscr, ["Pomodoro complete! Break time."])
                in_break = True
                session_mode_start = time.time()
            elif in_break and elapsed >= break_length:

                popup_show(stdscr, ["Break over! Back to focus."])
                in_break = False
                session_mode_start = time.time()

        time.sleep(1)

    stdscr.nodelay(False)


def set_task_reminder_tui(stdscr, sel):
    """
    Set a custom reminder for a task via popup (like CLI).
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    if not t.get("due"):
        popup_show(stdscr, ["Task must have a due date!"])
        return

    reminder_str = popup_input(
        stdscr, "How long before due for reminder? (e.g. 1d, 120):")
    try:
        from task_module import create_due_alert
        create_due_alert(t)
        popup_show(stdscr, ["Reminder set!"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("reminder_task_tui", e)


def delete_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    # ── Guard: no tasks to delete
    if not tasks:
        return popup_show(stdscr, ["No tasks to delete"])
    # ── Guard: sel out of range
    if sel < 0 or sel >= len(tasks):
        return popup_show(stdscr, ["No task selected"])

    tid = tasks[sel]["id"]
    if popup_confirm(stdscr, f"Delete task #{tid}?"):
        try:
            task_repository.delete_task(tid)
            popup_show(stdscr, [f"Deleted task #{tid}"])
        except Exception as e:
            popup_show(stdscr, [f"Error: {e}"])
            log_exception("delete_task_tui", e)


def edit_task_tui(stdscr, sel):
    """Edit ALL fields of the selected task using the model."""
    tasks = task_repository.get_all_tasks()
    t = tasks[sel]
    fields = get_task_fields()
    input_data = {}
    for field in fields:
        if field == "created":
            input_data[field] = t.created.isoformat() if t.created else None
            continue
        old_val = getattr(t, field, None) or ""
        if field == "category":
            val = popup_select_option(
                stdscr, f"Category [{old_val}]:", get_available_categories(), allow_new=True)
            if val and val not in get_available_categories():
                add_category_to_config(val)
        elif field == "project":
            val = popup_select_option(
                stdscr, f"Project [{old_val}]:", get_available_projects(), allow_new=True)
            if val and val not in get_available_projects():
                add_project_to_config(val)
        elif field == "status":
            val = popup_select_option(
                stdscr, f"Status [{old_val}]:", get_available_statuses())
        elif field == "tags":
            tag_list = tag_picker_tui(stdscr, get_available_tags())
            val = tag_list
            if val:
                for tag in (val.split(",") if isinstance(val, str) else val):
                    add_tag_to_config(tag)
        elif field == "notes":
            val = popup_multiline_input(
                stdscr, f"Notes [{old_val[:20]}...]:", initial=old_val)
        else:
            val = popup_input(stdscr, f"{field.capitalize()} [{old_val}]:")
        input_data[field] = val if val else old_val

        input_data["priority"] = calculate_priority(input_data)
    try:
        task = Task(**input_data)
        task_repository.update_task(t.id, asdict(task))
        popup_show(stdscr, [f"Task #{t.id} updated!"])
    except Exception as e:
        popup_show(stdscr, [f"Error updating task: {e}"])


def edit_recurrence_tui(stdscr, sel):
    """
    Prompts the user to view and edit recurrence settings for the selected task.
    Allows creating, updating, or clearing the recurrence rule.
    User can press ESC at any prompt to cancel editing (no changes saved).
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]

    # Get current recurrence or defaults
    rec = t.get("recurrence") or {}
    everyX = rec.get("everyX", "")
    unit = rec.get("unit", "")
    daysOfWeek = rec.get("daysOfWeek", [])
    onFirstOfMonth = rec.get("onFirstOfMonth", False)

    # Display current
    lines = [
        f"Current Recurrence:",
        f"  Every X:       {everyX or '-'}",
        f"  Unit:          {unit or '-'}",
        f"  DaysOfWeek:    {','.join(map(str, daysOfWeek)) or '-'}",
        f"  First of Month:{'Yes' if onFirstOfMonth else 'No'}"
    ]
    popup_show(stdscr, lines, title=" Edit Recurrence ")

    # Prompt new values, ESC = abort
    new_everyX = popup_input(stdscr, f"Every X [{everyX or ''}]:")
    if new_everyX is None:
        popup_show(stdscr, ["Edit cancelled."])
        return

    new_unit = popup_input(stdscr, f"Unit (days/weeks/months) [{unit or ''}]:")
    if new_unit is None:
        popup_show(stdscr, ["Edit cancelled."])
        return

    new_days = popup_input(
        stdscr, f"DaysOfWeek (0-6, comma list) [{','.join(map(str, daysOfWeek)) or ''}]:")
    if new_days is None:
        popup_show(stdscr, ["Edit cancelled."])
        return

    new_first = popup_input(
        stdscr, f"First of Month? (y/n) [{'y' if onFirstOfMonth else 'n'}]:")
    if new_first is None:
        popup_show(stdscr, ["Edit cancelled."])
        return

    # Build new recurrence dict
    updates = {}
    try:
        if new_everyX.strip():
            updates["everyX"] = int(new_everyX.strip())
        elif everyX:
            updates["everyX"] = everyX

        if new_unit.strip():
            updates["unit"] = new_unit.strip()
        elif unit:
            updates["unit"] = unit

        if new_days.strip():
            updates["daysOfWeek"] = [int(d)
                                     for d in new_days.strip().split(",") if d]
        elif daysOfWeek:
            updates["daysOfWeek"] = daysOfWeek

        if new_first.strip().lower() in ("y", "yes", "1"):
            updates["onFirstOfMonth"] = True
        elif new_first.strip().lower() in ("n", "no", "0"):
            updates["onFirstOfMonth"] = False
        else:
            updates["onFirstOfMonth"] = onFirstOfMonth

        # If user leaves all fields blank, clear recurrence
        if not any(str(v).strip() for v in updates.values()):
            confirm = popup_confirm(stdscr, "Clear recurrence?")
            if confirm:
                updates = None
    except Exception as e:
        popup_show(stdscr, [f"Invalid recurrence: {e}"])
        log_exception("edit_recur_tui", e)
        return

    # Save update
    try:
        if updates is not None:
            task_repository.update_task(t["id"], {"recurrence": updates})
            popup_show(stdscr, ["Recurrence updated"])
        else:
            task_repository.update_task(t["id"], {"recurrence": None})
            popup_show(stdscr, ["Recurrence cleared"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


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
        popup_show(stdscr, ["Notes updated"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("edit_task_notes_tui", e)


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
    tasks = task_repository.get_all_tasks()
    t = tasks[sel]
    fields = get_task_fields()
    display_lines = [
        f"{field.capitalize()}: {getattr(t, field) or '-'}" for field in fields]
    popup_show(stdscr, display_lines, title=" Task Details ")


def start_task_tui(stdscr, sel):
    """
    Starts timing the selected task, allowing user to review and update relevant fields.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]

    # Prompt to optionally update tags/notes before starting
    new_tags = popup_input(
        stdscr, f"Tags [{t.get('tags') or ''}]:") or t.get("tags")
    new_notes = popup_input(
        stdscr, f"Notes [{t.get('notes') or ''}]:") or t.get("notes")

    updates = {}
    if new_tags is not None:
        updates["tags"] = new_tags
    if new_notes is not None:
        updates["notes"] = new_notes

    # Mark task as active and set start time
    now_iso = datetime.now().isoformat()
    updates["status"] = "active"
    updates["start"] = now_iso

    # Update task in repository
    try:
        task_repository.update_task(t["id"], updates)
        time_repository.start_time_entry(
            title=t["title"],
            task_id=t["id"],
            start_time=now_iso,
            category=t.get("category"),
            project=t.get("project"),
            tags=new_tags,
            notes=new_notes,
        )
        popup_show(stdscr, [f"Started '{t['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("start_task_tui", e)


def stop_task_tui(stdscr):
    """
    Stops the current active task and time entry, optionally letting user add notes/tags.
    """
    active = time_repository.get_active_time_entry()
    if not active or not active.get("task_id"):
        popup_show(stdscr, ["No active task"])
        return

    tid = active["task_id"]
    task = task_repository.get_task_by_id(tid)
    if not task:
        popup_show(stdscr, ["Active task not found"])
        return

    # Prompt user to update tags/notes on stop
    new_tags = popup_input(
        stdscr, f"Tags [{task.get('tags') or ''}]:") or task.get("tags")
    new_notes = popup_input(
        stdscr, f"Notes [{task.get('notes') or ''}]:") or task.get("notes")

    updates = {}
    if new_tags is not None:
        updates["tags"] = new_tags
    if new_notes is not None:
        updates["notes"] = new_notes
    updates["status"] = "backlog"

    now_iso = datetime.now().isoformat()

    try:
        # Stop timing
        time_repository.stop_active_time_entry(end_time=now_iso)
        # Update the task fields
        task_repository.update_task(tid, updates)
        popup_show(stdscr, [f"Paused '{task['title']}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("stop_task_tui", e)


def done_task_tui(stdscr, sel):
    """
    Marks the selected task as done, prompts for tags/notes, stops timing if running.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]

    # Prompt to update tags/notes on completion
    new_tags = popup_input(
        stdscr, f"Tags [{t.get('tags') or ''}]:") or t.get("tags")
    new_notes = popup_input(
        stdscr, f"Notes [{t.get('notes') or ''}]:") or t.get("notes")

    updates = {
        "tags": new_tags,
        "notes": new_notes,
        "status": "done",
        "end": datetime.now().isoformat(),
    }

    try:
        # Stop time entry if this task is active
        active = time_repository.get_active_time_entry()
        if active and active.get("task_id") == t["id"]:
            time_repository.stop_active_time_entry(end_time=updates["end"])
        # Update the task
        task_repository.update_task(t["id"], updates)
        popup_show(stdscr, [f"Task '{t['title']}' marked done"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("done_task_tui", e)
