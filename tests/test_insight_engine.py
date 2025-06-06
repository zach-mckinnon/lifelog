# tests/test_insight_engine.py

import pytest
import statistics
from datetime import datetime, timedelta

from lifelog.utils.reporting.insight_engine import (
    load_tracker_data,
    load_time_data,
    daily_averages,
    compute_correlation,
    generate_insights,
)

# We will monkey‐patch the repository functions used inside load_tracker_data & load_time_data


@pytest.fixture(autouse=True)
def stub_repositories(monkeypatch):
    from lifelog.utils.db import track_repository, time_repository

    # Stub get_all_trackers_with_entries() to return two trackers with entries
    fake_trackers = [
        {
            "title": "MetricA",
            "entries": [
                {"timestamp": (datetime.now() - timedelta(days=2)
                               ).isoformat(), "value": 2.0},
                {"timestamp": (datetime.now() - timedelta(days=1)
                               ).isoformat(), "value": 4.0},
                {"timestamp": datetime.now().isoformat(), "value": 6.0},
            ]
        },
        {
            "title": "MetricB",
            "entries": [
                {"timestamp": (datetime.now() - timedelta(days=2)
                               ).isoformat(), "value": 20.0},
                {"timestamp": (datetime.now() - timedelta(days=1)
                               ).isoformat(), "value": 40.0},
                {"timestamp": datetime.now().isoformat(), "value": 60.0},
            ]
        }
    ]
    monkeypatch.setattr(
        track_repository, "get_all_trackers_with_entries", lambda: fake_trackers)

    # Stub get_all_time_logs() to return one time log
    fake_time_logs = [
        {
            "title": "WorkSession",
            "start": (datetime.now() - timedelta(days=1)).isoformat(),
            "duration_minutes": 30
        }
    ]
    monkeypatch.setattr(time_repository, "get_all_time_logs",
                        lambda: fake_time_logs)
    yield


# ────────────────────────────────────────────────────────────────────────────────
# 1. Test load_tracker_data & load_time_data combine correctly
# ────────────────────────────────────────────────────────────────────────────────

def test_load_tracker_data_combines_entries():
    combined = load_tracker_data()
    # We had two trackers, each with 3 entries → total 6 combined
    assert isinstance(combined, list)
    assert len(combined) == 6
    # Each dict has keys “tracker”, “timestamp”, “value”
    for item in combined:
        assert "tracker" in item and "timestamp" in item and "value" in item


def test_load_time_data_combines_time_logs():
    combined = load_time_data()
    # We have one time log → since duration_minutes not None, one combined entry
    assert isinstance(combined, list)
    assert len(combined) == 1
    assert combined[0]["tracker"].startswith("Time:")


# ────────────────────────────────────────────────────────────────────────────────
# 2. Test daily_averages
# ────────────────────────────────────────────────────────────────────────────────

def test_daily_averages_simple_and_invalid():
    now = datetime.now()
    # Two entries for same day and same tracker
    entries = [
        {"tracker": "T1", "timestamp": now.isoformat(), "value": 10},
        {"tracker": "T1", "timestamp": now.isoformat(), "value": 20},
        {"tracker": "T2", "timestamp": now.isoformat(), "value": 5},
        {"tracker": "T2", "timestamp": "invalid", "value": 5},  # skip
    ]
    result = daily_averages(entries)
    day = now.date().isoformat()
    assert "T1" in result and "T2" in result
    assert result["T1"][day] == statistics.mean([10, 20])
    assert result["T2"][day] == 5.0

# ────────────────────────────────────────────────────────────────────────────────
# 3. Test compute_correlation
# ────────────────────────────────────────────────────────────────────────────────


def test_compute_correlation_edge_and_normal():
    # Edge cases
    corr0 = compute_correlation([1], [2])
    assert corr0["pearson"] == 0.0 and corr0["spearman"] == 0.0

    # Normal case
    x = [1, 2, 3, 4]
    y = [4, 3, 2, 1]
    corr = compute_correlation(x, y)
    # Spearman and Pearson should be -1 (perfect negative)
    assert round(corr["pearson"], 3) == -1.0
    assert round(corr["spearman"], 3) == -1.0

# ────────────────────────────────────────────────────────────────────────────────
# 4. Test generate_insights produces sorted list
# ────────────────────────────────────────────────────────────────────────────────


def test_generate_insights_minimum_overlap():
    # daily_averages and load_tracker_data / load_time_data have been stubbed above
    # In our stub, MetricA & MetricB have overlapping 3 days → less than MIN_OVERLAP_DAYS=7 → no insights
    # So generate_insights() should return an empty list
    insights = generate_insights()
    assert insights == []


def test_generate_insights_with_enough_overlap(monkeypatch):
    # Force 7‐day overlap by stubbing daily_averages to return two metrics each with 7 day keys
    from lifelog.utils.reporting.insight_engine import generate_insights
    now = datetime.now().date()
    fake = {}
    for i in range(7):
        day = (now - timedelta(days=i)).isoformat()
        fake.setdefault("M1", {})[day] = i + 1
        fake.setdefault("M2", {})[day] = (i + 1) * 2
    monkeypatch.setattr(
        "livelog.utils.insight_engine.daily_averages", lambda entries: fake)
    # Now generate_insights should produce at least one insight
    insights = generate_insights()
    assert isinstance(insights, list)
    assert len(insights) >= 1
    assert all("correlation" in ins for ins in insights)
