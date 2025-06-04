
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
        period = get_time_period()
        period_title = {
            'day': ' (last 24h)',
            'week': ' (last 7 days)',
            'month': ' (last 30 days)',
            'all': ' (all time)'
        }.get(period, '')
        safe_addstr(pane, 0, max((max_w - 13) // 2, 1),
                    f" Time {period_title} ", curses.A_BOLD)

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


def add_manual_time_entry_tui(stdscr):
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

    start_str = popup_input(
        stdscr, "Start time (e.g. '2025-05-28T14:00' or '1h ago'):")
    end_str = popup_input(
        stdscr, "End time (e.g. '2025-05-28T15:00' or 'now'):")
    distracted_str = popup_input(stdscr, "Distracted minutes [optional]:")
    distracted = float(distracted_str) if distracted_str else 0

    try:
        start_dt = parse_date_string(start_str)
        end_dt = parse_date_string(end_str)
        if end_dt <= start_dt:
            popup_show(stdscr, ["End time must be after start time!"])
            return
    except Exception as e:
        popup_show(stdscr, [f"Invalid time: {e}"])
        return

    log = TimeLog(
        title=title,
        start=start_dt,
        end=end_dt,
        category=cat or None,
        project=proj or None,
        tags=tags or None,
        notes=notes or None,
        task_id=int(task_id) if task_id else None,
        duration_minutes=(end_dt - start_dt).total_seconds() / 60,
        distracted_minutes=distracted
    )

    try:
        time_repository.add_time_entry(log)
        popup_show(stdscr, [f"Time entry '{title}' added"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


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


def edit_time_entry_tui(stdscr, sel):
    logs = time_repository.get_all_time_logs(
        since=datetime.now()-timedelta(days=365))
    entry = logs[sel]
    new_tags = popup_input(stdscr, f"Tags [{entry.tags or '-'}]:")
    new_notes = popup_multiline_input(stdscr, f"Notes [{entry.notes or '-'}]:")
    new_distracted_str = popup_input(
        stdscr, f"Distracted minutes [{entry.distracted_minutes or 0}]:")
    try:
        new_distracted = float(
            new_distracted_str) if new_distracted_str else entry.distracted_minutes or 0
        time_repository.update_time_entry(
            entry.id,
            tags=new_tags or None,
            notes=new_notes or None,
            distracted_minutes=new_distracted
        )
        popup_show(stdscr, [f"Updated entry #{entry.id}"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])

    try:
        time_repository.update_time_entry(
            entry.id, tags=new_tags or None, notes=new_notes or None)
        popup_show(stdscr, [f"Updated entry #{entry.id}"])
    except Exception as e:
        popup_show(stdscr, [f"Error: {e}"])


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
