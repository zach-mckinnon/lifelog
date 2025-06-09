import npyscreen
from datetime import datetime, timedelta
from lifelog.utils.get_quotes import get_motivational_quote, get_feedback_saying
from lifelog.utils.db import task_repository, track_repository, time_repository
from lifelog.ui_views.popups import popup_show, popup_input, popup_confirm
# If you have MultiSelect, import here or use a custom popup


def start_day_tui(stdscr):
    # 1. Motivation
    quote = get_motivational_quote()
    popup_show(stdscr, [quote], title="🌞 Start Your Day!")

    # 2. Multi-select tasks
    all_tasks = task_repository.get_all_tasks()
    if not all_tasks:
        popup_show(stdscr, ["No tasks available!"], title="Start Day")
        return
    task_titles = [f"{t.title} (Due: {t.due or 'N/A'})" for t in all_tasks]
    # Use npyscreen.MultiSelectPopup if you have one, else ask 1 by 1:
    # For simple TUI, prompt comma-separated numbers
    selected = popup_input(stdscr, f"Select tasks for today (comma numbers, e.g., 1,3):\n" +
                           "\n".join(f"{i+1}. {t}" for i, t in enumerate(task_titles)))
    try:
        idx = [int(x.strip()) - 1 for x in selected.split(",") if x.strip()]
        today_tasks = [all_tasks[i] for i in idx]
    except Exception:
        popup_show(stdscr, ["Invalid selection."], title="Error")
        return

    # 3. Ask time per task
    plan = []
    total_minutes = 0
    for t in today_tasks:
        mins = popup_input(
            stdscr, f"How many minutes for '{t.title}'?", default="25")
        try:
            mins = int(mins)
        except Exception:
            mins = 25
        plan.append({"task": t, "minutes": mins})
        total_minutes += mins

    # 4. Overload warning
    if total_minutes > 480:
        popup_show(
            stdscr, ["⚠️ Over 8 hours planned! Consider reducing."], title="Overload")

    # 5. Trackers at start
    trackers = track_repository.get_all_trackers()
    for tr in trackers:
        if popup_confirm(stdscr, f"Log '{tr.title}' now?"):
            value = popup_input(stdscr, f"Enter value for {tr.title}:")
            track_repository.add_tracker_entry(
                tracker_id=tr.id, timestamp=datetime.now().isoformat(), value=value)

    # 6. Guided Pomodoro for each task
    for i, item in enumerate(plan):
        task = item["task"]
        minutes = item["minutes"]
        # Pomodoro style
        if minutes > 120:
            focus_len, break_len = 45, 10
        else:
            focus_len, break_len = 25, 5
        popup_show(stdscr, [
                   f"Task: {task.title}\n{focus_len}min focus / {break_len}min break"], title=f"Task {i+1}/{len(plan)}")
        sessions = (minutes + focus_len - 1) // focus_len
        mins_left = minutes
        distracted = 0
        for s in range(sessions):
            session_time = min(focus_len, mins_left)
            popup_show(stdscr, [
                       f"Pomodoro {s+1}/{sessions}: {session_time}min focus. Press any key when done."], title="Focus!")
            # You could add a countdown/animation here, but keep it simple for now
            distract = popup_input(
                stdscr, "Distracted minutes this session? (0 if none):", default="0")
            try:
                distracted += int(distract)
            except Exception:
                pass
            if s < sessions - 1:
                popup_show(stdscr, [
                           f"Take a {break_len}min break! Press any key to continue."], title="Break")
            mins_left -= session_time
        # Makeup Pomodoros for distraction
        while distracted > 0:
            extra = min(focus_len, distracted)
            popup_show(stdscr, [
                       f"Make up {extra}min focus time. Press any key when done."], title="Makeup Focus")
            distracted -= extra

        # End-of-task notes
        notes = popup_input(
            stdscr, "Any notes for this task? (blank to skip):")
        if notes:
            now = datetime.now()
            time_repository.start_time_entry({
                "title": task.title,
                "start": now.isoformat(),
                "category": getattr(task, "category", None),
                "project": getattr(task, "project", None),
                "notes": notes,
            })
            time_repository.stop_active_time_entry(
                end_time=now + timedelta(minutes=minutes))

        # Tracker logs between tasks
        for tr in trackers:
            if popup_confirm(stdscr, f"Log '{tr.title}' now?"):
                value = popup_input(stdscr, f"Enter value for {tr.title}:")
                track_repository.add_tracker_entry(
                    tracker_id=tr.id, timestamp=datetime.now().isoformat(), value=value)

        if i < len(plan) - 1:
            popup_show(stdscr, [
                       f"Transition: Next is {plan[i+1]['task'].title}. Take 5 min, press key when ready."], title="Transition")

    # 7. End-of-day
    feedback = get_feedback_saying("end_of_day")
    popup_show(stdscr, [feedback], title="🎉 Day Complete!")
