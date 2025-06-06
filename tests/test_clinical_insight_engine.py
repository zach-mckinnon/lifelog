# tests/test_clinical_insight_engine.py

import pytest
from datetime import datetime, timedelta

from lifelog.utils.reporting.clinical_insight_engine import (
    safe_mean,
    safe_iso_date,
    add_insight,
    log_and_return,
    is_tracker_present,
    insight_task_adherence,
    insight_habit_streaks,
    insight_mood_sleep_correlation,
    insight_time_usage_overload,
    insight_missed_goals,
    pearson_corr,
    generate_clinical_insights,
)

# ────────────────────────────────────────────────────────────────────────────────
# 1. Test safe_mean & safe_iso_date & pearson_corr helpers
# ────────────────────────────────────────────────────────────────────────────────


def test_safe_mean_with_values_and_empty():
    assert safe_mean([1, 2, 3]) == 2.0
    assert safe_mean([]) is None
    assert safe_mean(["a", "b"]) is None


def test_safe_iso_date_valid_and_invalid():
    valid = "2025-06-05T10:30:00"
    assert isinstance(safe_iso_date(valid), datetime)
    assert safe_iso_date("not-a-date") is None


def test_pearson_corr_edge_cases_and_normal():
    # Less than two elements
    assert pearson_corr([1], [1]) == 0.0
    # Unequal lengths
    assert pearson_corr([1, 2], [1]) == 0.0
    # Perfect positive correlation
    xs = [1, 2, 3, 4]
    ys = [10, 20, 30, 40]
    corr = pearson_corr(xs, ys)
    assert pytest.approx(corr, rel=1e-3) == 1.0
    # Perfect negative correlation
    xs2 = [1, 2, 3, 4]
    ys2 = [40, 30, 20, 10]
    corr2 = pearson_corr(xs2, ys2)
    assert pytest.approx(corr2, rel=1e-3) == -1.0

# ────────────────────────────────────────────────────────────────────────────────
# 2. Test “insight_task_adherence”
# ────────────────────────────────────────────────────────────────────────────────


def make_task(created_offset_days, status, start=None, end=None):
    d = {}
    # created_offset_days days ago
    created = (datetime.now() - timedelta(days=created_offset_days)).isoformat()
    d["created"] = created
    d["status"] = status
    if start:
        d["start"] = start
    if end:
        d["end"] = end
    return d


def test_insight_task_adherence_empty_lists():
    # No tasks yields empty insights
    insights = insight_task_adherence([], days=14)
    assert insights == []


def test_insight_task_adherence_partial_and_done():
    now = datetime.now()
    # Task done with a 30‐minute duration
    t1 = make_task(3, "done", start=(now - timedelta(minutes=30)
                                     ).isoformat(), end=now.isoformat())
    # Task not done
    t2 = make_task(2, "backlog")
    insights = insight_task_adherence([t1, t2], days=14)
    assert len(insights) == 1
    summary = insights[0]["summary"]
    assert "You completed 1 of 2" in summary

# ────────────────────────────────────────────────────────────────────────────────
# 3. Test “insight_habit_streaks”
# ────────────────────────────────────────────────────────────────────────────────


def test_insight_habit_streaks_single_tracker_short_and_long():
    # Tracker with no entries → no insights
    no_entries = {"title": "X", "entries": []}
    assert insight_habit_streaks([no_entries]) == []

    # Tracker with 3‐day streak
    d0 = datetime.now() - timedelta(days=2)
    d1 = datetime.now() - timedelta(days=1)
    d2 = datetime.now()
    en = [{"timestamp": d0.isoformat()}, {"timestamp": d1.isoformat()},
          {"timestamp": d2.isoformat()}]
    tracker = {"title": "HabitA", "entries": en}
    insights = insight_habit_streaks([tracker])
    assert len(insights) == 1
    assert "best streak" in insights[0]["summary"]

# ────────────────────────────────────────────────────────────────────────────────
# 4. Test “insight_mood_sleep_correlation”
# ────────────────────────────────────────────────────────────────────────────────


def make_tracker_with_entries(name, values, start_date):
    """
    Build a tracker dict with a list of entries dicts containing 'timestamp' and 'value'.
    """
    entries = []
    for i, v in enumerate(values):
        day_ts = (start_date + timedelta(days=i)).isoformat()
        entries.append({"timestamp": day_ts, "value": v})
    return {"title": name, "entries": entries}


def test_insight_mood_sleep_correlation_insufficient_and_sufficient():
    today = datetime.now().date()
    # Insufficient: fewer than 7 days
    mood = make_tracker_with_entries(
        "mood", [3, 4, 5], today - timedelta(days=2))
    sleep = make_tracker_with_entries(
        "sleep", [7, 8, 6], today - timedelta(days=2))
    ins1 = insight_mood_sleep_correlation([mood, sleep])
    assert len(ins1) == 1
    assert "Not enough mood/sleep data" in ins1[0]["summary"]

    # Sufficient: 7 days
    values = [1, 2, 3, 4, 5, 6, 7]
    mood2 = make_tracker_with_entries(
        "mood", values, today - timedelta(days=6))
    sleep2 = make_tracker_with_entries(
        "sleep", values, today - timedelta(days=6))
    ins2 = insight_mood_sleep_correlation([mood2, sleep2])
    assert len(ins2) == 1
    assert "Mood/Sleep correlation" in ins2[0]["summary"]

# ────────────────────────────────────────────────────────────────────────────────
# 5. Test “insight_time_usage_overload”
# ────────────────────────────────────────────────────────────────────────────────


def test_insight_time_usage_overload_above_and_below_threshold():
    # Category “Work” has 500 minutes, threshold=480 → insight
    entries = [
        {"category": "Work", "duration_minutes": 500},
        {"category": "Leisure", "duration_minutes": 100}
    ]
    ins = insight_time_usage_overload(entries, threshold=480)
    assert len(ins) == 1
    assert "High load in 'Work'" in ins[0]["summary"]
    # If below threshold → empty
    ins2 = insight_time_usage_overload(
        [{"category": "Work", "duration_minutes": 300}], threshold=480)
    assert ins2 == []

# ────────────────────────────────────────────────────────────────────────────────
# 6. Test “insight_missed_goals”
# ────────────────────────────────────────────────────────────────────────────────


def test_insight_missed_goals_with_and_without_progress():
    # Tracker with no goals → no insight
    tr1 = {"title": "T1", "goals": []}
    assert insight_missed_goals([tr1]) == []

    # Tracker with goal progress less than target → insight
    g = {"amount": 100.0, "progress": 40.0}
    tr2 = {"title": "T2", "goals": [g]}
    ins = insight_missed_goals([tr2])
    assert len(ins) == 1
    assert "Goal for 'T2'" in ins[0]["summary"]

    # Tracker with progress >= target → no insight
    g2 = {"amount": 50.0, "progress": 50.0}
    tr3 = {"title": "T3", "goals": [g2]}
    ins2 = insight_missed_goals([tr3])
    # We only add an insight if progress < target, so ins2 == []
    assert ins2 == []

# ────────────────────────────────────────────────────────────────────────────────
# 7. Test “generate_clinical_insights” combining all categories
# ────────────────────────────────────────────────────────────────────────────────


def test_generate_clinical_insights_combined():
    # Build sample data so that we get at least one insight from each category
    now = datetime.now()
    # Tasks: two tasks, one done with 60‐min duration, one not done
    t_done = {"created": (now - timedelta(days=1)).isoformat(), "status": "done",
              "start": (now - timedelta(minutes=60)).isoformat(), "end": now.isoformat()}
    t_not_done = {"created": (now - timedelta(days=2)
                              ).isoformat(), "status": "backlog"}
    tasks = [t_done, t_not_done]

    # Trackers: “mood” and “sleep” each with 7 days of entries
    base_date = now.date() - timedelta(days=6)
    mood = make_tracker_with_entries("mood", [5]*7, base_date)
    sleep = make_tracker_with_entries("sleep", [7]*7, base_date)
    trackers = [mood, sleep]

    # Time entries: one category “Work” with 600 minutes
    time_entries = [{"category": "Work", "duration_minutes": 600}]

    # Goals: embed a “missed goal” into trackers by adding “goals” and “entries”
    # For simplicity re‐use trackers above; add a goal with progress 20/100
    trackers[0]["goals"] = [{"amount": 100.0, "progress": 20.0}]

    insights = generate_clinical_insights(trackers, tasks, [], time_entries)
    # We expect at least:
    #  • One for task adherence (since 1 done of 2)
    #  • One for habit streak (both mood & sleep have streaks)
    #  • One for mood/sleep correlation
    #  • One for time usage overload (Work:600>480)
    #  • One for missed goal (mood tracker)
    categories = {i["summary"].split()[0] for i in insights}
    # At least 5 separate insights
    assert len(insights) >= 5
