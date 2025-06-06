# tests/test_summary_and_report.py

import os
import json
import csv
import pytest
import pandas as pd
from datetime import datetime, timedelta
from rich.table import Table
from rich.console import Console
from typer.testing import CliRunner

# Adjust imports as needed
from lifelog.commands.report import (
    generate_goal_report,
    _report_range,
    _report_sum,
    _report_count,
    _report_bool,
    _report_streak,
    _report_duration,
    _report_milestone,
    _report_percentage,
    _report_reduction,
    _report_replacement,
    print_dataframe,
)
from lifelog.utils.db import track_repository, report_repository, time_repository, task_repository
from lifelog.utils.reporting.insight_engine import daily_averages, load_tracker_data, load_time_data
from lifelog.utils.db.models import TrackerEntry, GoalSum, GoalCount, GoalRange
from lifelog.commands import report
from lifelog.commands.report import app as report_app
from lifelog.config import config_manager as cfg

runner = CliRunner()

# ────────────────────────────────────────────────────────────────────────────────
# 1. Test the “_report_*” helper functions in isolation (pure‐function outputs)
# ────────────────────────────────────────────────────────────────────────────────


def test_report_range_in_and_out_of_range():
    tracker = {"id": 1, "title": "T1"}
    goal = {"id": 100, "kind": "range"}
    # details: min=10, max=20, mode="goal"
    details = {"min_amount": 10.0, "max_amount": 20.0, "mode": "goal"}
    # Create a DataFrame with one entry value=15 → in range
    df = pd.DataFrame([{"timestamp": "2025-06-05T00:00:00", "value": 15.0}])
    out = _report_range(tracker, goal, details, df)
    assert out["completed"] is True
    assert "In range" in out["status"]
    # Now value=5 → out of range
    df2 = pd.DataFrame([{"timestamp": "2025-06-05T00:00:00", "value": 5.0}])
    out2 = _report_range(tracker, goal, details, df2)
    assert out2["completed"] is False
    assert "Out of range" in out2["status"]


def test_report_sum_before_and_after_target():
    tracker = {"id": 1}
    goal = {"id": 101, "kind": "sum"}
    details = {"amount": 100.0}
    # Two entries totaling 80 < 100
    df = pd.DataFrame([{"timestamp": "2025-06-01T00:00:00", "value": 30.0},
                       {"timestamp": "2025-06-02T00:00:00", "value": 50.0}])
    out = _report_sum(tracker, goal, details, df)
    assert out["completed"] is False
    assert "Keep going" in out["status"]
    # Now total 120 > 100
    df2 = pd.DataFrame([{"timestamp": "2025-06-01T00:00:00", "value": 60.0},
                        {"timestamp": "2025-06-02T00:00:00", "value": 60.0}])
    out2 = _report_sum(tracker, goal, details, df2)
    assert out2["completed"] is True
    assert "Goal reached" in out2["status"]


def test_report_count_before_and_after_target():
    tracker = {"id": 2}
    goal = {"id": 102, "kind": "count"}
    details = {"amount": 3}
    # 2 entries (count=2) < target=3
    df = pd.DataFrame([{"timestamp": "t", "value": 1},
                      {"timestamp": "t", "value": 1}])
    out = _report_count(tracker, goal, details, df)
    assert out["completed"] is False
    assert "Progressing" in out["status"]
    # 3 entries (count=3) == target
    df2 = pd.DataFrame([{"timestamp": "t", "value": 1}]*3)
    out2 = _report_count(tracker, goal, details, df2)
    assert out2["completed"] is True


def test_report_bool_all_and_partial():
    tracker = {"id": 3}
    goal = {"id": 103, "kind": "bool"}
    # Values: [1,1,1] → 100% true
    df = pd.DataFrame([{"timestamp": "t", "value": 1}]*3)
    out = _report_bool(tracker, goal, df)
    assert out["completed"] is True
    assert "All completed" in out["status"]
    # Mixed [1,0,1] → 66.6%
    df2 = pd.DataFrame([
        {"timestamp": "t", "value": 1},
        {"timestamp": "t", "value": 0},
        {"timestamp": "t", "value": 1},
    ])
    out2 = _report_bool(tracker, goal, df2)
    assert out2["completed"] is False


def test_report_streak_logic():
    tracker = {"id": 4}
    goal = {"id": 104, "kind": "streak"}
    details = {"target_streak": 2}
    # Create 3 consecutive days
    now = datetime.now()
    entries = [
        {"timestamp": (now - timedelta(days=2)).isoformat(), "value": 1},
        {"timestamp": (now - timedelta(days=1)).isoformat(), "value": 1},
        {"timestamp": now.isoformat(), "value": 1},
    ]
    df = pd.DataFrame(entries)
    out = _report_streak(tracker, goal, details, df)
    assert out["completed"] is True or out["metrics"]["streak"] == 3


def test_report_duration_conversions_and_messages():
    tracker = {"id": 5}
    goal = {"id": 105, "kind": "duration"}
    details = {"amount": 120.0, "unit": "minutes"}
    # total = 30 + 90 = 120
    df = pd.DataFrame([
        {"timestamp": "t", "value": 30},
        {"timestamp": "t", "value": 90},
    ])
    out = _report_duration(tracker, goal, details, df)
    assert out["completed"] is True
    assert "Goal reached" in out["status"]


def test_report_milestone_and_percentage_and_reduction_and_replacement():
    # Milestone
    tracker = {"id": 6}
    goal = {"id": 106, "kind": "milestone"}
    details = {"target": 50.0, "unit": "kg"}
    df = pd.DataFrame([{"timestamp": "t", "value": 20},
                      {"timestamp": "t", "value": 40}])
    out = _report_milestone(tracker, goal, details, df)
    assert out["completed"] is False
    details2 = {"target": 50.0, "unit": "kg"}
    df2 = pd.DataFrame([{"timestamp": "t", "value": 30},
                       {"timestamp": "t", "value": 30}])
    out2 = _report_milestone(tracker, goal, details2, df2)
    assert out2["completed"] is True

    # Percentage
    tracker2 = {"id": 7}
    goal2 = {"id": 107, "kind": "percentage"}
    details_p = {"target_percentage": 75.0}
    dfp = pd.DataFrame([{"timestamp": "t", "value": 80.0}])
    out_p = _report_percentage(tracker2, goal2, details_p, dfp)
    assert out_p["completed"] is True

    # Reduction
    tracker3 = {"id": 8}
    goal3 = {"id": 108, "kind": "reduction"}
    details_r = {"amount": 100.0, "unit": "units"}
    dfr = pd.DataFrame([{"timestamp": "t", "value": 80.0}])
    out_r = _report_reduction(tracker3, goal3, details_r, dfr)
    assert out_r["completed"] is True

    # Replacement
    tracker4 = {"id": 9}
    goal4 = {"id": 109, "kind": "replacement"}
    details_rep = {"old_behavior": "smoke", "new_behavior": "chew"}
    # Values >0 count as new, <0 as old
    df = pd.DataFrame([
        {"timestamp": "2025-06-05T00:00:00", "value": 20.0},
        {"timestamp": "2025-06-05T00:00:00", "value": 20.0},
    ])

    out = _report_milestone(tracker, goal, details, df)
    assert out["completed"] is False

# ────────────────────────────────────────────────────────────────────────────────
# 2. Test print_dataframe for empty and non‐empty
# ────────────────────────────────────────────────────────────────────────────────


def test_print_dataframe_empty(capsys):
    df_empty = pd.DataFrame()
    print_dataframe(df_empty)
    captured = capsys.readouterr().out
    assert "No data found" in captured


def test_print_dataframe_non_empty(capsys):
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    print_dataframe(df)
    captured = capsys.readouterr().out
    # Should contain column headers "A" and "B"
    assert "A" in captured and "B" in captured

# ────────────────────────────────────────────────────────────────────────────────
# 3. (Optional) Test the CLI command “insights” prints something
# ────────────────────────────────────────────────────────────────────────────────


def test_cli_insights_command(monkeypatch, capsys):
    # Monkey‐patch report_repository.get_correlation_insights()
    fake_insights = [{"note": "Test correlation",
                      "correlation": {"pearson": 0.5}}]
    from lifelog.utils.db import report_repository
    monkeypatch.setattr(report_repository,
                        "get_correlation_insights", lambda: fake_insights)

    result = runner.invoke(report_app, ["insights"])
    assert result.exit_code == 0
    out = result.stdout
    assert "1. Test correlation" in out
