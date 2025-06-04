# clinical_insight_engine.py
from datetime import datetime, timedelta
import statistics
from scipy.stats import pearsonr

# ---------- Shared Helpers ----------


def safe_mean(values):
    """Return mean or None if no values."""
    try:
        return round(statistics.mean(values), 1)
    except Exception:
        return None


def safe_iso_date(dtstr):
    """Parse ISO date or None."""
    try:
        return datetime.fromisoformat(dtstr)
    except Exception:
        return None


def add_insight(insights, summary, rationale, action=None):
    insights.append(
        {"summary": summary, "rationale": rationale, "action": action})


def log_and_return(insights, summary, rationale, action=None):
    # DRY shortcut for adding and returning insights
    add_insight(insights, summary, rationale, action)
    return insights


def is_tracker_present(trackers, name):
    return next((t for t in trackers if t['title'].lower() == name.lower()), None)

# ---------- Insight Category Functions ----------


def insight_task_adherence(tasks, days=14):
    now = datetime.now()
    recent_tasks = [t for t in tasks if t.get('created') and
                    (now - safe_iso_date(t['created'])).days <= days]
    done = [t for t in recent_tasks if t.get('status') == 'done']
    not_done = [t for t in recent_tasks if t.get('status') != 'done']
    durations = []
    for t in done:
        if t.get('start') and t.get('end'):
            s = safe_iso_date(t['start'])
            e = safe_iso_date(t['end'])
            if s and e:
                durations.append((e - s).total_seconds() / 60)
    avg_complete_time = safe_mean(durations)
    insights = []
    if not_done or done:
        summary = f"You completed {len(done)} of {len(done)+len(not_done)} recent tasks"
        if (len(done) + len(not_done)):
            pct = int(100 * len(done) / (len(done) + len(not_done)))
            summary += f" ({pct}%)."
        rationale = "Task completion rate in the last 2 weeks."
        if avg_complete_time:
            summary += f" Avg time to complete: {avg_complete_time} min."
        action = "Consider reviewing why some tasks remain undone. Is there a common blocker?"
        add_insight(insights, summary, rationale, action)
    return insights


def insight_habit_streaks(trackers):
    insights = []
    for tr in trackers:
        entries = tr.get("entries", [])
        if not entries:
            continue
        # Calculate streaks (assume one entry per day max)
        dates = sorted({e['timestamp'][:10]
                       for e in entries if 'timestamp' in e})
        if not dates:
            continue
        streak = best_streak = 1
        last_date = safe_iso_date(dates[0])
        for dt_str in dates[1:]:
            dt = safe_iso_date(dt_str)
            if not last_date or not dt:
                continue
            if (dt - last_date).days == 1:
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 1
            last_date = dt
        add_insight(
            insights,
            f"Habit '{tr['title']}' best streak: {best_streak} days.",
            "Longest streak found in tracker history.",
            f"Try to beat your {best_streak}-day streak this week."
        )
    return insights


def insight_mood_sleep_correlation(trackers):
    mood_tracker = is_tracker_present(trackers, "mood")
    sleep_tracker = is_tracker_present(trackers, "sleep")
    insights = []
    if not (mood_tracker and sleep_tracker):
        add_insight(
            insights,
            "Not enough mood/sleep data for correlation.",
            "Trackers for both mood and sleep are required.",
            None
        )
        return insights
    mood_vals = [e['value'] for e in mood_tracker.get(
        "entries", []) if isinstance(e['value'], (int, float))]
    sleep_vals = [e['value'] for e in sleep_tracker.get(
        "entries", []) if isinstance(e['value'], (int, float))]
    n = min(len(mood_vals), len(sleep_vals))
    if n >= 7:
        mood_slice, sleep_slice = mood_vals[-n:], sleep_vals[-n:]
        try:
            r, p = pearsonr(mood_slice, sleep_slice)
            add_insight(
                insights,
                f"Mood/Sleep correlation over last {n} days: r={r:.2f} (p={p:.3f})",
                "Correlation coefficient; closer to 1 means higher mood with more sleep.",
                "Reflect on how sleep patterns may influence your mood."
            )
        except Exception:
            add_insight(
                insights,
                "Correlation calculation failed.",
                "Could not compute correlation between mood and sleep.",
                None
            )
    else:
        add_insight(
            insights,
            "Not enough mood/sleep data for correlation.",
            "At least 7 entries for both mood and sleep required.",
            None
        )
    return insights


def insight_time_usage_overload(time_entries, threshold=8*60):
    cat_totals = {}
    for t in time_entries:
        cat = t.get('category', 'Other')
        cat_totals[cat] = cat_totals.get(cat, 0) + t.get('duration_minutes', 0)
    insights = []
    for cat, total in cat_totals.items():
        if total > threshold:
            add_insight(
                insights,
                f"High load in '{cat}': {total} min in last period.",
                "Possible overload if you consistently spend 8+ hours on one category.",
                f"Consider if you want to rebalance your focus away from '{cat}'."
            )
    return insights


def insight_missed_goals(trackers):
    insights = []
    for tr in trackers:
        g = tr.get("goals", [{}])[0] if tr.get("goals") else None
        if not g:
            continue
        progress = g.get("progress", 0)
        target = g.get("amount", g.get("target", 0))
        if target and progress < target:
            add_insight(
                insights,
                f"Goal for '{tr['title']}': {progress} / {target} so far.",
                "Progress toward your defined goal.",
                "Consider adjusting your approach or setting a smaller target."
            )
    return insights


def pearson_corr(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    avg_x = sum(xs) / n
    avg_y = sum(ys) / n
    num = sum((x - avg_x)*(y - avg_y) for x, y in zip(xs, ys))
    den_x = sum((x - avg_x)**2 for x in xs)
    den_y = sum((y - avg_y)**2 for y in ys)
    denom = (den_x * den_y) ** 0.5
    if denom == 0:
        return 0.0
    return num / denom

# ---------- Main Clinical Insight Generator ----------


def generate_clinical_insights(trackers, tasks, goals, time_entries):
    """
    Aggregate all available data and return a list of meaningful, clinical-style insights.
    Each insight is a dict with: summary, rationale, optional action/reflection.
    """
    insights = []
    insights.extend(insight_task_adherence(tasks))
    insights.extend(insight_habit_streaks(trackers))
    insights.extend(insight_mood_sleep_correlation(trackers))
    insights.extend(insight_time_usage_overload(time_entries))
    insights.extend(insight_missed_goals(trackers))
    return insights
