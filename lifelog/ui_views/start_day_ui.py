import os
import curses
from datetime import datetime, timedelta, timezone

from lifelog.commands.environmental_sync import fetch_today_forecast
from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, environment_repository
from lifelog.ui_views.popups import popup_show, popup_input, popup_confirm, popup_error
from lifelog.ui_views.tasks_ui import countdown_timer_ui
from lifelog.utils.shared_utils import now_utc, utc_iso_to_local, format_datetime_for_user
from lifelog.utils.db.gamify_repository import modify_pomodoro_lengths
from lifelog.utils.hooks import run_hooks

MIN_LINES, MIN_COLS = 10, 40
OVERLOAD_THRESHOLD = int(os.getenv("LIFELOG_OVERLOAD_THRESHOLD", "480"))

# ──────────────────────────────────────────────────────────────────────────────
# Utility wrappers that respect screen size
# ──────────────────────────────────────────────────────────────────────────────


def _get_dims(stdscr):
    """Return usable (height, width) inside a small border."""
    h, w = stdscr.getmaxyx()
    return max(1, h - 4), max(1, w - 4)


def safe_show(stdscr, lines, title=""):
    """
    Trim each line to the current width, and limit number of lines
    to the current height, then call popup_show.
    """
    max_h, max_w = _get_dims(stdscr)
    safe = [ln[:max_w] for ln in lines][:max_h]
    popup_show(stdscr, safe, title=title)


def safe_input(stdscr, prompt, default=""):
    """
    Trim prompt to width before calling popup_input.
    """
    _, max_w = _get_dims(stdscr)
    p = prompt[:max_w]
    return popup_input(stdscr, p, default=p[:max_w] if default else "")


def safe_confirm(stdscr, prompt, default=False):
    """
    Trim prompt to width before calling popup_confirm.
    """
    _, max_w = _get_dims(stdscr)
    p = prompt[:max_w]
    return popup_confirm(stdscr, p, default=default)


def tui_continue(stdscr, msg="Press any key to continue…"):
    """Show a one-line prompt at the bottom and wait."""
    h, w = stdscr.getmaxyx()
    stdscr.addstr(h - 1, 1, msg[:w-2], curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def tui_input_int(stdscr, prompt, default):
    """Prompt for an int, safely truncated."""
    s = safe_input(
        stdscr, f"{prompt} [default {default}]", default=str(default))
    try:
        return int(s)
    except Exception:
        popup_error(stdscr, "Invalid number — using default.")
        return default

# ──────────────────────────────────────────────────────────────────────────────
# Main TUI Flow
# ──────────────────────────────────────────────────────────────────────────────


def start_day_tui(stdscr):
    # enforce minimum size
    lines, cols = stdscr.getmaxyx()
    if lines < MIN_LINES or cols < MIN_COLS:
        popup_error(
            stdscr, f"Terminal too small: need ≥{MIN_COLS}×{MIN_LINES}")
        return

    # 1) Motivation
    safe_show(stdscr, [get_motivational_quote()], title="🌞 Motivation")

    # 1a) Weather
    _show_weather_tui(stdscr)

    # 2) Task selection
    tasks = _select_tasks_tui(stdscr)
    if not tasks:
        return

    # 3) Time allocation
    plan = _ask_time_tui(stdscr, tasks)
    total = sum(item["minutes"] for item in plan)

    # 4) Overload warning
    if total > OVERLOAD_THRESHOLD:
        safe_show(
            stdscr,
            [f"⚠️ {total} min planned (>{OVERLOAD_THRESHOLD})"],
            title="Overload Warning"
        )
        tui_continue(stdscr)

    # 5) Initial trackers
    safe_show(stdscr, ["Log any trackers now"], title="Initial Trackers")
    _log_initial_trackers_tui(stdscr)

    # Prepare reminders
    session_start = datetime.now(timezone.utc)
    reminders = {"water": False, "lunch": False}

    # 6) Loop through each task
    for idx, item in enumerate(plan, start=1):
        task, minutes = item["task"], item["minutes"]

        # Announce the task
        safe_show(
            stdscr,
            [f"Task {idx}/{len(plan)}: {task.title}",
             f"{minutes} min total focus"],
            title="Start Task"
        )

        # Checklist step
        safe_show(
            stdscr,
            ["📝 Take 5 minutes to make a quick checklist of what you'll do."],
            title="Checklist Time"
        )
        tui_continue(stdscr)

        # Ready prompt
        safe_show(
            stdscr,
            [f"Ready to begin {minutes} min of focus on '{task.title}'?"],
            title="Ready to Focus"
        )
        tui_continue(stdscr)

        # Pomodoro sessions
        distracted = run_pomodoro_tui(stdscr, task, minutes)

        # Makeup sessions
        if distracted > 0:
            run_makeup_tui(stdscr, task, distracted)

        # Mark complete
        run_hooks("task", "completed", task)
        safe_show(stdscr, [f"✔️ Completed '{task.title}'"], title="Task Done")

        # After-task trackers & mood
        safe_show(stdscr, ["Log trackers & how you felt"], title="Post-Task")
        _log_initial_trackers_tui(stdscr)
        mood = safe_input(stdscr, "How did you feel?", default="")
        if mood:
            entry = track_repository.add_tracker_entry(
                tracker_id=None,
                timestamp=now_utc(),
                value=mood
            )
            run_hooks("tracker", "logged", entry)

        # Hydration & lunch reminders
        elapsed = datetime.now(timezone.utc) - session_start
        if elapsed >= timedelta(hours=2) and not reminders["water"]:
            if safe_confirm(stdscr, "🚰 Two hours in—grab water?", default=False):
                reminders["water"] = True
        if elapsed >= timedelta(hours=4) and not reminders["lunch"]:
            if safe_confirm(stdscr, "🍱 Four hours in—time for lunch?", default=False):
                reminders["lunch"] = True

        # Next task
        if idx < len(plan):
            safe_show(
                stdscr,
                [f"Next up: {plan[idx]['task'].title}"],
                title="Up Next"
            )
            tui_continue(stdscr)

    # 7) End-of-day report
    safe_show(stdscr, [get_feedback_saying("end_of_day")],
              title="🎉 Day Complete!")

# ──────────────────────────────────────────────────────────────────────────────
# Focus & Makeup Helpers
# ──────────────────────────────────────────────────────────────────────────────


def run_pomodoro_tui(stdscr, task, total_minutes: int) -> int:
    focus_base, break_base = (25, 5) if total_minutes <= 120 else (45, 10)
    focus, brk = modify_pomodoro_lengths(focus_base, break_base)
    sessions = (total_minutes + focus - 1) // focus
    distracted = 0

    for s in range(sessions):
        safe_show(
            stdscr,
            [f"Pomodoro {s+1}/{sessions}", f"{focus} min focus"],
            title="Focus Time"
        )
        completed = countdown_timer_ui(stdscr, focus * 60, title="Focus")
        run_hooks("task", "pomodoro_done", task)

        if completed:
            extra = tui_input_int(stdscr, "Distracted minutes?", 0)
        else:
            actual = tui_input_int(stdscr, f"Actual focus (≤{focus})?", focus)
            extra = focus - actual
        distracted += extra

        if s < sessions - 1:
            safe_show(stdscr, [f"{brk} min break"], title="Break Time")
            countdown_timer_ui(stdscr, brk * 60, title="Break")
            safe_show(stdscr, ["Break's over!"], title="💪 Ready?")
            tui_continue(stdscr)

    return distracted


def run_makeup_tui(stdscr, task, total_distracted: int, focus_len: int = 25):
    if total_distracted <= 0:
        return
    sessions = (total_distracted + focus_len - 1) // focus_len
    rem = total_distracted

    for m in range(sessions):
        safe_show(
            stdscr,
            [f"Makeup {m+1}/{sessions}", f"{min(rem, focus_len)} min focus"],
            title="Makeup"
        )
        completed = countdown_timer_ui(
            stdscr, min(rem, focus_len) * 60, title="Makeup")
        run_hooks("task", "pomodoro_done", task)

        if not completed:
            actual = tui_input_int(
                stdscr, f"Actual focus (≤{focus_len})?", focus_len)
            rem -= actual
        else:
            rem -= focus_len

        if rem > 0:
            safe_show(stdscr, ["Short break"], title="Break")
            tui_continue(stdscr)

# ──────────────────────────────────────────────────────────────────────────────
# Weather, Task, and Tracker Subroutines
# ──────────────────────────────────────────────────────────────────────────────


def _show_weather_tui(stdscr):
    try:
        env = environment_repository.get_latest_environment_data("weather")
    except Exception:
        env = None

    if not env:
        safe_show(
            stdscr, ["No weather data — run sync first"], title="Weather")
        return

    lat, lon = env.get("latitude"), env.get("longitude")
    if lat is None or lon is None:
        popup_error(stdscr, "Incomplete weather location data")
        return

    try:
        forecast = fetch_today_forecast(lat, lon)
    except Exception as e:
        popup_error(stdscr, f"Weather fetch error: {e}")
        return

    lines = [f"Forecast for {format_datetime_for_user(now_utc()).split()[0]}:"]
    for ent in forecast:
        local = utc_iso_to_local(ent["time"])
        lines.append(
            f"{format_datetime_for_user(local)} — {ent['temperature']}°C, "
            f"Precip {ent['precip_prob']}%, {ent['description']}"
        )
    safe_show(stdscr, lines, title="🌤️ Forecast")


def _select_tasks_tui(stdscr):
    tasks = task_repository.get_all_tasks()
    if not tasks:
        safe_show(stdscr, ["No tasks to select."], title="Tasks")
        return []
    prompt = ["Select tasks (e.g. 1,3):"]
    for i, t in enumerate(tasks, 1):
        prompt.append(f"{i}. {t.title}")
    sel = safe_input(stdscr, "\n".join(prompt))
    if not sel:
        return []
    chosen = []
    for part in sel.split(","):
        if part.strip().isdigit():
            idx = int(part.strip()) - 1
            if 0 <= idx < len(tasks):
                chosen.append(tasks[idx])
    return chosen


def _ask_time_tui(stdscr, tasks):
    plan = []
    for t in tasks:
        mins = tui_input_int(stdscr, f"Minutes for {t.title}?", 25)
        plan.append({"task": t, "minutes": mins})
    return plan


def _log_initial_trackers_tui(stdscr):
    trackers = track_repository.get_all_trackers()
    for tr in trackers:
        if popup_confirm(stdscr, f"Log '{tr.title}' now?", default=False):
            val = safe_input(stdscr, f"Value for {tr.title}:", default="")
            if val:
                entry = track_repository.add_tracker_entry(
                    tracker_id=tr.id,
                    timestamp=now_utc(),
                    value=val
                )
                run_hooks("tracker", "logged", entry)
