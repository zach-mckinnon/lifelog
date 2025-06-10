# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------
import time
import npyscreen
import curses
from dataclasses import asdict
from datetime import datetime
from lifelog.utils.db.models import Task
from lifelog.commands.task_module import calculate_priority, create_due_alert
from lifelog.utils.db import task_repository, time_repository
from lifelog.ui_views.popups import popup_confirm, popup_error, popup_input, popup_multiline_input, popup_show
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr
from lifelog.commands.task_module import calculate_priority
from lifelog.utils.db.models import Task

import calendar
import re
from datetime import datetime

from lifelog.ui_views.forms import TaskCloneForm, TaskEditForm, TaskForm, TaskViewForm, run_form
from lifelog.utils.hooks import build_payload, run_hooks


# Module‐level state for task filter:
TASK_FILTERS = ["backlog", "active", "done"]
current_filter_idx = 0


def draw_agenda(pane, h, w, selected_idx):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Tasks "
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)
        now = datetime.now()

        # --- CALENDAR PANEL ---
        cal = calendar.TextCalendar(firstweekday=0)
        month_lines = cal.formatmonth(now.year, now.month).splitlines()
        tasks = task_repository.query_tasks(
            show_completed=False, sort="priority")
        due_days = set()
        for t in tasks:
            due_val = getattr(t, "due", None)
            if due_val:
                # If due_val is datetime, use it directly; if string, parse:
                if isinstance(due_val, datetime):
                    due_dt = due_val
                else:
                    try:
                        due_dt = datetime.fromisoformat(due_val)
                    except Exception:
                        continue
                # Only include days in this month/year
                if due_dt.year == now.year and due_dt.month == now.month:
                    due_days.add(due_dt.day)
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
                id_val = getattr(t, "id", None)
                id_str = f"{id_val:>2}" if id_val is not None else " -"
                title_str = t.title if t.title else "-"
                line = f"{id_str}: {title_str}"
                y = task_win_top + i - start
                if y < max_h - 2:
                    safe_addstr(pane, y, task_win_left,
                                line[:max_w//2-8], attr)

            # --- TASK DETAIL PREVIEW (right side, if enough space) ---
            if max_w > 40:
                preview_left = max_w//2 + 2
                detail_y = cal_panel_height
                t = tasks[selected_idx]
                # ID
                id_val = getattr(t, "id", None)
                line_id = f"ID: {id_val}" if id_val is not None else "ID: -"
                # Title
                title_val = t.title or "-"
                line_title = f"Title: {title_val}"
                # Due: display ISO string or formatted date
                due_val = getattr(t, "due", None)
                if isinstance(due_val, datetime):
                    due_str = due_val.isoformat()
                elif due_val:
                    try:
                        due_str = datetime.fromisoformat(due_val).isoformat()
                    except Exception:
                        due_str = str(due_val)
                else:
                    due_str = "-"
                line_due = f"Due: {due_str}"
                # Status: TaskStatus enum -> .value
                status_val = getattr(t, "status", None)
                if hasattr(status_val, "value"):
                    status_str = status_val.value
                else:
                    status_str = str(status_val) if status_val else "-"
                line_status = f"Status: {status_str}"
                # Category
                cat_str = t.category or "-"
                line_cat = f"Category: {cat_str}"
                # Project
                proj_str = t.project or "-"
                line_proj = f"Project: {proj_str}"
                # Priority
                prio_val = getattr(t, "priority", None)
                prio_str = str(prio_val) if prio_val is not None else "-"
                line_prio = f"Priority: {prio_str}"
                # Notes: take substring
                notes_val = t.notes or "-"
                notes_display = notes_val[:max_w//2 - 6]
                line_notes = f"Notes: {notes_display or '-'}"

                preview_lines = [
                    line_id,
                    line_title,
                    line_due,
                    line_status,
                    line_cat,
                    line_proj,
                    line_prio,
                    line_notes,
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


# --- Main Add Task using Form ---
def add_task_tui(_stdscr=None):
    """Launch TaskForm to add a new task (all fields, recurrence, etc)."""
    task_data = run_form(TaskForm)
    if not task_data:
        return  # User cancelled

    try:
        # Add mandatory fields
        task_data.setdefault('created', datetime.now().isoformat())
        task_data.setdefault('status', 'backlog')
        task_data.setdefault('importance', 3)

        # Calculate priority like CLI
        task_data["priority"] = calculate_priority(task_data)

        # Create and save task
        task = Task(**task_data)
        task_repository.add_task(task)

        # Run hooks like CLI
        run_hooks("task", "created", task)

        npyscreen.notify_confirm(
            f"Task '{task.title}' added!", title="Success")
    except Exception as e:
        npyscreen.notify_confirm(str(e), title="Error")

# --- Quick Add Task (keep popup for simplicity, but handle errors nicely) ---


def quick_add_task_tui(stdscr):
    try:
        title = popup_input(
            stdscr, "Quick Task Title (required):", max_length=60, required=True)
        if not title:
            popup_error(stdscr, "A task title is required.")
            return

        # Add default values like CLI does
        now = datetime.now().isoformat()
        task_data = {
            "title": title,
            "created": now,
            "status": "backlog",
            "importance": 3,  # Default importance
            "priority": 0  # Will be calculated
        }

        # Calculate priority like CLI
        task_data["priority"] = calculate_priority(task_data)

        # Create and save task
        task = Task(**task_data)
        task_repository.add_task(task)

        # Run hooks like CLI
        run_hooks("task", "created", task)

        popup_show(stdscr, [f"Quick Task '{title}' added!"], title="Success")
    except Exception as e:
        popup_error(stdscr, f"Could not add task: {e}")

# --- Batch Add Tasks (multiline popup) ---


def batch_add_tasks_tui(stdscr):
    try:
        tasks_text = popup_multiline_input(
            stdscr,
            "Batch Add Tasks (One per line, Ctrl+D to finish):",
            initial="",
            max_lines=10
        )
        if not tasks_text:
            popup_show(stdscr, ["No tasks entered."], title="Batch Add")
            return
        lines = [l.strip() for l in tasks_text.splitlines() if l.strip()]
        if not lines:
            popup_show(stdscr, ["No valid tasks entered."], title="Batch Add")
            return
        count = 0
        for line in lines:
            now = datetime.now().isoformat()
            task = Task(title=line, created=now)
            task_data = {
                "title": line,
                "created": now,
                "status": "backlog",
                "importance": 3,
                "priority": calculate_priority({"importance": 3})
            }
            try:
                task_repository.add_task(task)
                count += 1
            except Exception as e:
                popup_error(stdscr, f"Could not add '{line}': {e}")
        popup_show(stdscr, [f"Added {count} tasks!"],
                   title="Batch Add Complete")
    except Exception as e:
        popup_error(stdscr, f"Batch add failed: {e}")

# --- Clone Task with Form ---


def clone_task_tui(_stdscr, sel):
    tasks = task_repository.get_all_tasks()
    t = tasks[sel]
    # Use the modular TaskCloneForm, pre-filling values:

    class App(npyscreen.NPSAppManaged):
        def onStart(selfx):
            form = selfx.addForm("MAIN", TaskCloneForm, name="Clone Task")
            form.title.value = t.title
            form.category.value = t.category
            form.project.value = t.project
            form.due.value = t.due if t.due else ""
            if hasattr(form.notes, "values"):
                form.notes.values = t.notes.splitlines() if t.notes else [""]
            else:
                form.notes.value = t.notes or ""
            form.tags.value = t.tags or ""
            rec = t.recurrence or {}
            if rec and rec.get("repeat"):
                form.recur_enabled.value = [1]
                form.recur_everyX.value = str(rec.get("everyX", 1))
                form.recur_unit.value = rec.get("unit", "day")
                form.recur_days.value = ",".join(
                    str(d) for d in rec.get("daysOfWeek", []))
                form.recur_first_of_month.value = [
                    1] if rec.get("onFirstOfMonth") else [0]
            else:
                form.recur_enabled.value = [0]
    app = App()
    app.run()
    task_data = getattr(app, 'form_data', None)
    if not task_data:
        return
    now = datetime.now().isoformat()
    # Do NOT clone start/stop/time-tracking fields!
    task = Task(**{**task_data, "created": now,
                "priority": calculate_priority(task_data), "status": "backlog"})
    task_repository.add_task(task)
    npyscreen.notify_confirm(f"Task cloned as '{task.title}'", title="Cloned")

# --- Edit Task with Form ---


def edit_task_tui(_stdscr, sel):
    tasks = task_repository.get_all_tasks()
    t = tasks[sel]
    # Use modular TaskEditForm, pre-filling

    class App(npyscreen.NPSAppManaged):
        def onStart(selfx):
            form = selfx.addForm("MAIN", TaskEditForm, name="Edit Task")
            form.title.value = t.title
            form.category.value = t.category
            form.project.value = t.project
            form.due.value = t.due if t.due else ""
            if hasattr(form.notes, "values"):
                form.notes.values = t.notes.splitlines() if t.notes else [""]
            else:
                form.notes.value = t.notes or ""
            form.tags.value = t.tags or ""
            rec = t.recurrence or {}
            if rec and rec.get("repeat"):
                form.recur_enabled.value = [1]
                form.recur_everyX.value = str(rec.get("everyX", 1))
                form.recur_unit.value = rec.get("unit", "day")
                form.recur_days.value = ",".join(
                    str(d) for d in rec.get("daysOfWeek", []))
                form.recur_first_of_month.value = [
                    1] if rec.get("onFirstOfMonth") else [0]
            else:
                form.recur_enabled.value = [0]
    app = App()
    app.run()
    task_data = getattr(app, 'form_data', None)
    if not task_data:
        return
    task = Task(**{**asdict(t), **task_data})
    task_repository.update_task(t.id, asdict(task))
    run_hooks("task", "updated", task)
    npyscreen.notify_confirm(f"Task #{t.id} updated!", title="Updated")

# --- View Task with Form (read-only) ---


def view_task_tui(_stdscr, sel):
    tasks = task_repository.get_all_tasks()
    t = tasks[sel]

    class App(npyscreen.NPSAppManaged):
        def onStart(selfx):
            form = selfx.addForm("MAIN", TaskViewForm, name="View Task")
            form.title.value = t.title
            form.category.value = t.category
            form.project.value = t.project
            form.due.value = t.due if t.due else ""
            if hasattr(form.notes, "values"):
                form.notes.values = t.notes.splitlines() if t.notes else [""]
            else:
                form.notes.value = t.notes or ""
            form.tags.value = t.tags or ""
            rec = t.recurrence or {}
            if rec and rec.get("repeat"):
                form.recur_enabled.value = [1]
                form.recur_everyX.value = str(rec.get("everyX", 1))
                form.recur_unit.value = rec.get("unit", "day")
                form.recur_days.value = ",".join(
                    str(d) for d in rec.get("daysOfWeek", []))
                form.recur_first_of_month.value = [
                    1] if rec.get("onFirstOfMonth") else [0]
            else:
                form.recur_enabled.value = [0]
            # Make all fields readonly:
            for f in (form.title, form.category, form.project, form.due, form.notes, form.tags,
                      form.recur_enabled, form.recur_everyX, form.recur_unit, form.recur_days, form.recur_first_of_month):
                f.editable = False
    app = App()
    app.run()


def countdown_timer_ui(stdscr, total_seconds, title="Focus Session"):
    """
    Show a countdown timer in a centered window for total_seconds.
    Returns True if completed normally, False if aborted by user keypress.
    """
    # Compute window size: e.g., height 5 lines, width enough for title and timer
    h, w = stdscr.getmaxyx()
    win_h = 5
    win_w = max(len(title) + 4, 20)
    # Center position
    start_y = max(0, (h - win_h) // 2)
    start_x = max(0, (w - win_w) // 2)
    # Create a new window
    win = curses.newwin(win_h, win_w, start_y, start_x)
    win.border()

    # Title line
    try:
        win.addstr(0, max(1, (win_w - len(title))//2), title, curses.A_BOLD)
    except curses.error:
        pass

    # Set nodelay to allow checking for keypress without blocking
    stdscr.nodelay(True)
    win.nodelay(True)

    remaining = total_seconds
    completed = True

    while remaining >= 0:
        # Compute MM:SS
        mins, secs = divmod(remaining, 60)
        timer_str = f"{mins:02d}:{secs:02d}"
        # Clear the line in the window and display timer
        try:
            # Place at center of window
            win.addstr(2, max(1, (win_w - len(timer_str))//2), timer_str)
        except curses.error:
            pass
        win.refresh()

        # Wait up to 1 second, checking for keypress
        start = time.time()
        while time.time() - start < 1:
            c = stdscr.getch()
            if c != -1:
                # If user presses 'p' or 'q', abort early
                # You can refine: e.g., 'p' to pause, 'q' to quit session
                if c in (ord('q'), ord('p')):
                    completed = False
                    break
            time.sleep(0.1)  # small sleep to avoid busy loop
        if not completed:
            break
        remaining -= 1

    # Clean up: restore blocking mode
    stdscr.nodelay(False)
    win.clear()
    win.refresh()
    del win
    return completed


def focus_mode_tui(stdscr, sel):
    """
    Robust distraction-free focus mode for a task.
    - Locks keys so only pause or mark done will exit.
    - Shows total time spent.
    - Supports Pomodoro timer cycles.
    """
    import time
    from datetime import datetime
    from lifelog.utils.db import time_repository

    # --- Get task
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    # Guard: sel in range
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # --- Start timer if not running for this task
    active = time_repository.get_active_time_entry()
    # Compare dict active["task_id"] with t.id
    if not (active and active.get("task_id") == t.id):
        # Start a new time entry for this task
        time_repository.start_time_entry(
            title=t.title,
            category=t.category,
            project=t.project,
            tags=t.tags,
            notes=t.notes,
            task_id=t.id
        )
        timer_started = True
    else:
        timer_started = False

    # --- Total time spent on task (helper)
    def get_total_task_time():
        logs = time_repository.get_all_time_logs()
        # logs are dicts; sum durations for this task
        return int(sum(
            e.get('duration_minutes', 0)
            for e in logs
            if e.get('task_id') == t.id and e.get('duration_minutes')
        ))

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
        # Add current session minutes if active and for this task
        active = time_repository.get_active_time_entry()
        if active and active.get("task_id") == t.id and active.get("start"):
            # active["start"] is ISO string
            try:
                dt_start = datetime.fromisoformat(active["start"])
                now = datetime.now()
                total_minutes += int((now - dt_start).total_seconds() // 60)
            except Exception:
                pass

        timer_str = f"{mins:02}:{secs:02}"
        # Build display lines using attribute access
        # Fallback to "-" when field is None or empty
        due_display = "-"
        if getattr(t, "due", None):
            due_val = t.due
            if isinstance(due_val, datetime):
                due_display = due_val.isoformat()
            else:
                try:
                    due_display = datetime.fromisoformat(due_val).isoformat()
                except Exception:
                    due_display = str(due_val)
        lines = [
            "FOCUS MODE - Pomodoro ON" if pomodoro_mode else "FOCUS MODE",
            "",
            f"Title: {t.title or '-'}",
            f"Project: {t.project or '-'}",
            f"Category: {t.category or '-'}",
            f"Due: {due_display}",
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

        # Center and render lines
        for idx, line in enumerate(lines):
            try:
                stdscr.addstr(h//2 - len(lines)//2 + idx,
                              max(2, (w - len(line))//2), line)
            except curses.error:
                # In case of small window, skip out-of-bounds
                pass

        stdscr.refresh()
        c = stdscr.getch()
        if c == ord("p"):
            # Pause -> stop timing for this task
            stop_task_tui(stdscr)
            break
        if c == ord("d"):
            # Mark done
            done_task_tui(stdscr, sel)
            break
        if c == ord("P"):
            pomodoro_mode = not pomodoro_mode
            in_break = False
            session_mode_start = time.time()
            continue
        if c in (ord("q"), 27):  # Quit attempt
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
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Check if due date exists
    if not getattr(t, "due", None):
        popup_show(stdscr, ["Task must have a due date!"])
        return

    # Ask user how long before due for reminder
    reminder_str = popup_input(
        stdscr, "How long before due for reminder? (e.g. 1d, 120):")
    # You may parse reminder_str if needed; create_due_alert likely handles it internally
    try:
        create_due_alert(t)
        popup_show(stdscr, ["Reminder set!"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("reminder_task_tui", e)


def delete_task_tui(stdscr, sel):
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    # Guard: no tasks to delete
    if not tasks:
        return popup_show(stdscr, ["No tasks to delete"])
    # Guard: sel out of range
    if sel < 0 or sel >= len(tasks):
        return popup_show(stdscr, ["No task selected"])

    tid = tasks[sel].id
    if popup_confirm(stdscr, f"Delete task #{tid}?"):
        try:
            task_repository.delete_task(tid)
            popup_show(stdscr, [f"Deleted task #{tid}"])
        except Exception as e:
            popup_show(stdscr, [f"Error: {e}"])
            log_exception("delete_task_tui", e)


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
    Edit notes for the selected task, multi-line popup for convenience.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    current = t.get("notes") or ""
    note = popup_multiline_input(
        stdscr, "Edit Notes (Ctrl+D=save, ESC=cancel):", initial=current)
    try:
        task_repository.update_task(t["id"], {"notes": note or None})
        popup_show(stdscr, ["Notes updated"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("edit_task_notes_tui", e)


def cycle_task_filter(stdscr):
    """
    Cycle through TASK_FILTERS and show the new filter.
    draw_agenda() must read this state.
    """
    global current_filter_idx
    current_filter_idx = (current_filter_idx + 1) % len(TASK_FILTERS)
    popup_show(stdscr, [f"Filter: {TASK_FILTERS[current_filter_idx]}"])


def start_task_tui(stdscr, sel):
    """
    Starts timing the selected task. Optionally lets user update tags/notes.
    """
    from datetime import datetime
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Prompt for tags (show existing or empty)
    existing_tags = t.tags or ""
    new_tags = popup_input(
        stdscr, f"Tags [{existing_tags}]:"
    ) or existing_tags

    # Prompt for notes
    existing_notes = t.notes or ""
    new_notes = popup_multiline_input(
        stdscr, "Notes (optional):", initial=existing_notes
    ) or existing_notes

    updates = {}
    if new_tags is not None:
        updates["tags"] = new_tags
    if new_notes is not None:
        updates["notes"] = new_notes

    now_iso = datetime.now().isoformat()
    updates["status"] = "active"
    updates["start"] = now_iso

    try:
        # Update the task record first
        task_repository.update_task(t.id, updates)
        # Start time entry
        time_repository.start_time_entry(
            title=t.title,
            task_id=t.id,
            start_time=now_iso,
            category=t.category,
            project=t.project,
            tags=new_tags,
            notes=new_notes,
        )
        run_hooks("task", "started", t)
        popup_show(stdscr, [f"Started '{t.title}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("start_task_tui", e)


def stop_task_tui(stdscr):
    """
    Stops the current active task and time entry. Optionally lets user update tags/notes.
    """
    from datetime import datetime
    active = time_repository.get_active_time_entry()
    if not active or not active.get("task_id"):
        popup_show(stdscr, ["No active task"])
        return

    tid = active.get("task_id")
    task = task_repository.get_task_by_id(tid)
    if not task:
        popup_show(stdscr, ["Active task not found"])
        return

    # Prompt for tags
    existing_tags = task.tags or ""
    new_tags = popup_input(
        stdscr, f"Tags [{existing_tags}]:"
    ) or existing_tags

    # Prompt for notes
    existing_notes = task.notes or ""
    new_notes = popup_multiline_input(
        stdscr, "Notes (optional):", initial=existing_notes
    ) or existing_notes

    updates = {}
    if new_tags is not None:
        updates["tags"] = new_tags
    if new_notes is not None:
        updates["notes"] = new_notes
    updates["status"] = "backlog"

    now_iso = datetime.now().isoformat()

    try:
        # Stop the active time entry
        time_repository.stop_active_time_entry(end_time=now_iso)
        # Update the task record
        task_repository.update_task(tid, updates)
        run_hooks("task", "stopped", task)
        popup_show(stdscr, [f"Paused '{task.title}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("stop_task_tui", e)


def done_task_tui(stdscr, sel):
    """
    Marks the selected task as done, prompts for tags/notes, stops timing if running.
    """
    from datetime import datetime
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Prompt for tags
    existing_tags = t.tags or ""
    new_tags = popup_input(
        stdscr, f"Tags [{existing_tags}]:"
    ) or existing_tags

    # Prompt for notes
    existing_notes = t.notes or ""
    new_notes = popup_multiline_input(
        stdscr, "Notes (optional):", initial=existing_notes
    ) or existing_notes

    updates = {
        "tags": new_tags,
        "notes": new_notes,
        "status": "done",
        "end": datetime.now().isoformat(),
    }

    try:
        active = time_repository.get_active_time_entry()
        if active and active.get("task_id") == t.id:
            # Stop timing
            time_repository.stop_active_time_entry(end_time=updates["end"])
        # Update task record
        task_repository.update_task(t.id, updates)
        run_hooks("task", "completed", t)
        popup_show(stdscr, [f"Task '{t.title}' marked done"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("done_task_tui", e)
