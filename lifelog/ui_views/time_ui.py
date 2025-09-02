
# -------------------------------------------------------------------
# Time view
# -------------------------------------------------------------------
import curses
from datetime import datetime, timedelta
import time

import npyscreen
from lifelog.utils.db.models import TimeLog
from lifelog.utils.db import time_repository
from lifelog.utils.shared_utils import add_category_to_config, add_project_to_config, get_available_categories, get_available_projects, now_local, now_utc, parse_date_string
from lifelog.ui_views.popups import popup_confirm, popup_input, popup_multiline_input, popup_select_option, popup_show
from lifelog.ui_views.ui_helpers import safe_addstr
from lifelog.ui_views.forms import TimeEntryForm, run_form

TIME_PERIODS = {'d': 'day', 'w': 'week', 'm': 'month', 'a': 'all'}


current_time_period = {"period": "week"}


def set_time_period(period):
    if period in ('day', 'week', 'month', 'all'):
        current_time_period["period"] = period


def get_time_period():
    return current_time_period["period"]


def _format_duration(minutes: float) -> str:
    # Format minutes into "H hr M min" or "M min"
    try:
        minutes = float(minutes)
    except Exception:
        return "-"
    if minutes >= 60:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours} hr {mins} min"
    else:
        return f"{int(minutes)} min"


def get_since_from_period(period):
    now = now_local()
    if period == 'day':
        return now - timedelta(days=1)
    elif period == 'week':
        return now - timedelta(days=7)
    elif period == 'month':
        return now - timedelta(days=30)
    else:
        # 'all' or other: far past
        return now - timedelta(days=365*10)


def draw_time(pane, h, w, selected_idx):
    """
    Draw the active timer (if any) and recent time entries in the UI pane.
    Uses TimeLog dataclass attributes.
    """
    try:
        pane.erase()
        max_h, max_w = pane.getmaxyx()
        pane.border()
        title = " Time "
        period = get_time_period()
        period_title = {
            'day': ' (last 24h)',
            'week': ' (last 7 days)',
            'month': ' (last 30 days)',
            'all': ' (all time)'
        }.get(period, '')
        safe_addstr(pane, 0, max((max_w - len(title + period_title)) // 2, 1),
                    title + period_title, curses.A_BOLD)

        y = 2
        active = time_repository.get_active_time_entry()
        if active:
            start_dt = getattr(active, "start", None)
            if isinstance(start_dt, datetime):
                elapsed = (now_utc() - start_dt).total_seconds() // 60
            else:
                elapsed = 0
            safe_addstr(
                pane, y, 2, f"▶ {active.title} ({int(elapsed)} min)", curses.A_BOLD)
            y += 2

        since = get_since_from_period(period)
        # Repository returns list of TimeLog instances
        logs = time_repository.get_all_time_logs(since=since)
        n = len(logs)
        if n == 0:
            safe_addstr(pane, y, 2, "(no history)")
            pane.noutrefresh()
            return 0

        # Clamp selected_idx
        selected_idx = max(0, min(selected_idx, n - 1))
        visible_rows = max_h - y - 2
        start = max(0, selected_idx - visible_rows // 2)
        end = min(start + visible_rows, n)
        for i, r in enumerate(logs[start:end], start=start):
            duration = getattr(r, "duration_minutes", None) or 0
            m = int(duration)
            title_str = r.title or ""
            line = f"{r.id:>2} {title_str[:20]:20} {m:>4} min"
            row_y = y + i - start
            if row_y < max_h - 1:
                attr = curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
                safe_addstr(pane, row_y, 2, line[:max_w - 4], attr)
        pane.noutrefresh()
        return selected_idx
    except Exception as e:
        # On exception, show message at bottom
        safe_addstr(pane, h - 2, 2, f"Time err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        return 0


# ——— Start Timer ———


def start_time_tui(stdscr):
    """
    Prompt user to start a new time tracking session via TUI.
    """
    title = popup_input(stdscr, "Activity Title:")
    if not title:
        return

    # Category selection, allow new
    cat = popup_select_option(
        stdscr, "Category:", get_available_categories(), allow_new=True)
    if cat:
        if cat not in get_available_categories():
            add_category_to_config(cat)

    # Project selection, allow new
    proj = popup_select_option(
        stdscr, "Project:", get_available_projects(), allow_new=True)
    if proj:
        if proj not in get_available_projects():
            add_project_to_config(proj)

    tags = popup_input(stdscr, "Tags (comma, optional):")
    notes = popup_multiline_input(stdscr, "Notes (optional):")
    task_id_str = popup_input(stdscr, "Attach to task ID [optional]:")

    past = popup_input(stdscr, "Start time (e.g. '30m ago') [optional]:")
    try:
        start_dt = parse_date_string(past) if past else now_utc()
    except Exception as e:
        popup_confirm(stdscr, f"Invalid time: {e}")
        return

    # Build a dict for repository. Repository expects Dict[str,Any].
    data: dict = {}
    data["title"] = title
    data["start"] = start_dt
    if cat:
        data["category"] = cat
    if proj:
        data["project"] = proj
    if tags:
        data["tags"] = tags
    if notes:
        data["notes"] = notes
    if task_id_str:
        try:
            data["task_id"] = int(task_id_str)
        except ValueError:
            popup_confirm(stdscr, f"Invalid task ID: {task_id_str}")
            return

    # Call repository
    try:
        time_repository.start_time_entry(data)
    except Exception as e:
        popup_confirm(stdscr, f"Failed to start time entry: {e}")
        return

    popup_confirm(stdscr, f"Started '{title}'")


def add_manual_time_entry_tui(_stdscr=None):
    """
    Launches the TimeEntryForm for manual time entry and adds it to DB.
    """
    entry_data = run_form(TimeEntryForm)
    if not entry_data:
        return
    try:
        # Parse start time; default now if missing/invalid
        if entry_data.get("start"):
            try:
                start_dt = parse_date_string(entry_data["start"])
            except Exception as e:
                raise ValueError(f"Invalid start time: {e}")
        else:
            start_dt = now_utc()

        # Parse end time if provided
        if entry_data.get("end"):
            try:
                end_dt = parse_date_string(entry_data["end"])
            except Exception as e:
                raise ValueError(f"Invalid end time: {e}")
        else:
            end_dt = None

        # Parse distracted minutes
        distracted = 0.0
        if entry_data.get("distracted"):
            try:
                distracted = float(entry_data["distracted"])
            except Exception:
                raise ValueError(
                    f"Invalid distracted minutes: {entry_data['distracted']}")

        # Compute duration_minutes if both start and end
        duration = None
        if end_dt:
            duration = (end_dt - start_dt).total_seconds() / 60

        # Build dict for repository
        data: dict = {}
        data["title"] = entry_data.get("title") or ""
        data["start"] = start_dt
        if end_dt:
            data["end"] = end_dt
        if duration is not None:
            data["duration_minutes"] = duration
        if entry_data.get("category"):
            data["category"] = entry_data["category"]
        if entry_data.get("project"):
            data["project"] = entry_data["project"]
        if entry_data.get("tags"):
            data["tags"] = entry_data["tags"]
        if entry_data.get("notes"):
            data["notes"] = entry_data["notes"]
        if entry_data.get("task_id"):
            try:
                data["task_id"] = int(entry_data["task_id"])
            except ValueError:
                raise ValueError(f"Invalid task ID: {entry_data['task_id']}")
        if distracted:
            data["distracted_minutes"] = distracted

        # Call repository.add_time_entry
        time_repository.add_time_entry(data)
        npyscreen.notify_confirm(
            f"Time entry '{data['title']}' added", title="Success")
    except Exception as e:
        npyscreen.notify_confirm(f"Error: {e}", title="Time Entry Error")


def edit_time_entry_tui(_stdscr, sel):
    """
    Edit an existing time entry via TimeEntryForm.
    sel: index in the list returned by get_all_time_logs.
    """
    # Fetch recent logs (past year)
    try:
        logs = time_repository.get_all_time_logs(
            since=now_utc() - timedelta(days=365))
    except Exception as e:
        popup_show(_stdscr, [f"Error fetching logs: {e}"], title="Error")
        return

    if not (0 <= sel < len(logs)):
        popup_show(_stdscr, [f"Invalid selection {sel}"], title="Error")
        return
    entry = logs[sel]

    # Prefill form with existing entry data
    class EditApp(npyscreen.NPSAppManaged):
        def onStart(selfx):
            form = selfx.addForm("MAIN", TimeEntryForm, name="Edit Time Entry")
            # Title
            form.title.value = entry.title or ""
            # Category, project, tags, notes
            form.category.value = entry.category or ""
            form.project.value = entry.project or ""
            form.tags.value = entry.tags or ""
            # Notes: if multiline widget
            if hasattr(form.notes, "values"):
                form.notes.values = entry.notes.splitlines() if entry.notes else [
                    ""]
            else:
                form.notes.value = entry.notes or ""
            # Task ID
            form.task_id.value = str(entry.task_id) if entry.task_id else ""
            # Start/end as formatted strings
            if isinstance(entry.start, datetime):
                form.start.value = entry.start.strftime("%Y-%m-%d %H:%M")
            else:
                form.start.value = ""
            if isinstance(entry.end, datetime):
                form.end.value = entry.end.strftime("%Y-%m-%d %H:%M")
            else:
                form.end.value = ""
            # Distracted
            form.distracted.value = str(
                getattr(entry, 'distracted_minutes', 0) or "")

    app = EditApp()
    app.run()
    new_data = getattr(app, 'form_data', None)
    if not new_data:
        return

    try:
        # Parse updated fields
        # Start
        if new_data.get("start"):
            try:
                start_dt = parse_date_string(new_data["start"])
            except Exception as e:
                raise ValueError(f"Invalid start time: {e}")
        else:
            start_dt = entry.start
        # End
        if new_data.get("end"):
            try:
                end_dt = parse_date_string(new_data["end"])
            except Exception as e:
                raise ValueError(f"Invalid end time: {e}")
        else:
            end_dt = entry.end
        # Distracted
        distracted = 0.0
        if new_data.get("distracted"):
            try:
                distracted = float(new_data["distracted"])
            except Exception:
                raise ValueError(
                    f"Invalid distracted minutes: {new_data['distracted']}")
        # Compute duration
        if isinstance(start_dt, datetime) and isinstance(end_dt, datetime):
            duration = (end_dt - start_dt).total_seconds() / 60
        else:
            duration = entry.duration_minutes

        # Build updates dict
        updates: dict = {}
        # Only include changed fields or simply overwrite:
        updates["title"] = new_data.get("title") or entry.title
        cat = new_data.get("category")
        updates["category"] = cat if cat else None
        proj = new_data.get("project")
        updates["project"] = proj if proj else None
        tags = new_data.get("tags")
        updates["tags"] = tags if tags else None
        notes = new_data.get("notes")
        updates["notes"] = notes if notes else None
        task_id_str = new_data.get("task_id")
        if task_id_str:
            try:
                updates["task_id"] = int(task_id_str)
            except ValueError:
                raise ValueError(f"Invalid task ID: {task_id_str}")
        else:
            updates["task_id"] = None
        # Dates and durations
        if start_dt is not None:
            updates["start"] = start_dt
        if end_dt is not None:
            updates["end"] = end_dt
        updates["distracted_minutes"] = distracted
        updates["duration_minutes"] = duration

        # Call repository.update_time_entry
        time_repository.update_time_entry(entry.id, **updates)
        npyscreen.notify_confirm(f"Updated entry #{entry.id}", title="Updated")
    except Exception as e:
        npyscreen.notify_confirm(f"Error: {e}", title="Edit Entry Error")


def add_distracted_time_tui(stdscr):
    """
    Log a distracted block for the current active time log.
    """
    mins_str = popup_input(stdscr, "How many minutes distracted?")
    try:
        mins = int(mins_str)
        if mins <= 0:
            raise ValueError("Must be positive")
    except Exception as e:
        popup_show(stdscr, [f"Invalid input: {e}"])
        return

    active = time_repository.get_active_time_entry()
    if not active:
        popup_show(stdscr, ["No active timer to add distraction to."])
        return

    try:
        new_distracted = time_repository.add_distracted_minutes_to_active(mins)
    except Exception as e:
        popup_show(stdscr, [f"Error updating distracted minutes: {e}"])
        return

    popup_show(stdscr, [
               f"Added {mins} distracted min (Total distracted: {new_distracted} min)"])


def delete_time_entry_tui(stdscr, sel):
    """
    Delete a selected time entry.
    """
    try:
        logs = time_repository.get_all_time_logs(
            since=now_utc() - timedelta(days=365))
    except Exception as e:
        popup_show(stdscr, [f"Error fetching logs: {e}"], title="Error")
        return

    if not (0 <= sel < len(logs)):
        popup_show(stdscr, [f"Invalid selection {sel}"], title="Error")
        return
    entry = logs[sel]
    if popup_confirm(stdscr, f"Delete entry #{entry.id}?"):
        try:
            time_repository.delete_time_entry(entry.id)
            popup_show(stdscr, [f"Deleted entry #{entry.id}"])
        except Exception as e:
            popup_show(stdscr, [f"Error deleting entry: {e}"])


def stopwatch_tui(stdscr):
    """
    Show a live stopwatch for the active timer until a key is pressed.
    """
    curses.curs_set(0)
    stdscr.nodelay(True)
    h, w = stdscr.getmaxyx()
    active = time_repository.get_active_time_entry()
    if not active or not isinstance(active.start, datetime):
        stdscr.addstr(h//2, max((w-20)//2, 0),
                      "⚠️ No active timer ⚠️", curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()
        return

    start = active.start
    while True:
        stdscr.erase()
        elapsed = now_utc() - start
        hms = str(elapsed).split(".")[0]
        stdscr.addstr(h//2, max((w - len(hms))//2, 0), hms, curses.A_BOLD)
        stdscr.addstr(
            h - 2, 2, "Press any key to exit stopwatch", curses.A_DIM)
        stdscr.refresh()
        if stdscr.getch() != -1:
            break
        time.sleep(1)

# ——— Stop Timer ———


def stop_time_tui(stdscr):
    """
    Stop the current active timer via TUI.
    """
    active = time_repository.get_active_time_entry()
    if not active:
        popup_confirm(stdscr, "No active timer.")
        return

    # Prompt for updated tags/notes
    tags = popup_input(
        stdscr, f"Tags (comma, optional) [{active.tags or ''}]:")
    notes = popup_multiline_input(
        stdscr, f"Notes (optional) [{active.notes or ''}]:")
    past = popup_input(stdscr, "End time (e.g. '5m ago') [optional]:")
    try:
        end_dt = parse_date_string(past) if past else now_utc()
    except Exception as e:
        popup_confirm(stdscr, f"Invalid time: {e}")
        return

    # Stop in repository
    try:
        updated = time_repository.stop_active_time_entry(
            end_time=end_dt,
            tags=tags or None,
            notes=notes or None
        )
    except Exception as e:
        popup_confirm(stdscr, f"Failed to stop timer: {e}")
        return

    # Calculate durations
    start_dt = active.start
    if isinstance(start_dt, datetime):
        mins = round((end_dt - start_dt).total_seconds() / 60, 2)
    else:
        mins = 0.0
    distracted = getattr(updated, 'distracted_minutes', 0) or 0
    focus = max(0, mins - distracted)
    popup_confirm(
        stdscr,
        f"⏹️ Stopped. {mins} min on '{active.title}' "
        f"(Distracted: {distracted} min, Focus: {focus} min)"
    )


def view_time_entry_tui(stdscr, sel):
    """
    Show details of a time entry.
    """
    try:
        logs = time_repository.get_all_time_logs(
            since=now_utc() - timedelta(days=365))
    except Exception as e:
        popup_show(stdscr, [f"Error fetching logs: {e}"], title="Error")
        return

    if not (0 <= sel < len(logs)):
        popup_show(stdscr, [f"Invalid selection {sel}"], title="Error")
        return
    entry = logs[sel]
    # Format start/end as strings if datetime
    if isinstance(entry.start, datetime):
        start_str = entry.start.strftime("%Y-%m-%d %H:%M")
    else:
        start_str = str(entry.start or "-")
    if isinstance(entry.end, datetime):
        end_str = entry.end.strftime("%Y-%m-%d %H:%M")
    else:
        end_str = str(entry.end or "-")
    duration = int(entry.duration_minutes or 0)
    distracted = getattr(entry, 'distracted_minutes', 0) or 0

    lines = [
        f"Title:      {entry.title or '-'}",
        f"Category:   {entry.category or '-'}",
        f"Project:    {entry.project or '-'}",
        f"Tags:       {entry.tags or '-'}",
        f"Notes:      {entry.notes or '-'}",
        f"Start:      {start_str}",
        f"End:        {end_str}",
        f"Duration:   {duration} min",
        f"Distracted: {distracted} min"
    ]

    popup_show(stdscr, lines, title=f" Entry #{entry.id} ")


def status_time_tui(stdscr):
    """
    Show status of current active timer.
    """
    active = time_repository.get_active_time_entry()
    if not active:
        popup_show(stdscr, ["No active timer."], title=" Status ")
        return

    start_dt = active.start
    if isinstance(start_dt, datetime):
        elapsed = now_utc() - start_dt
        mins = round(elapsed.total_seconds() / 60, 2)
    else:
        mins = 0.0
    distracted = getattr(active, 'distracted_minutes', 0) or 0
    focus = max(0, mins - distracted)
    if isinstance(start_dt, datetime):
        start_str = start_dt.strftime("%Y-%m-%d %H:%M")
    else:
        start_str = str(start_dt or "-")
    lines = [
        f"Title:      {active.title or '-'}",
        f"Since:      {start_str}",
        f"Elapsed:    {mins} min",
        f"Distracted: {distracted} min",
        f"Focus:      {focus} min"
    ]
    if active.category:
        lines.insert(1, f"Category:   {active.category}")
    if active.project:
        insert_idx = 2 if active.category else 1
        lines.insert(insert_idx, f"Project:    {active.project}")
    popup_show(stdscr, lines, title=" Status ")


def summary_time_tui(stdscr):
    """
    Show summary grouping time by a chosen field in TUI.
    """
    by = popup_input(stdscr, "Group by [title/category/project]:") or "title"
    by = by.strip().lower()
    if by not in ("title", "category", "project"):
        popup_show(stdscr, [
                   f"Invalid group field: {by}. Must be title, category, or project."], title="Error")
        return

    period = popup_input(stdscr, "Period [day/week/month/all]:") or "week"
    period = period.strip().lower()
    now = now_utc()
    if period == "day":
        since = now - timedelta(days=1)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        # treat 'all' or invalid as all time
        since = now - timedelta(days=365*10)

    try:
        logs = time_repository.get_all_time_logs(since=since)
    except Exception as e:
        popup_show(stdscr, [f"Error fetching logs: {e}"], title="Error")
        return

    totals = {}
    distracted_totals = {}
    for r in logs:
        key = getattr(r, by, None) or "(none)"
        duration = r.duration_minutes or 0
        distracted = getattr(r, 'distracted_minutes', 0) or 0
        focus = max(0, duration - distracted)
        totals[key] = totals.get(key, 0) + focus
        distracted_totals[key] = distracted_totals.get(key, 0) + distracted

    if not totals:
        popup_show(stdscr, ["No records found."], title=" Summary ")
        return

    # Build lines: header + rows
    lines = [f"{by.capitalize():<15} Focus   Distracted"]
    for k, v in sorted(totals.items(), key=lambda x: -x[1]):
        dist = distracted_totals.get(k, 0)
        lines.append(f"{k[:15]:<15}{_format_duration(v):>8}   {dist:>4}min")
    popup_show(stdscr, lines, title=" Summary ")
