
# -------------------------------------------------------------------
# Time view
# -------------------------------------------------------------------
import curses
from datetime import datetime, timedelta
import time
from lifelog.utils.db.models import TimeLog
from lifelog.utils.db import time_repository
from lifelog.utils.shared_utils import add_category_to_config, add_project_to_config, get_available_categories, get_available_projects, parse_date_string
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
    if minutes >= 60:
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours} hr {mins} min"
    else:
        return f"{int(minutes)} min"


def get_since_from_period(period):
    now = datetime.now()
    if period == 'day':
        return now - timedelta(days=1)
    elif period == 'week':
        return now - timedelta(days=7)
    elif period == 'month':
        return now - timedelta(days=30)
    else:
        return now - timedelta(days=365*10)


def draw_time(pane, h, w, selected_idx):
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
        safe_addstr(pane, 0, max((max_w - len(title)) // 2, 1),
                    title, curses.A_BOLD)

        y = 2
        active = time_repository.get_active_time_entry()
        if active:
            start_dt = active.start
            elapsed = (datetime.now() - start_dt).total_seconds() // 60
            safe_addstr(pane,
                        y, 2, f"▶ {active.title} ({int(elapsed)} min)", curses.A_BOLD)
            y += 2

        since = get_since_from_period(period)
        logs = time_repository.get_all_time_logs(since=since)
        n = len(logs)
        if n == 0:
            safe_addstr(pane, y, 2, "(no history)")
            pane.noutrefresh()
            return 0

        selected_idx = max(0, min(selected_idx, n-1))
        visible_rows = max_h - y - 2
        start = max(0, selected_idx - visible_rows // 2)
        end = min(start + visible_rows, n)
        for i, r in enumerate(logs[start:end], start=start):
            m = int(r.duration_minutes or 0)
            line = f"{r.id:>2} {r.title[:20]:20} {m:>4} min"
            row_y = y + i - start
            if row_y < max_h - 1:
                attr = curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
                safe_addstr(pane, row_y, 2, line[:max_w-4], attr)
        pane.noutrefresh()
        return selected_idx
    except Exception as e:
        safe_addstr(pane, h-2, 2, f"Time err: {e}", curses.A_BOLD)
        pane.noutrefresh()
        return 0


# ——— Start Timer ———


def start_time_tui(stdscr):
    title = popup_input(stdscr, "Activity Title:")
    if not title:
        return

    cat = popup_select_option(
        stdscr, "Category:", get_available_categories(), allow_new=True)
    if cat and cat not in get_available_categories():
        add_category_to_config(cat)

    proj = popup_select_option(
        stdscr, "Project:", get_available_projects(), allow_new=True)
    if proj and proj not in get_available_projects():
        add_project_to_config(proj)

    tags = popup_input(stdscr, "Tags (comma, optional):")
    notes = popup_multiline_input(stdscr, "Notes (optional):")
    task_id = popup_input(stdscr, "Attach to task ID [optional]:")

    past = popup_input(stdscr, "Start time (e.g. '30m ago') [optional]:")
    try:
        start_dt = parse_date_string(past) if past else datetime.now()
    except Exception as e:
        popup_confirm(stdscr, f"Invalid time: {e}")
        return

    log = TimeLog(
        title=title,
        start=start_dt,
        category=cat or None,
        project=proj or None,
        tags=tags or None,
        notes=notes or None,
        task_id=int(task_id) if task_id else None
    )

    time_repository.start_time_entry(log)
    popup_confirm(stdscr, f"Started '{title}'")


def add_manual_time_entry_tui(_stdscr=None):
    """
    Launches the TimeEntryForm for manual time entry.
    """
    entry_data = run_form(TimeEntryForm)
    if not entry_data:
        return
    try:
        # Parse times
        start_dt = parse_date_string(entry_data["start"]) if entry_data.get(
            "start") else datetime.now()
        end_dt = parse_date_string(
            entry_data["end"]) if entry_data.get("end") else None
        distracted = float(entry_data.get("distracted") or 0)
        duration = (end_dt - start_dt).total_seconds() / 60 if end_dt else None

        log = TimeLog(
            title=entry_data["title"],
            category=entry_data.get("category"),
            project=entry_data.get("project"),
            tags=entry_data.get("tags"),
            notes=entry_data.get("notes"),
            task_id=int(entry_data.get("task_id")) if entry_data.get(
                "task_id") else None,
            start=start_dt,
            end=end_dt,
            duration_minutes=duration,
            distracted_minutes=distracted
        )
        time_repository.add_time_entry(log)
        # npyscreen's notify_confirm is best for feedback, since we're using forms now
        import npyscreen
        npyscreen.notify_confirm(
            f"Time entry '{log.title}' added", title="Success")
    except Exception as e:
        import npyscreen
        npyscreen.notify_confirm(f"Error: {e}", title="Time Entry Error")


def edit_time_entry_tui(_stdscr, sel):
    logs = time_repository.get_all_time_logs(
        since=datetime.now()-timedelta(days=365))
    entry = logs[sel]

    # Pre-fill form with existing entry data
    class App(npyscreen.NPSAppManaged):
        def onStart(selfx):
            form = selfx.addForm("MAIN", TimeEntryForm, name="Edit Time Entry")
            form.title.value = entry.title
            form.category.value = entry.category
            form.project.value = entry.project
            form.tags.value = entry.tags or ""
            if hasattr(form.notes, "values"):
                form.notes.values = entry.notes.splitlines() if entry.notes else [
                    ""]
            else:
                form.notes.value = entry.notes or ""
            form.task_id.value = str(entry.task_id) if entry.task_id else ""
            form.start.value = entry.start.strftime(
                "%Y-%m-%d %H:%M") if entry.start else ""
            form.end.value = entry.end.strftime(
                "%Y-%m-%d %H:%M") if entry.end else ""
            form.distracted.value = str(entry.distracted_minutes or "")

    app = App()
    app.run()
    new_data = getattr(app, 'form_data', None)
    if not new_data:
        return

    try:
        start_dt = parse_date_string(
            new_data["start"]) if new_data.get("start") else entry.start
        end_dt = parse_date_string(
            new_data["end"]) if new_data.get("end") else entry.end
        distracted = float(new_data.get("distracted") or 0)
        time_repository.update_time_entry(
            entry.id,
            title=new_data["title"],
            category=new_data.get("category"),
            project=new_data.get("project"),
            tags=new_data.get("tags"),
            notes=new_data.get("notes"),
            task_id=int(new_data.get("task_id")) if new_data.get(
                "task_id") else None,
            start=start_dt,
            end=end_dt,
            distracted_minutes=distracted,
            duration_minutes=(end_dt - start_dt).total_seconds() /
            60 if start_dt and end_dt else entry.duration_minutes
        )
        import npyscreen
        npyscreen.notify_confirm(f"Updated entry #{entry.id}", title="Updated")
    except Exception as e:
        import npyscreen
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
        popup_show(stdscr, [f"Invalid: {e}"])
        return
    active = time_repository.get_active_time_entry()
    if not active:
        popup_show(stdscr, ["No active timer to add distraction to."])
        return
    new_distracted = time_repository.add_distracted_minutes_to_active(mins)
    popup_show(stdscr, [
               f"Added {mins} distracted min (Total distracted: {new_distracted} min)"])


def delete_time_entry_tui(stdscr, sel):
    logs = time_repository.get_all_time_logs(
        since=datetime.now()-timedelta(days=365))
    entry = logs[sel]
    if popup_confirm(stdscr, f"Delete entry #{entry.id}?"):
        try:
            time_repository.delete_time_entry(entry.id)
            popup_show(stdscr, [f"Deleted #{entry.id}"])
        except Exception as e:
            popup_show(stdscr, [f"Error: {e}"])


def stopwatch_tui(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    h, w = stdscr.getmaxyx()
    active = time_repository.get_active_time_entry()
    if not active or not active.start:
        stdscr.addstr(h//2, (w-20)//2, "⚠️ No active timer ⚠️", curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()
        return

    start = active.start

    while True:
        stdscr.erase()
        elapsed = datetime.now() - start
        hms = str(elapsed).split(".")[0]
        stdscr.addstr(h//2, (w - len(hms))//2, hms, curses.A_BOLD)
        stdscr.addstr(
            h - 2, 2, "Press any key to exit stopwatch", curses.A_DIM)
        stdscr.refresh()
        if stdscr.getch() != -1:
            break
        time.sleep(1)

# ——— Stop Timer ———


def stop_time_tui(stdscr):
    active = time_repository.get_active_time_entry()
    if not active:
        popup_confirm(stdscr, "No active timer.")
        return

    tags = popup_input(
        stdscr, f"Tags (comma, optional) [{active.tags or ''}]:")
    notes = popup_multiline_input(
        stdscr, f"Notes (optional) [{active.notes or ''}]:")
    past = popup_input(stdscr, "End time (e.g. '5m ago') [optional]:")
    try:
        end_dt = parse_date_string(past) if past else datetime.now()
    except Exception as e:
        popup_confirm(stdscr, f"Invalid time: {e}")
        return

    updated = time_repository.stop_active_time_entry(
        end_time=end_dt,
        tags=tags or None,
        notes=notes or None
    )
    distracted = getattr(updated, 'distracted_minutes', 0) or 0
    mins = round((end_dt - active.start).total_seconds() / 60, 2)
    focus = max(0, mins - distracted)
    popup_confirm(
        stdscr, f"⏹️ Stopped. {mins} min on '{active.title}' (Distracted: {distracted} min, Focus: {focus} min)")


def view_time_entry_tui(stdscr, sel):
    logs = time_repository.get_all_time_logs(
        since=datetime.now()-timedelta(days=365))
    entry = logs[sel]
    lines = [
        f"Title:    {entry.title or '-'}",
        f"Category: {entry.category or '-'}",
        f"Project:  {entry.project or '-'}",
        f"Tags:     {entry.tags or '-'}",
        f"Notes:    {entry.notes or '-'}",
        f"Start:    {entry.start or '-'}",
        f"End:      {entry.end or '-'}",
        f"Duration: {int(entry.duration_minutes or 0)} min",
        f"Distracted: {getattr(entry, 'distracted_minutes', 0) or 0} min"
    ]

    popup_show(stdscr, lines, title=f" Entry #{entry.id} ")


def status_time_tui(stdscr):
    active = time_repository.get_active_time_entry()
    if not active:
        popup_show(stdscr, ["No active timer."], title=" Status ")
        return

    elapsed = datetime.now() - active.start
    mins = round(elapsed.total_seconds() / 60, 2)
    distracted = getattr(active, 'distracted_minutes', 0) or 0
    focus = max(0, mins - distracted)
    lines = [
        f"Title:   {active.title}",
        f"Since:   {active.start.strftime('%Y-%m-%d %H:%M')}",
        f"Elapsed: {mins} min",
        f"Distracted: {distracted} min",
        f"Focus: {focus} min"
    ]
    if active.category:
        lines.insert(1, f"Category: {active.category}")
    if active.project:
        lines.insert(2, f"Project:  {active.project}")
    popup_show(stdscr, lines, title=" Status ")


def summary_time_tui(stdscr):
    by = popup_input(stdscr, "Group by [title/category/project]:") or "title"
    period = popup_input(stdscr, "Period [day/week/month/all]:") or "week"
    now = datetime.now()
    if period == "day":
        since = now - timedelta(days=1)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(days=365*10)

    logs = time_repository.get_all_time_logs(since=since)
    totals = {}
    for r in logs:
        key = getattr(r, by, None) or "(none)"
        totals[key] = totals.get(key, 0) + (r.duration_minutes or 0)
    if not totals:
        popup_show(stdscr, ["No records found."], title=" Summary ")
        return

    lines = [f"{by.capitalize():<15}Total"]
    for k, v in sorted(totals.items(), key=lambda x: -x[1]):
        lines.append(f"{k[:15]:<15}{_format_duration(v)}")
    popup_show(stdscr, lines, title=" Summary ")
