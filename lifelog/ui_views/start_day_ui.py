import time
import npyscreen
from datetime import datetime, timedelta
from lifelog.commands.environmental_sync import fetch_today_forecast
from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, time_repository
from lifelog.ui_views.popups import popup_show, popup_input, popup_confirm
from lifelog.utils.db import environment_repository
from lifelog.ui_views.tasks_ui import countdown_timer_ui
# If you have MultiSelect, import here or use a custom popup


def start_day_tui(stdscr):
    # 1. Motivation and Weather
    show_motivation(stdscr)

    show_today_weather(stdscr)
    # 2. Select tasks for today
    selected_tasks = select_tasks_for_today(stdscr)
    if not selected_tasks:
        return

    # 3. Ask time allocation per task
    plan = ask_time_for_tasks(stdscr, selected_tasks)

    # 4. Warn if overload
    warn_overload_if_needed(stdscr, plan)

    # 5. Initial tracker logs
    log_initial_trackers(stdscr)

    # 6. For each task: run Pomodoro flow, record notes, log trackers, transition
    run_tasks_with_pomodoro(stdscr, plan)

    # 7. End-of-day feedback
    show_end_of_day(stdscr)


def show_motivation(stdscr):
    """Display a motivational quote at the start of day."""
    quote = get_motivational_quote()
    popup_show(stdscr, [quote], title="🌞 Start Your Day!")


def show_today_weather(stdscr):
    """
    Retrieve saved location from environment data, fetch today's forecast,
    and display in a popup.
    """
    # Retrieve latest weather environment data to get lat/lon
    env = environment_repository.get_latest_environment_data("weather")
    if not env:
        popup_show(
            stdscr, ["No weather data available. Please sync environment."], title="Weather")
        return
    lat = env.get("latitude")
    lon = env.get("longitude")
    if lat is None or lon is None:
        popup_show(
            stdscr, ["Location missing in environment data."], title="Weather")
        return

    # Fetch and display forecast
    try:
        forecast_entries = fetch_today_forecast(lat, lon)
    except Exception as e:
        popup_show(stdscr, [f"Weather fetch error: {e}"], title="Weather")
        return

    if not forecast_entries:
        popup_show(
            stdscr, ["No forecast available for today."], title="Weather")
        return

    # Build lines for popup: include header and each entry
    lines = ["Today's forecast (every 4 hours):"]
    for entry in forecast_entries:
        # entry["time"] is "YYYY-MM-DDThh:MM"
        t_local = entry["time"][11:]  # "hh:MM"
        temp = entry["temperature"]
        precip = entry["precip_prob"]
        desc = entry["description"]
        # Format e.g. "04:00 — 15°C, Precip 10%, Clear sky"
        # Note: temperature is in °C by default from Open-Meteo
        if temp is None:
            temp_str = "-"
        else:
            # Format with one decimal if float
            temp_str = f"{temp:.1f}°C" if isinstance(
                temp, float) else f"{temp}°C"
        if precip is None:
            precip_str = "-"
        else:
            precip_str = f"{precip}%"
        lines.append(f"{t_local} — {temp_str}, Precip {precip_str}, {desc}")

    popup_show(stdscr, lines, title="🌤️ Today's Forecast")


def select_tasks_for_today(stdscr):
    """
    Present user with a list of available tasks (sorted by priority or due),
    let them select via comma-separated input, return list of Task instances.
    """
    # Fetch and sort tasks; here using priority ordering
    all_tasks = task_repository.query_tasks(
        show_completed=False, sort="priority")
    if not all_tasks:
        popup_show(stdscr, ["No tasks available!"], title="Start Day")
        return None

    # Build display lines with formatted due date
    from datetime import datetime
    task_lines = []
    for t in all_tasks:
        due_label = "N/A"
        if getattr(t, "due", None):
            if isinstance(t.due, datetime):
                due_label = t.due.strftime("%Y-%m-%d")
            else:
                try:
                    dt = datetime.fromisoformat(t.due)
                    due_label = dt.strftime("%Y-%m-%d")
                except Exception:
                    due_label = str(t.due)
        task_lines.append(f"{t.title} (Due: {due_label})")

    # Prompt
    prompt_lines = ["Select tasks for today (comma numbers, e.g., 1,3):"]
    for idx, desc in enumerate(task_lines, start=1):
        prompt_lines.append(f"{idx}. {desc}")
    selected = popup_input(stdscr, "\n".join(prompt_lines))
    if not selected:
        popup_show(stdscr, ["No tasks selected."], title="Start Day")
        return None

    # Parse selection robustly
    idx_list = []
    for part in selected.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ii = int(part) - 1
            if 0 <= ii < len(all_tasks):
                idx_list.append(ii)
            else:
                popup_show(
                    stdscr, [f"Selection out of range: {part}"], title="Error")
                return None
        except Exception:
            popup_show(stdscr, [f"Invalid selection: {part}"], title="Error")
            return None

    today_tasks = [all_tasks[i] for i in idx_list]
    return today_tasks


def ask_time_for_tasks(stdscr, tasks):
    """
    For each Task in tasks list, prompt “How many minutes?” (default 25).
    Return list of dicts: {"task": Task, "minutes": int}.
    """
    plan = []
    total = 0
    for t in tasks:
        # If popup_input supports default= param; if not, include default in prompt
        try:
            mins_str = popup_input(
                stdscr, f"How many minutes for '{t.title}'? [default 25]", default="25")
        except TypeError:
            mins_str = popup_input(
                stdscr, f"How many minutes for '{t.title}'? [default 25]")
        try:
            mins = int(mins_str) if mins_str else 25
        except Exception:
            mins = 25
        plan.append({"task": t, "minutes": mins})
        total += mins
    return plan


def warn_overload_if_needed(stdscr, plan):
    """Show warning if total planned minutes exceed threshold (e.g. 480)."""
    total_minutes = sum(item["minutes"] for item in plan)
    if total_minutes > 480:
        popup_show(
            stdscr, ["⚠️ Over 8 hours planned! Consider reducing."], title="Overload")


def log_initial_trackers(stdscr):
    """
    Prompt user at start of day: for each tracker, ask if they want to log now.
    """
    from datetime import datetime
    trackers = track_repository.get_all_trackers()
    for tr in trackers:
        if popup_confirm(stdscr, f"Log '{tr.title}' now?"):
            value = popup_input(stdscr, f"Enter value for {tr.title}:")
            if value is not None:
                track_repository.add_tracker_entry(
                    tracker_id=tr.id,
                    timestamp=datetime.now().isoformat(),
                    value=value
                )


def run_tasks_with_pomodoro(stdscr, plan):
    """
    For each item in plan ({"task": Task, "minutes": int}), run:
      - Automated Pomodoro sessions with countdown
      - Makeup sessions using same focus_len
      - End-of-task notes entry
      - Tracker logs between tasks
      - Transition prompt
    """
    from datetime import datetime, timedelta
    trackers = track_repository.get_all_trackers()

    for i, item in enumerate(plan):
        task = item["task"]
        minutes = item["minutes"]

        # Decide Pomodoro lengths
        if minutes > 120:
            focus_len, break_len = 45, 10
        else:
            focus_len, break_len = 25, 5

        # Show initial info
        popup_show(
            stdscr,
            [f"Task: {task.title}\n{focus_len}min focus / {break_len}min break"],
            title=f"Task {i+1}/{len(plan)}"
        )

        # Run focus/break sessions
        total_distracted = run_pomodoro_sessions(
            stdscr, task, minutes, focus_len, break_len)

        # Run makeup sessions if needed, using same focus_len and break_len
        run_makeup_sessions_ui(stdscr, total_distracted, focus_len, break_len)

        # End-of-task notes
        record_task_notes(stdscr, task, minutes)

        # Tracker logs between tasks
        log_between_tasks(stdscr, trackers)

        # Transition to next task
        if i < len(plan) - 1:
            next_task = plan[i+1]["task"]
            popup_show(
                stdscr,
                [f"Transition: Next is {next_task.title}. Take 5 min, press key when ready."],
                title="Transition"
            )


def run_pomodoro_sessions(stdscr, task, total_minutes, focus_len, break_len):
    """
    Loop through Pomodoro sessions with automated countdown.
    Track actual elapsed focus time; compute distracted minutes per session.
    """
    sessions = (total_minutes + focus_len - 1) // focus_len
    mins_left = total_minutes
    total_distracted = 0

    for s in range(sessions):
        session_time = min(focus_len, mins_left)
        # Show initial popup
        popup_show(stdscr, [
                   f"Starting Pomodoro {s+1}/{sessions}: {session_time} min focus"], title="Focus Session")
        # Run countdown; track start time
        start_ts = time.time()
        completed = countdown_timer_ui(
            stdscr, session_time * 60, title=f"Focus {s+1}/{sessions}")
        elapsed = time.time() - start_ts
        # Compute elapsed minutes
        elapsed_minutes = int(elapsed // 60)
        if elapsed_minutes > session_time:
            elapsed_minutes = session_time
        # Compute distracted minutes: remaining of session_time not focused
        distracted = session_time - elapsed_minutes
        # If user did not abort early (completed=True), optionally ask for manual distraction override:
        if completed:
            # Ask user if there was additional distraction beyond early abort
            distract_str = popup_input(
                stdscr, "Distracted minutes this session? (0 if none):", default="0")
            try:
                extra = int(distract_str) if distract_str else 0
            except Exception:
                extra = 0
            distracted += extra
        else:
            # Session aborted early: inform user and ask actual focused minutes or treat missing as distraction
            # For clarity, ask: "You ended session early after approx X min. How many minutes did you actually focus?"
            prompt = f"You ended early after about {elapsed_minutes} min. Enter actual focused minutes (<= {session_time}):"
            focused_str = popup_input(
                stdscr, prompt, default=str(elapsed_minutes))
            try:
                focused = int(focused_str)
                if focused < 0:
                    focused = 0
                if focused > session_time:
                    focused = session_time
            except Exception:
                focused = elapsed_minutes
            distracted = session_time - focused
        total_distracted += distracted

        mins_left -= session_time

        # Break between sessions
        if s < sessions - 1:
            popup_show(stdscr, [
                       f"Take a {break_len} min break. Press any key when ready."], title="Break")
    return total_distracted


def run_makeup_sessions_ui(stdscr, total_distracted, focus_len, break_len=None):
    """
    Run makeup sessions equal to total_distracted, using same focus_len.
    Optionally show break_len between makeup sessions if provided.
    """
    if total_distracted <= 0:
        return
    popup_show(stdscr, [
               f"Additional focus time needed from distractions: {total_distracted} min"], title="Makeup Sessions")
    # Compute how many sessions
    sessions = (total_distracted + focus_len - 1) // focus_len
    distracted_left = total_distracted
    for i in range(sessions):
        session_time = min(focus_len, distracted_left)
        popup_show(stdscr, [
                   f"Makeup Pomodoro {i+1}/{sessions}: {session_time} min focus"], title="Makeup Focus")
        # Run countdown
        completed = countdown_timer_ui(
            stdscr, session_time * 60, title=f"Makeup {i+1}/{sessions}")
        # If aborted early, ask actual focused minutes:
        if not completed:
            # Similar handling as above
            prompt = f"You ended early. Enter actual focused minutes (<= {session_time}):"
            focused_str = popup_input(stdscr, prompt, default=str(0))
            try:
                focused = int(focused_str)
                if focused < 0:
                    focused = 0
                if focused > session_time:
                    focused = session_time
            except Exception:
                focused = 0
            # We won't accumulate further distractions in makeup
            # but could loop until fully made up if desired
            distracted_left -= focused
        else:
            distracted_left -= session_time
        # Break between makeup sessions if break_len provided
        if break_len and distracted_left > 0:
            popup_show(stdscr, [
                       f"Take a short break before next makeup session. Press any key when ready."], title="Break")
    # Final popup when makeup complete
    popup_show(stdscr, [f"Makeup sessions complete."], title="Makeup Done")


def record_task_notes(stdscr, task, minutes):
    """
    Prompt for notes at end of task; if provided, record a separate time entry.
    """
    from datetime import datetime, timedelta
    notes = popup_input(stdscr, "Any notes for this task? (blank to skip):")
    if notes:
        now = datetime.now()
        # Start a new time entry for notes
        time_repository.start_time_entry(
            title=task.title,
            task_id=task.id,
            start_time=now.isoformat(),
            category=task.category,
            project=task.project,
            notes=notes,
        )
        # Stop it after the planned duration
        end_dt = now + timedelta(minutes=minutes)
        time_repository.stop_active_time_entry(end_time=end_dt.isoformat())


def log_between_tasks(stdscr, trackers):
    """
    After a task, prompt user to log any trackers before next task.
    """
    from datetime import datetime
    for tr in trackers:
        if popup_confirm(stdscr, f"Log '{tr.title}' now?"):
            value = popup_input(stdscr, f"Enter value for {tr.title}:")
            if value is not None:
                track_repository.add_tracker_entry(
                    tracker_id=tr.id,
                    timestamp=datetime.now().isoformat(),
                    value=value
                )


def show_end_of_day(stdscr):
    """Display end-of-day feedback."""
    feedback = get_feedback_saying("end_of_day")
    popup_show(stdscr, [feedback], title="🎉 Day Complete!")
