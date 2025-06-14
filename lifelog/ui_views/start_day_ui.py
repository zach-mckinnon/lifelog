import os
import time
import curses
import npyscreen
from datetime import datetime, timedelta, timezone
from lifelog.commands.environmental_sync import fetch_today_forecast
from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, time_repository
from lifelog.ui_views.popups import popup_show, popup_input, popup_confirm, popup_error
from lifelog.ui_views.tasks_ui import countdown_timer_ui
from lifelog.utils.shared_utils import format_datetime_for_user, now_utc, utc_iso_to_local
from lifelog.utils.db.gamify_repository import modify_pomodoro_lengths
from lifelog.utils.hooks import run_hooks

# Minimum terminal size to avoid curses errors
MIN_LINES, MIN_COLS = 10, 40
OVERLOAD_THRESHOLD = int(os.getenv("LIFELOG_OVERLOAD_THRESHOLD", "480"))


def tui_continue(stdscr, msg: str = "Press any key to continue…") -> None:
    stdscr.addstr(curses.LINES - 1, 1, msg[:curses.COLS-2], curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def tui_confirm(stdscr, prompt: str, default: bool = False) -> bool:
    try:
        return popup_confirm(stdscr, prompt, default=default)
    except Exception:
        popup_error(stdscr, "Confirmation failed.")
        return default


def tui_input_int(stdscr, prompt: str, default: int) -> int:
    try:
        s = popup_input(
            stdscr, f"{prompt} [default {default}]", default=str(default))
        return int(s) if s and s.isdigit() else default
    except Exception:
        popup_error(stdscr, "Invalid number — using default.")
        return default


def get_weather_service():
    return fetch_today_forecast


def start_day_tui(stdscr):
    # Ensure minimum size
    lines, cols = stdscr.getmaxyx()
    if lines < MIN_LINES or cols < MIN_COLS:
        popup_error(
            stdscr, f"Terminal too small: need ≥{MIN_COLS}×{MIN_LINES}")
        return

    # 1. Motivation
    quote = get_motivational_quote()
    popup_show(stdscr, [quote], title="🌞 Start Your Day!")

    # 1a. Weather
    show_today_weather_tui(stdscr)

    # 2. Task selection
    tasks = select_tasks_for_today(stdscr)
    if not tasks:
        return

    # 3. Time plan
    plan = ask_time_for_tasks(stdscr, tasks)

    # 4. Overload warning
    total = sum(item["minutes"] for item in plan)
    if total > OVERLOAD_THRESHOLD:
        popup_show(
            stdscr, [f"⚠️ {total} min planned (> {OVERLOAD_THRESHOLD})"], title="Overload")

    # 5. Initial tracker logs
    log_initial_trackers(stdscr)

    # 6. Pomodoro loop
    for idx, item in enumerate(plan, start=1):
        task = item["task"]
        mins = item["minutes"]

        # Announce start of focus block
        popup_show(
            stdscr,
            [f"Task {idx}/{len(plan)}: {task.title}", f"{mins} min focus"],
            title="Start Task"
        )
        tty_continue = tui_continue  # alias

        # Run the focus and makeup sessions
        distracted = run_pomodoro_tui(stdscr, mins)
        run_makeup_tui(stdscr, distracted)

        # After focus ends, show a fun transition quote
        transition_quote = get_feedback_saying("transition_break")
        popup_show(
            stdscr,
            [transition_quote],
            title="💬 Take Five!"
        )
        tui_continue(stdscr)  # wait for user to absorb it

        # Notes & between-task trackers
        record_task_notes_tui(stdscr, task, mins)
        log_between_tasks(stdscr)

        # If there’s another task coming up, show its title
        if idx < len(plan):
            popup_show(
                stdscr,
                [f"Next up: {plan[idx]['task'].title}"],
                title="🔜 On Deck"
            )
            tui_continue(stdscr)

    # 7. End-of-day
    feedback = get_feedback_saying("end_of_day")
    popup_show(stdscr, [feedback], title="🎉 Day Complete!")


def show_today_weather_tui(stdscr):
    """
    Fetch today’s forecast, convert each timestamp to local time,
    format as MM/DD/YY HH:MM, and display.
    """
    try:
        env = __import__("lifelog.utils.db.environment_repository", fromlist=[""])\
            .get_latest_environment_data("weather")
    except Exception:
        env = None

    if not env:
        popup_show(
            stdscr, ["No weather data — run sync first"], title="Weather")
        return

    lat, lon = env.get("latitude"), env.get("longitude")
    if lat is None or lon is None:
        popup_error(stdscr, "Incomplete location data")
        return

    try:
        forecast = fetch_today_forecast(lat, lon)
    except Exception as e:
        popup_error(stdscr, f"Weather fetch error: {e}")
        return

    if not forecast:
        popup_show(stdscr, ["No forecast available today."], title="Weather")
        return

    lines = ["Today's forecast (4 h intervals):"]
    for entry in forecast:
        # Parse the full UTC ISO string, convert to local tz, then format
        local_dt = utc_iso_to_local(entry["time"])
        time_str = format_datetime_for_user(local_dt)
        temp = f"{entry['temperature']:.1f}°C" if isinstance(
            entry["temperature"], float) else f"{entry['temperature']}°C"
        pop = f"{entry['precip_prob']}%" if entry['precip_prob'] is not None else "-"
        lines.append(
            f"{time_str} — {temp}, Precip {pop}, {entry['description']}")

    popup_show(stdscr, lines, title="🌤️ Forecast")


def select_tasks_for_today(stdscr):
    try:
        all_tasks = task_repository.query_tasks(
            show_completed=False, sort="priority")
    except Exception:
        popup_error(stdscr, "Failed loading tasks")
        return None
    if not all_tasks:
        popup_show(stdscr, ["No tasks found."], title="Start Day")
        return None

    prompt = ["Select tasks (comma-separated):"]
    for i, t in enumerate(all_tasks, 1):
        prompt.append(f"{i}. {t.title}")
    sel = popup_input(stdscr, "\n".join(prompt))
    if not sel:
        return None

    chosen = []
    for part in sel.split(","):
        if not part.strip().isdigit():
            popup_error(stdscr, f"Invalid choice: {part}")
            return None
        idx = int(part) - 1
        if idx < 0 or idx >= len(all_tasks):
            popup_error(stdscr, f"Out of range: {part}")
            return None
        chosen.append(all_tasks[idx])
    return chosen


def ask_time_for_tasks(stdscr, tasks):
    plan = []
    for t in tasks:
        mins = tui_input_int(stdscr, f"Minutes for {t.title}?", 25)
        plan.append({"task": t, "minutes": mins})
    return plan


def log_initial_trackers(stdscr):
    """
    For each tracker in the repo, ask the user if they want to log it now.
    If yes, prompt for a value and record the entry with a UTC timestamp.
    """
    try:
        trackers = track_repository.get_all_trackers()
    except Exception:
        popup_error(stdscr, "Failed loading trackers")
        return

    for tr in trackers:
        if popup_confirm(stdscr, f"Log '{tr.title}' now?", default=False):
            val = popup_input(stdscr, f"Value for {tr.title}:", default="")
            if val:
                try:
                    track_repository.add_tracker_entry(
                        tracker_id=tr.id,
                        timestamp=now_utc().isoformat(),
                        value=val
                    )
                    run_hooks("tracker", "logged", {
                        "tracker_id": tr.id,
                        "timestamp": now_utc().isoformat(),
                        "value": val
                    })
                except Exception:
                    popup_error(stdscr, f"Failed logging {tr.title}")


def run_pomodoro_tui(stdscr, total_minutes):
    base_focus, base_break = (25, 5) if total_minutes <= 120 else (45, 10)
    focus, brk = modify_pomodoro_lengths(base_focus, base_break)
    sessions = (total_minutes + focus - 1) // focus
    distracted = 0
    for s in range(sessions):
        popup_show(
            stdscr, [f"Pomodoro {s+1}/{sessions}", f"{focus} min focus"], "Focus")
        start = time.time()
        completed = countdown_timer_ui(stdscr, focus*60, title="Focus")
        elapsed = int((time.time() - start)/60)
        elapsed = min(elapsed, focus)
        if completed:
            extra = tui_input_int(stdscr, "Distracted minutes?", 0)
        else:
            prompt = f"Actual focus minutes (≤{focus})?"
            actual = tui_input_int(stdscr, prompt, elapsed)
            extra = focus - actual
        distracted += extra
        if s < sessions - 1:
            # Show an automatic break timer instead of a static popup
            countdown_timer_ui(stdscr, brk * 60, title="Break Time")
            # Optionally give a “break’s over” message
            popup_show(
                stdscr, [f"Break’s over—back to work!"], title="💪 Ready?")
    return distracted


def run_makeup_tui(stdscr, total_distracted, focus_len=25, break_len=None):
    if total_distracted <= 0:
        return
    sessions = (total_distracted + focus_len - 1) // focus_len
    rem = total_distracted
    for i in range(sessions):
        session_time = min(focus_len, rem)
        popup_show(stdscr, [f"Makeup {i+1}/{sessions}",
                   f"{session_time} min focus"], "Makeup")
        completed = countdown_timer_ui(stdscr, session_time*60, title="Makeup")
        if not completed:
            actual = tui_input_int(
                stdscr, f"Actual focus (≤{session_time})?", 0)
            rem -= actual
        else:
            rem -= session_time
        if break_len and rem > 0:
            popup_show(stdscr, [f"{break_len} min break"], "Break")


def record_task_notes_tui(stdscr, task, minutes):
    """
    Prompt the user for free-form notes on a just-completed focus period,
    then start+stop a time entry in UTC based on those notes and the focus length.
    """
    notes = popup_input(stdscr, "Notes? (blank to skip):", default="")
    if not notes:
        return

    try:
        # Capture the start time in UTC
        start_dt_utc = now_utc()
        time_repository.start_time_entry(
            title=task.title,
            task_id=task.id,
            start_time=start_dt_utc.isoformat(),
            project=getattr(task, "project", None),
            notes=notes
        )

        # Compute the end time in UTC
        end_dt_utc = start_dt_utc + timedelta(minutes=minutes)
        time_repository.stop_active_time_entry(
            end_time=end_dt_utc.isoformat()
        )
    except Exception:
        popup_error(stdscr, "Failed logging notes")


def log_between_tasks(stdscr):
    """
    After one focus session ends and before the next begins, offer to log
    any tracker values now, using UTC timestamps for storage.
    """
    try:
        trackers = track_repository.get_all_trackers()
    except Exception:
        return

    for tr in trackers:
        if popup_confirm(stdscr, f"Log '{tr.title}' now?", default=False):
            val = popup_input(stdscr, f"Value for {tr.title}:", default="")
            if val:
                try:
                    track_repository.add_tracker_entry(
                        tracker_id=tr.id,
                        timestamp=now_utc().isoformat(),
                        value=val
                    )
                    run_hooks("tracker", "logged", {
                        "tracker_id": tr.id,
                        "timestamp": now_utc().isoformat(),
                        "value": val
                    })
                except Exception:
                    popup_error(stdscr, f"Failed logging {tr.title}")
