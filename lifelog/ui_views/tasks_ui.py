# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------
from dataclasses import asdict
import time
import npyscreen
import curses
from datetime import datetime
import calendar
import re

from lifelog.utils.db.models import Task
from lifelog.commands.task_module import create_due_alert
from lifelog.utils.db import task_repository, time_repository
from lifelog.ui_views.popups import popup_confirm, popup_error, popup_input, popup_multiline_input, popup_show
from lifelog.ui_views.ui_helpers import log_exception, safe_addstr
from lifelog.ui_views.forms import TaskCloneForm, TaskEditForm, TaskForm, TaskViewForm, run_form
from lifelog.utils.hooks import run_hooks
from lifelog.utils.shared_utils import now_local, now_utc, parse_date_string, calculate_priority


# Module‐level state for task filter:
TASK_FILTERS = ["backlog", "active", "done"]
current_filter_idx = 0


def draw_agenda(pane, h, w, selected_idx):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = f" Tasks "
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)
        now = now_local()

        # Determine filter
        # e.g., "backlog", "active", "done"
        status_filter = TASK_FILTERS[current_filter_idx]
        show_completed = (status_filter == "done")
        # If you want only backlog/active when status_filter != "done":
        try:
            tasks = task_repository.query_tasks(
                show_completed=show_completed,
                sort="priority"
            )
        except Exception as db_err:
            popup_error(pane, f"Failed to load tasks: {db_err}")
            return 0

        if status_filter in ("backlog", "active"):
            tasks = [t for t in tasks if getattr(
                t, "status", None) == status_filter]
        # --- CALENDAR PANEL ---
        cal = calendar.TextCalendar(firstweekday=0)
        month_lines = cal.formatmonth(now.year, now.month).splitlines()
        due_days = set()
        for t in tasks:
            due_val = getattr(t, "due", None)
            if due_val:
                if isinstance(due_val, datetime):
                    due_dt = due_val
                else:
                    try:
                        due_dt = datetime.fromisoformat(due_val)
                    except Exception:
                        continue
                if due_dt.year == now.year and due_dt.month == now.month:
                    due_days.add(due_dt.day)
        calendar_pad_top = 2
        calendar_pad_left = 2
        for i, line in enumerate(month_lines):
            y = calendar_pad_top + i
            if y < max_h - 1 and len(line) < max_w - 2:
                # highlight days
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
                # non-numeric header lines
                if re.fullmatch(r"\D+", line.strip()):
                    safe_addstr(pane, y, calendar_pad_left, line[:max_w-4])
        cal_panel_height = calendar_pad_top + len(month_lines) + 1

        # --- TASK LIST ---
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
            selected_idx = max(0, min(selected_idx, n-1))
            start = max(0, selected_idx - visible_rows // 2)
            end = min(start + visible_rows, n)
            # Clear area
            for i in range(visible_rows):
                y = task_win_top + i
                if y < max_h - 2:
                    safe_addstr(pane, y, task_win_left, " " * (max_w//2-4))
            # Draw tasks
            for i, t in enumerate(tasks[start:end], start=start):
                is_sel = (i == selected_idx)
                attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
                id_val = getattr(t, "id", None)
                id_str = f"{id_val:>2}" if id_val is not None else " -"
                title_str = t.title or "-"
                line = f"{id_str}: {title_str}"
                y = task_win_top + i - start
                if y < max_h - 2:
                    safe_addstr(pane, y, task_win_left,
                                line[:max_w//2-8], attr)

            # --- TASK DETAIL PREVIEW (right side) ---
            if max_w > 40:
                preview_left = max_w//2 + 2
                detail_y = cal_panel_height
                t = tasks[selected_idx]
                # Build preview lines via attribute access:
                id_val = getattr(t, "id", None)
                line_id = f"ID: {id_val}" if id_val is not None else "ID: -"
                title_val = t.title or "-"
                line_title = f"Title: {title_val}"
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
                status_val = getattr(t, "status", None)
                if hasattr(status_val, "value"):
                    status_str = status_val.value
                else:
                    status_str = str(status_val) if status_val else "-"
                line_status = f"Status: {status_str}"
                cat_str = t.category or "-"
                line_cat = f"Category: {cat_str}"
                proj_str = t.project or "-"
                line_proj = f"Project: {proj_str}"
                prio_val = getattr(t, "priority", None)
                prio_str = str(prio_val) if prio_val is not None else "-"
                line_prio = f"Priority: {prio_str}"
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
                for idx_line, line in enumerate(preview_lines):
                    if detail_y + idx_line < max_h - 2:
                        safe_addstr(pane, detail_y + idx_line, preview_left,
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
        task_data.setdefault('created', now_utc().isoformat())
        task_data.setdefault('status', 'backlog')
        task_data.setdefault('importance', 3)

        # Calculate priority like CLI
        task_data["priority"] = calculate_priority(task_data)
        if "due" in task_data and task_data["due"]:
            try:
                due_dt = parse_date_string(
                    task_data["due"], future=True, now=now_utc())
                task_data["due"] = due_dt.isoformat()
            except Exception as e:
                popup_error(_stdscr, f"Invalid due date: {e}")
                return
        # Create and save task
        task = Task(**task_data)
        task_repository.add_task(task)

        # Run hooks like CLI
        # run_hooks("task", "created", task)

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
        now = now_utc().isoformat()
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
        # run_hooks("task", "created", task)

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
            now_iso = now_utc().isoformat()
            task_data = {
                "title": line,
                "created": now_iso,
                "status": "backlog",
                "importance": 3,
            }
            task_data["priority"] = calculate_priority(task_data)
            task = Task(**task_data)
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
    if sel < 0 or sel >= len(tasks):
        popup_show(_stdscr, ["No tasks to clone"], title="Error")
        return
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
    now = now_utc().isoformat()
    # Do NOT clone start/stop/time-tracking fields!
    task = Task(**{**task_data, "created": now,
                "priority": calculate_priority(task_data), "status": "backlog"})
    task_repository.add_task(task)
    npyscreen.notify_confirm(f"Task cloned as '{task.title}'", title="Cloned")

# --- Edit Task with Form ---


def edit_task_tui(_stdscr, sel):
    tasks = task_repository.get_all_tasks()
    if sel < 0 or sel >= len(tasks):
        popup_show(_stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    class App(npyscreen.NPSAppManaged):
        def onStart(selfx):
            form = selfx.addForm("MAIN", TaskEditForm, name="Edit Task")
            form.title.value = t.title or ""
            form.category.value = t.category or ""
            form.project.value = t.project or ""
            # due: if datetime, format; if string, keep
            if getattr(t, "due", None):
                if isinstance(t.due, datetime):
                    form.due.value = t.due.strftime("%Y-%m-%d")
                else:
                    form.due.value = str(t.due)
            else:
                form.due.value = ""
            # notes
            if hasattr(form.notes, "values"):
                form.notes.values = t.notes.splitlines() if t.notes else [""]
            else:
                form.notes.value = t.notes or ""
            form.tags.value = t.tags or ""
            # recurrence fields:
            rec = getattr(t, "recurrence", None) or {}
            if rec.get("repeat"):
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
    # Build updates dict
    updates = {}
    # For each field in form_data, set if changed:
    if "title" in task_data and task_data["title"] != t.title:
        updates["title"] = task_data["title"]
    if "category" in task_data and task_data["category"] != t.category:
        updates["category"] = task_data["category"] or None
    if "project" in task_data and task_data["project"] != t.project:
        updates["project"] = task_data["project"] or None
    if "due" in task_data:
        due_str = task_data["due"].strip()
        if due_str:
            try:
                due_dt = datetime.fromisoformat(due_str)
                updates["due"] = due_dt.isoformat()
            except Exception:
                popup_show(_stdscr, [f"Invalid due date: {due_str}"])
                return
        else:
            updates["due"] = None
    if "notes" in task_data:
        updates["notes"] = task_data["notes"] or None
    if "tags" in task_data:
        updates["tags"] = task_data["tags"] or None
    # Handle recurrence if present in form_data:
    if "recur_enabled" in task_data:
        if task_data["recur_enabled"]:
            # build recurrence dict from form_data fields
            rec = {}
            # assume form_data provides recur_everyX, recur_unit, recur_days, recur_first_of_month
            if task_data.get("recur_everyX"):
                try:
                    rec["everyX"] = int(task_data["recur_everyX"])
                except:
                    popup_show(
                        _stdscr, [f"Invalid recurrence everyX: {task_data['recur_everyX']}"])
                    return
            if task_data.get("recur_unit"):
                rec["unit"] = task_data["recur_unit"]
            if task_data.get("recur_days"):
                try:
                    rec["daysOfWeek"] = [
                        int(d) for d in task_data["recur_days"].split(",") if d.strip()]
                except:
                    popup_show(
                        _stdscr, [f"Invalid recurrence days: {task_data['recur_days']}"])
                    return
            rec["onFirstOfMonth"] = bool(task_data.get("recur_first_of_month"))
            updates["recurrence"] = rec
        else:
            updates["recurrence"] = None

    if updates:
        # Recalculate priority if fields affecting it changed (e.g., importance, due)
        # If calculate_priority expects a dict with relevant fields, build merged dict:
        temp_kwargs = asdict(t)
        temp_kwargs.update(updates)
        temp_task = Task(**temp_kwargs)
        try:
            updates["priority"] = calculate_priority(temp_task)
        except Exception as e:
            # Log but continue
            log_exception("edit_task_tui priority", e)
        try:
            task_repository.update_task(t.id, updates)
            updated_task = task_repository.get_task_by_id(t.id)
            # run_hooks("task", "updated", updated_task)
            npyscreen.notify_confirm(f"Task #{t.id} updated!", title="Updated")
        except Exception as e:
            popup_error(_stdscr, f"Error updating task: {e}")
            log_exception("edit_task_tui", e)
    else:
        npyscreen.notify_confirm("No changes made.", title="Edit Task")


# --- View Task with Form (read-only) ---


def view_task_tui(_stdscr, sel):
    tasks = task_repository.get_all_tasks()
    if sel < 0 or sel >= len(tasks):
        popup_show(_stdscr, ["No task selected"], title="Error")
        return
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
    import time as _time
    from datetime import datetime as _datetime

    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # --- Start timer if not running for this task
    active = time_repository.get_active_time_entry()
    if not (active and getattr(active, "task_id", None) == t.id):
        # Start a new time entry for this task
        now_iso = _datetime.now().isoformat()
        time_entry_data = {
            "title": t.title or "",
            "task_id": t.id,
            "start": now_iso,
            "category": t.category,
            "project": t.project,
            "tags": t.tags,
            "notes": t.notes,
        }
        try:
            time_repository.start_time_entry(time_entry_data)
            # run_hooks("task", "started", t)
        except Exception as e:
            popup_show(
                stdscr, [f"Error starting time entry: {e}"], title="Error")
            log_exception("focus_mode_tui start", e)
            return
        timer_started = True
    else:
        timer_started = False

    # Helper: total time for this task (sum of durations from TimeLog instances)
    def get_total_task_time():
        logs = time_repository.get_all_time_logs()
        total = 0
        for e in logs:
            if getattr(e, "task_id", None) == t.id:
                dur = getattr(e, "duration_minutes", None)
                if dur:
                    total += dur
        return int(total)

    # Pomodoro settings
    pomodoro_mode = False
    pomo_length = 25 * 60  # seconds
    break_length = 5 * 60  # seconds
    in_break = False

    session_mode_start = _time.time()
    stdscr.nodelay(True)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        elapsed = int(_time.time() - session_mode_start)
        mins, secs = divmod(elapsed, 60)

        # Display total task time including current running segment
        total_minutes = get_total_task_time()
        active = time_repository.get_active_time_entry()
        if active and getattr(active, "task_id", None) == t.id and getattr(active, "start", None):
            dt_start = active.start
            if isinstance(dt_start, _datetime):
                now = _datetime.now()
                total_minutes += int((now - dt_start).total_seconds() // 60)
            else:
                try:
                    dt0 = _datetime.fromisoformat(dt_start)
                    now = _datetime.now()
                    total_minutes += int((now - dt0).total_seconds() // 60)
                except Exception:
                    pass

        timer_str = f"{mins:02}:{secs:02}"
        # Format due display
        due_display = "-"
        due_val = getattr(t, "due", None)
        if due_val:
            if isinstance(due_val, _datetime):
                due_display = due_val.isoformat()
            else:
                try:
                    due_display = _datetime.fromisoformat(due_val).isoformat()
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
            lines.append(
                "Press 'P' to toggle Pomodoro, 'p' to pause, 'd' to mark done.")
        else:
            lines.append(
                "Press 'P' for Pomodoro, 'p' to pause, 'd' to mark done.")
        lines.append("You must pause or complete the task to exit focus mode.")

        # Render centered
        for idx, line in enumerate(lines):
            try:
                stdscr.addstr(h//2 - len(lines)//2 + idx,
                              max(2, (w - len(line))//2), line)
            except curses.error:
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
            session_mode_start = _time.time()
            continue
        # Prevent quitting other than pause/done
        if c in (ord("q"), 27):
            popup_show(stdscr, [
                "You must pause ('p') or mark done ('d') to exit focus mode.",
                "Pomodoro: 'P' to toggle, stay focused!"
            ])
            continue

        if pomodoro_mode:
            if not in_break and elapsed >= pomo_length:
                popup_show(stdscr, ["Pomodoro complete! Break time."])
                in_break = True
                session_mode_start = _time.time()
            elif in_break and elapsed >= break_length:
                popup_show(stdscr, ["Break over! Back to focus."])
                in_break = False
                session_mode_start = _time.time()

        _time.sleep(1)

    stdscr.nodelay(False)


def set_task_reminder_tui(stdscr, sel):
    """
    Set a custom reminder for a task via popup, using user-specified offset.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Check due date:
    due = getattr(t, "due", None)
    if not due:
        popup_show(stdscr, ["Task must have a due date!"], title="Error")
        return

    # Ask user how long before due for reminder
    reminder_str = popup_input(
        stdscr,
        "How long before due for reminder? (e.g. '1d', '2h', '120'):",
        required=True
    )
    if reminder_str is None:
        # User cancelled
        return

    try:
        # Use the new signature: pass offset_str
        create_due_alert(t, reminder_str)
        popup_show(
            stdscr, [f"Reminder set {reminder_str} before due."], title="Success")
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"], title="Error")
        log_exception("set_task_reminder_tui", e)


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
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Get current recurrence or defaults
    rec = getattr(t, "recurrence", {}) or {}
    everyX = rec.get("everyX", "")
    unit = rec.get("unit", "")
    daysOfWeek = rec.get("daysOfWeek", [])
    onFirstOfMonth = rec.get("onFirstOfMonth", False)

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

    updates_recur = {}
    try:
        if new_everyX.strip():
            updates_recur["everyX"] = int(new_everyX.strip())
        elif everyX:
            updates_recur["everyX"] = everyX

        if new_unit.strip():
            updates_recur["unit"] = new_unit.strip()
        elif unit:
            updates_recur["unit"] = unit

        if new_days.strip():
            updates_recur["daysOfWeek"] = [
                int(d) for d in new_days.strip().split(",") if d.strip()]
        elif daysOfWeek:
            updates_recur["daysOfWeek"] = daysOfWeek

        if new_first.strip().lower() in ("y", "yes", "1"):
            updates_recur["onFirstOfMonth"] = True
        elif new_first.strip().lower() in ("n", "no", "0"):
            updates_recur["onFirstOfMonth"] = False
        else:
            updates_recur["onFirstOfMonth"] = onFirstOfMonth

        # If user leaves all fields blank (and no previous), clear recurrence
        if not (new_everyX.strip() or new_unit.strip() or new_days.strip()):
            confirm = popup_confirm(stdscr, "Clear recurrence?")
            if confirm:
                updates_recur = None
    except Exception as e:
        popup_show(stdscr, [f"Invalid recurrence: {e}"])
        log_exception("edit_recurrence_tui", e)
        return

    try:
        if updates_recur is not None:
            task_repository.update_task(t.id, {"recurrence": updates_recur})
            popup_show(stdscr, ["Recurrence updated"])
        else:
            task_repository.update_task(t.id, {"recurrence": None})
            popup_show(stdscr, ["Recurrence cleared"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("edit_recurrence_tui", e)


def edit_notes_tui(stdscr, sel):
    """
    Edit notes for the selected task, multi-line popup for convenience.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    t = tasks[sel]
    current = t.notes or ""
    note = popup_multiline_input(
        stdscr, "Edit Notes (Ctrl+D=save, ESC=cancel):", initial=current)
    try:
        task_repository.update_task(t.id, {"notes": note or None})
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
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Prompt for tags (show existing or empty)
    existing_tags = t.tags or ""
    new_tags = popup_input(
        stdscr, f"Tags [{existing_tags}]:"
    )
    if new_tags is None:
        return
    if new_tags == "":
        new_tags = existing_tags

    # Prompt for notes
    existing_notes = t.notes or ""
    new_notes = popup_multiline_input(
        stdscr, "Notes (optional):", initial=existing_notes
    )
    if new_notes is None:
        return
    if new_notes == "":
        new_notes = existing_notes

    # Build updates dict for task
    updates = {}
    if new_tags != existing_tags:
        updates["tags"] = new_tags or None
    if new_notes != existing_notes:
        updates["notes"] = new_notes or None
    now_iso = now_utc().isoformat()
    updates["status"] = "active"
    updates["start"] = now_iso

    try:
        # Update the task record first
        task_repository.update_task(t.id, updates)
        # Start time entry: build a dict for repository
        time_entry_data = {
            "title": t.title or "",
            "task_id": t.id,
            "start": now_iso,
            # Optionally propagate category/project/tags/notes:
            "category": t.category,
            "project": t.project,
            "tags": new_tags or None,
            "notes": new_notes or None,
        }
        time_repository.start_time_entry(time_entry_data)
        # Refresh task for hooks
        updated_task = task_repository.get_task_by_id(t.id)
        # run_hooks("task", "started", updated_task)
        popup_show(stdscr, [f"Started '{t.title}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("start_task_tui", e)


def stop_task_tui(stdscr):
    """
    Stops the current active task and time entry. Optionally lets user update tags/notes.
    """
    active = time_repository.get_active_time_entry()
    if not active or not getattr(active, "task_id", None):
        popup_show(stdscr, ["No active task"])
        return

    tid = active.task_id
    task = task_repository.get_task_by_id(tid)
    if not task:
        popup_show(stdscr, ["Active task not found"])
        return

    # Prompt for tags
    existing_tags = task.tags or ""
    new_tags = popup_input(
        stdscr, f"Tags [{existing_tags}]:"
    )
    if new_tags is None:
        return
    if new_tags == "":
        new_tags = existing_tags

    # Prompt for notes
    existing_notes = task.notes or ""
    new_notes = popup_multiline_input(
        stdscr, "Notes (optional):", initial=existing_notes
    )
    if new_notes is None:
        return
    if new_notes == "":
        new_notes = existing_notes

    updates = {}
    if new_tags != existing_tags:
        updates["tags"] = new_tags or None
    if new_notes != existing_notes:
        updates["notes"] = new_notes or None
    updates["status"] = "backlog"
    now_iso = now_utc().isoformat()

    try:
        # Stop the active time entry
        # Repository expects a dict or datetime for end_time:
        time_repository.stop_active_time_entry(end_time=now_iso,
                                               tags=new_tags or None,
                                               notes=new_notes or None)
        # Update the task record
        task_repository.update_task(tid, updates)
        updated_task = task_repository.get_task_by_id(tid)
        # run_hooks("task", "stopped", updated_task)
        popup_show(stdscr, [f"Paused '{task.title}'"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("stop_task_tui", e)


def done_task_tui(stdscr, sel):
    """
    Marks the selected task as done, prompts for tags/notes, stops timing if running.
    """
    tasks = task_repository.query_tasks(show_completed=False, sort="priority")
    if sel < 0 or sel >= len(tasks):
        popup_show(stdscr, ["No task selected"], title="Error")
        return
    t = tasks[sel]

    # Prompt for tags
    existing_tags = t.tags or ""
    new_tags = popup_input(
        stdscr, f"Tags [{existing_tags}]:"
    )
    if new_tags is None:
        return
    if new_tags == "":
        new_tags = existing_tags

    # Prompt for notes
    existing_notes = t.notes or ""
    new_notes = popup_multiline_input(
        stdscr, "Notes (optional):", initial=existing_notes
    )
    if new_notes is None:
        return
    if new_notes == "":
        new_notes = existing_notes

    updates = {
        "tags": new_tags or None,
        "notes": new_notes or None,
        "status": "done",
        # Optionally record completion timestamp on Task if schema has e.g. 'completed' field:
        # "completed_at": now_utc().isoformat()
    }

    now_iso = now_utc().isoformat()
    try:
        active = time_repository.get_active_time_entry()
        if active and getattr(active, "task_id", None) == t.id:
            # Stop timing
            time_repository.stop_active_time_entry(end_time=now_iso,
                                                   tags=new_tags or None,
                                                   notes=new_notes or None)
        # Update task record
        task_repository.update_task(t.id, updates)
        updated_task = task_repository.get_task_by_id(t.id)
        # run_hooks("task", "completed", updated_task)
        popup_show(stdscr, [f"Task '{t.title}' marked done"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])
        log_exception("done_task_tui", e)
