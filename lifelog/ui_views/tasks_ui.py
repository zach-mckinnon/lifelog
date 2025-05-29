# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------


import calendar
import curses
from datetime import datetime
from lifelog.commands.task import calculate_priority
from lifelog.commands.utils.db import task_repository, time_repository
from lifelog.commands.utils.shared_utils import create_recur_schedule, parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_show


def draw_agenda(pane, h, w, selected_idx):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Tasks "
        pane.addstr(0, max((max_w - len(title)) // 2, 1), title, curses.A_BOLD)
        tasks = task_repository.query_tasks(sort="priority")
        n = len(tasks)
        if n == 0:
            pane.addstr(2, 2, "(no tasks)", curses.A_DIM)
            pane.noutrefresh()
            return 0

        selected_idx = max(0, min(selected_idx, n-1))
        visible_rows = max_h - 3  # 1 for border, 1 for title, 1 for bottom border

        start = max(0, selected_idx - visible_rows // 2)
        end = min(start + visible_rows, n)

        for i, t in enumerate(tasks[start:end], start=start):
            is_sel = (i == selected_idx)
            attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
            due = t.get("due") or ""
            due_str = due.split("T")[0] if due else "-"
            recur = " [R]" if t.get("recur_interval") else ""
            line = f"{t['id']:>2} [{t['priority']}] {due_str} {t['title']}{recur}"
            y = 1 + i - start + 1  # 1 for border, 1 for title
            if y < max_h - 1:
                pane.addstr(y, 2, line[:max_w-4], attr)

        pane.noutrefresh()
        return selected_idx

    except Exception as e:
        pane.addstr(max_h-2, 2, f"Agenda err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        return 0


def add_task_tui(stdscr):
    """
    Prompt for all task fields, compute priority, and save.
    """
    # 1) Title
    title = popup_input(stdscr, "Title:")
    if not title:
        return

    # 2) Category & Project
    category = popup_input(stdscr, "Category [optional]:") or None
    project = popup_input(stdscr, "Project  [optional]:") or None

    # 3) Importance
    impt_str = popup_input(stdscr, "Importance (1–5) [default 1]:")
    impt = int(impt_str) if impt_str.isdigit() else 1

    # 4) Due date
    due_str = popup_input(
        stdscr, "Due (e.g. 'tomorrow' or '2025-12-31') [optional]:")
    due_iso = None
    if due_str:
        try:
            due_iso = parse_date_string(due_str).isoformat()
        except Exception as e:
            popup_show(stdscr, [f"Invalid due date: {e}"])
            return

    # 5) Recurrence
    recur_interval = recur_unit = recur_days = recur_base = None
    if popup_confirm(stdscr, "Add recurrence rule?"):
        try:
            recur_data = create_recur_schedule("interactive")
            recur_interval = recur_data["interval"]
            recur_unit = recur_data["unit"]
            recur_days = recur_data.get("days_of_week") or None
            recur_base = datetime.now().isoformat()
        except Exception as e:
            popup_show(stdscr, [f"Recurrence setup failed: {e}"])
            return

    # 6) Tags & Notes
    tags = popup_input(stdscr, "Tags (comma-separated) [opt]:") or None
    notes = popup_input(stdscr, "Notes [optional]:") or None

    # 7) Build task_data and compute priority
    now = datetime.now().isoformat()
    task_data = {
        "title":            title,
        "category":         category,
        "project":          project,
        "impt":             impt,
        "created":          now,
        "due":              due_iso,
        "status":           "backlog",
        "start":            None,
        "end":              None,
        "priority":         0,  # will be overwritten
        "recur_interval":   recur_interval,
        "recur_unit":       recur_unit,
        "recur_days_of_week": recur_days,
        "recur_base":       recur_base,
        "tags":             tags,
        "notes":            notes,
    }
    # compute final priority
    task_data["priority"] = calculate_priority(task_data)

    # 8) Save
    try:
        task_repository.add_task(task_data)
        popup_show(stdscr, [f"Task '{title}' added"])
    except Exception as e:
        popup_show(stdscr, [f"Error saving task: {e}"])


def quick_add_task_tui(stdscr):
    """
    Add a new task with minimal fields: title (required) and optional category.
    """
    title = popup_input(stdscr, "Quick Task Title:")
    if not title:
        popup_show(stdscr, ["Title required."])
        return

    category = popup_input(stdscr, "Category [optional]:") or None

    now = datetime.now().isoformat()
    task_data = {
        "title": title,
        "category": category,
        "created": now,
        "status": "backlog",
        "priority": 1,
        "impt": 1,
        "project": None,
        "due": None,
        "recur_interval": None,
        "recur_unit": None,
        "recur_days_of_week": None,
        "recur_base": None,
        "tags": None,
        "notes": None,
        "start": None,
        "end": None,
    }
    task_data["priority"] = calculate_priority(task_data)
    try:
        task_repository.add_task(task_data)
        popup_show(stdscr, [f"Quick Task '{title}' added"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


def clone_task_tui(stdscr, sel):
    """
    Clone the selected task, prompting for new title/due.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected to clone"])
        return
    t = tasks[sel]
    new_title = popup_input(
        stdscr, f"Clone Title [{t['title']}] :") or t["title"]
    new_due = popup_input(
        stdscr, f"Due [{t.get('due') or '-'}] :") or t.get("due")
    now = datetime.now().isoformat()

    task_data = {**t}
    task_data.update({
        "title": new_title,
        "due": parse_date_string(new_due).isoformat() if new_due else None,
        "created": now,
        "status": "backlog",
        "start": None,
        "end": None,
    })
    # Remove the original id if present
    task_data.pop("id", None)
    task_data["priority"] = calculate_priority(task_data)

    try:
        task_repository.add_task(task_data)
        popup_show(stdscr, [f"Task cloned as '{new_title}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


def focus_mode_tui(stdscr, sel):
    """
    Distraction-free fullscreen mode for working on a task.
    Shows task info and a large timer.
    """
    import time

    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    start_time = datetime.now()
    stdscr.clear()
    stdscr.nodelay(True)  # non-blocking input

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        elapsed = (datetime.now() - start_time).seconds
        mins, secs = divmod(elapsed, 60)
        timer = f"{mins:02}:{secs:02}"

        # Task Info
        lines = [
            f"FOCUS MODE",
            "",
            f"Title: {t['title']}",
            f"Project: {t.get('project', '-')}",
            f"Category: {t.get('category', '-')}",
            f"Due: {t.get('due', '-')}",
            f"",
            f"[{timer}]",
            "",
            "Press 'p' to pause, 'd' to mark done, or 'q' to exit focus."
        ]
        for idx, line in enumerate(lines):
            stdscr.addstr(h//2 - len(lines)//2 + idx, (w - len(line))//2, line)

        stdscr.refresh()
        c = stdscr.getch()
        if c == ord("p"):
            stop_task_tui(stdscr)
            break
        if c == ord("d"):
            done_task_tui(stdscr, sel)
            break
        if c == ord("q"):
            break
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
        from lifelog.commands.task import create_due_alert
        create_due_alert(t)
        popup_show(stdscr, ["Reminder set!"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


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


def edit_task_tui(stdscr, sel):
    """
    Edit ALL fields of the selected task.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    # Prompt for all fields, with current value as default
    new_title = popup_input(stdscr, f"Title [{t['title']}]:") or t["title"]
    new_due = popup_input(
        stdscr, f"Due [{t.get('due') or '-'}]:") or t.get("due")
    new_cat = popup_input(
        stdscr, f"Category [{t.get('category') or '-'}]:") or t.get("category")
    new_prj = popup_input(
        stdscr, f"Project [{t.get('project') or '-'}]:") or t.get("project")
    new_impt = popup_input(stdscr, f"Importance [{t.get('impt', 1)}]:")
    new_tags = popup_input(
        stdscr, f"Tags [{t.get('tags') or ''}]:") or t.get("tags")
    new_notes = popup_input(
        stdscr, f"Notes [{t.get('notes') or ''}]:") or t.get("notes")

    # Optional: Edit recurrence interactively
    if popup_confirm(stdscr, "Edit recurrence?"):
        try:
            recur_data = create_recur_schedule("interactive")
            recur_interval = recur_data["interval"]
            recur_unit = recur_data["unit"]
            recur_days = recur_data.get("days_of_week") or None
            recur_base = datetime.now().isoformat()
        except Exception as e:
            popup_show(stdscr, [f"Recurrence setup failed: {e}"])
            return
    else:
        recur_interval = t.get("recur_interval")
        recur_unit = t.get("recur_unit")
        recur_days = t.get("recur_days_of_week")
        recur_base = t.get("recur_base")

    updates = {
        "title": new_title,
        "due": parse_date_string(new_due).isoformat() if new_due else None,
        "category": new_cat,
        "project": new_prj,
        "impt": int(new_impt) if new_impt and new_impt.isdigit() else t.get("impt", 1),
        "tags": new_tags,
        "notes": new_notes,
        "recur_interval": recur_interval,
        "recur_unit": recur_unit,
        "recur_days_of_week": recur_days,
        "recur_base": recur_base,
    }
    # Priority recalculation
    updates["priority"] = calculate_priority({**t, **updates})
    try:
        task_repository.update_task(t["id"], updates)
        popup_show(stdscr, [f"Updated #{t['id']}"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


def edit_recurrence_tui(stdscr, sel):
    """
    Prompts the user to view and edit recurrence settings for the selected task.
    Allows creating, updating, or clearing the recurrence rule.
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

    # Prompt new values
    new_everyX = popup_input(stdscr, f"Every X [{everyX or ''}]:")
    new_unit = popup_input(stdscr, f"Unit (days/weeks/months) [{unit or ''}]:")
    new_days = popup_input(
        stdscr, f"DaysOfWeek (0-6, comma list) [{','.join(map(str, daysOfWeek)) or ''}]:")
    new_first = popup_input(
        stdscr, f"First of Month? (y/n) [{'y' if onFirstOfMonth else 'n'}]:")

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
        if not any(updates.values()):
            confirm = popup_confirm(stdscr, "Clear recurrence?")
            if confirm:
                updates = None
    except Exception as e:
        popup_show(stdscr, [f"Invalid recurrence: {e}"])
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
    """
    Display all details of a selected task.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    fields = [
        f"Title: {t.get('title') or '-'}",
        f"Category: {t.get('category') or '-'}",
        f"Project: {t.get('project') or '-'}",
        f"Importance: {t.get('impt') or '-'}",
        f"Priority: {t.get('priority') or '-'}",
        f"Due: {t.get('due') or '-'}",
        f"Status: {t.get('status') or '-'}",
        f"Recurrence: {t.get('recur_interval') or '-'} {t.get('recur_unit') or ''} {t.get('recur_days_of_week') or ''}",
        f"Tags: {t.get('tags') or '-'}",
        f"Notes: {t.get('notes') or '-'}",
        f"Created: {t.get('created') or '-'}",
        f"Start: {t.get('start') or '-'}",
        f"End: {t.get('end') or '-'}",
    ]
    popup_show(stdscr, fields, title=" Task Details ")


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
