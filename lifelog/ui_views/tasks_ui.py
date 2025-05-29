# -------------------------------------------------------------------
# Agenda view: calendar + top‐priority tasks
# -------------------------------------------------------------------


import curses
from datetime import datetime, timedelta
from lifelog.commands.task import calculate_priority
from lifelog.commands.utils.db import task_repository, time_repository
from lifelog.commands.utils.shared_utils import create_recur_schedule, parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_show


import calendar
import re
from datetime import datetime


def draw_agenda(pane, h, w, selected_idx):
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Agenda "
        pane.addstr(0, max((max_w - len(title)) // 2, 1), title, curses.A_BOLD)
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
                        pane.addstr(y, x, f"{day:>2}", curses.A_REVERSE)
                    elif day in due_days:
                        pane.addstr(y, x, f"{day:>2}", curses.A_UNDERLINE)
                    else:
                        pane.addstr(y, x, f"{day:>2}")
                # For non-numeric lines (month/year/header)
                if re.fullmatch(r"\D+", line.strip()):
                    pane.addstr(y, calendar_pad_left, line[:max_w-4])
        cal_panel_height = calendar_pad_top + len(month_lines) + 1

        # --- TASK LIST ---
        tasks = task_repository.query_tasks(
            show_completed=False, sort="priority")
        n = len(tasks)
        visible_rows = max_h - cal_panel_height - 5
        if visible_rows < 1:
            visible_rows = 1

        pane.addstr(cal_panel_height, 2, "Tasks:", curses.A_UNDERLINE)
        task_win_left = 2
        task_win_top = cal_panel_height + 1

        if n == 0:
            pane.addstr(task_win_top, task_win_left,
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
                    pane.addstr(y, task_win_left, " " * (max_w//2-4))
            for i, t in enumerate(tasks[start:end], start=start):
                is_sel = (i == selected_idx)
                attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
                id_str = f"{t['id']:>2}"
                title = t.get("title", "-")
                line = f"{id_str}: {title}"
                y = task_win_top + i - start
                if y < max_h - 2:
                    pane.addstr(y, task_win_left, line[:max_w//2-8], attr)

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
                        pane.addstr(detail_y + idx, preview_left,
                                    line[:max_w//2-6])

        pane.noutrefresh()
        return selected_idx
    except Exception as e:
        max_h, _ = pane.getmaxyx()
        pane.addstr(max_h-2, 2, f"Agenda err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        return 0


def draw_burndown(pane, h, w):
    try:
        pane.erase()
        pane.border()
        title = " Task Burndown "
        pane.addstr(0, max((w - len(title)) // 2, 1), title, curses.A_BOLD)

        tasks = task_repository.get_all_tasks()
        now = datetime.now()
        start_date = now - timedelta(days=2)
        end_date = now + timedelta(days=3)

        all_dates = []
        date_labels = []
        current_date = start_date
        while current_date <= end_date:
            all_dates.append(current_date)
            date_labels.append(current_date.strftime("%m/%d"))
            current_date += timedelta(days=1)

        not_done_counts = []
        overdue_counts = []
        for d in all_dates:
            not_done = 0
            overdue = 0
            for task in tasks:
                if task and task.get("status") != "done":
                    due_str = task.get("due")
                    if due_str:
                        try:
                            due_date = datetime.fromisoformat(due_str)
                            if due_date.date() <= d.date():
                                not_done += 1
                                if due_date.date() < now.date() and d.date() >= now.date():
                                    overdue += 1
                        except Exception:
                            continue
            not_done_counts.append(not_done)
            overdue_counts.append(overdue)

        # Y-axis: max outstanding
        max_count = max(not_done_counts + [1])
        chart_height = max(5, min(h-6, max_count + 1))
        left_margin = 4

        # Draw Y-axis
        for i in range(chart_height):
            y = 2 + i
            val = max_count - i
            if y < h - 2:
                pane.addstr(y, left_margin-2, f"{val:2d}|")

        # Draw bars
        for x, (count, overdue) in enumerate(zip(not_done_counts, overdue_counts)):
            bar_height = int((count / max_count) *
                             (chart_height-1)) if max_count > 0 else 0
            for i in range(bar_height):
                y = 2 + chart_height - 1 - i
                if y < h - 2:
                    pane.addstr(y, left_margin + x, "#" if overdue == 0 else "!",
                                curses.A_BOLD if overdue else curses.A_NORMAL)

        # X-axis (dates)
        pane.addstr(2+chart_height, left_margin, "".join(
            date_labels[i][3:]+" " for i in range(len(date_labels)))[:w-left_margin-1])

        # Stats
        pane.addstr(
            h-3, left_margin, f"Outstanding: {not_done_counts[-1]}, Overdue: {overdue_counts[-1]}")
        pane.addstr(h-2, left_margin, "Key: # = open, ! = overdue")

        pane.noutrefresh()

    except Exception as e:
        pane.addstr(h-2, 2, f"Burndown err: {e}", curses.A_BOLD)
        pane.noutrefresh()


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
    recurrence = None
    if popup_confirm(stdscr, "Add recurrence rule?"):
        recur_input = popup_recurrence(stdscr)
        try:
            recur_data = create_recur_schedule("interactive", recur_input)
            recurrence = {
                "everyX": recur_data.get("interval"),
                "unit": recur_data.get("unit"),
                "daysOfWeek": recur_data.get("days_of_week"),
                "onFirstOfMonth": recur_data.get("on_first_of_month", False)
            }
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
        "recurrence": recurrence,
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
        "recurrence": None,
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
    recurrence = None
    # Optional: Edit recurrence interactively
    if popup_confirm(stdscr, "Edit recurrence?"):
        recur_input = popup_recurrence(stdscr)
        try:
            recur_data = create_recur_schedule("interactive", recur_input)
            recurrence = {
                "everyX": recur_data.get("interval"),
                "unit": recur_data.get("unit"),
                "daysOfWeek": recur_data.get("days_of_week"),
                "onFirstOfMonth": recur_data.get("on_first_of_month", False)
            }
        except Exception as e:
            popup_show(stdscr, [f"Recurrence setup failed: {e}"])
            return

    updates = {
        "title": new_title,
        "due": parse_date_string(new_due).isoformat() if new_due else None,
        "category": new_cat,
        "project": new_prj,
        "impt": int(new_impt) if new_impt and new_impt.isdigit() else t.get("impt", 1),
        "tags": new_tags,
        "notes": new_notes,
        "recurrence": recurrence,
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
