# tests/test_reports_ui.py

from lifelog.utils.db import task_repository
from lifelog.ui_views.reports_ui import (
    _drop_to_console,
    run_summary_trackers,
    run_summary_time,
    run_daily_tracker,
    run_insights,
    run_clinical_insights,
    draw_report,
    draw_burndown
)
import sys
import builtins
import pytest
from types import SimpleNamespace
from datetime import datetime, timedelta

# ────────────────────────────────────────────────────────────────────────────────
# 1. Inject a dummy curses module before importing reports_ui
# ────────────────────────────────────────────────────────────────────────────────


class DummyCurses:
    A_BOLD = 1
    A_NORMAL = 0

    def __init__(self):
        pass

    def endwin(self):
        # no-op for tests
        pass


# Override sys.modules so that `import curses` yields our DummyCurses
sys.modules['curses'] = DummyCurses()

# ────────────────────────────────────────────────────────────────────────────────
# 2. Import the functions under test
# ────────────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────────────
# 3. A minimal “window” stub to capture calls to erase, border, addstr, noutrefresh
# ────────────────────────────────────────────────────────────────────────────────


class DummyWin:
    def __init__(self, h=10, w=40):
        self._h = h
        self._w = w
        self.calls = []

    def getmaxyx(self):
        return (self._h, self._w)

    def erase(self):
        self.calls.append(('erase',))

    def border(self):
        self.calls.append(('border',))

    def addstr(self, y, x, s, attr=0):
        self.calls.append(('addstr', y, x, s, attr))

    def noutrefresh(self):
        self.calls.append(('noutrefresh',))

    def getch(self):
        # Not used by draw_report/draw_burndown
        return -1

# ────────────────────────────────────────────────────────────────────────────────
# 4. Fixture to stub popups, logging, builtins.input, and curses.endwin
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_global(monkeypatch):
    """
    - Patch builtins.input so that _drop_to_console does not block.
    - Patch curses.endwin to no-op (already provided via DummyCurses).
    - Stub popup_input, popup_error, log_and_popup_error, log_exception, safe_addstr.
    """
    import lifelog.ui_views.reports_ui as rui
    from lifelog.ui_views.popups import popup_input, popup_error, log_and_popup_error
    from lifelog.ui_views.ui_helpers import log_exception, safe_addstr

    # 4a. Ensure input() returns immediately
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")

    # 4b. Stub popup_input to return empty by default
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_input", lambda stdscr, msg: "")

    # 4c. Stub popup_error and log_and_popup_error so calls are recorded in a dict
    called = {
        "popup_error": False,
        "log_and_popup_error": False,
        "log_exception": False
    }
    monkeypatch.setattr("livelog.ui_views.popups.popup_error",
                        lambda stdscr, msg: called.update({"popup_error": True}))
    monkeypatch.setattr("livelog.ui_views.popups.log_and_popup_error",
                        lambda stdscr, m, e: called.update({"log_and_popup_error": True}))
    monkeypatch.setattr("livelog.ui_views.ui_helpers.log_exception",
                        lambda ctx, e: called.update({"log_exception": True}))
    # safe_addstr just calls pane.addstr, so no need to override it

    # Expose `called` dict via the fixture
    yield called

# ────────────────────────────────────────────────────────────────────────────────
# 5. Tests for _drop_to_console()
# ────────────────────────────────────────────────────────────────────────────────


def test__drop_to_console_normal(monkeypatch):
    """
    Simulate a function that prints something to stdout. Verify that it runs,
    catches no exception, and then returns. We check by setting a flag.
    """
    # 5a. Create a fake function to pass to _drop_to_console
    called = {"ran": False}

    def fake_report():
        called["ran"] = True
        print("Fake report executed")

    # 5b. Call _drop_to_console
    _drop_to_console(fake_report)
    assert called["ran"], "_drop_to_console should invoke the provided function"


def test__drop_to_console_exception(monkeypatch, capsys):
    """
    Simulate a function that raises. Verify that exception is caught,
    printed to stdout, and we still return.
    """
    def bad_report():
        raise ValueError("bad things")

    # Call _drop_to_console, capture stdout
    _drop_to_console(bad_report)
    captured = capsys.readouterr()
    # Should print the error message
    assert "Error running report: bad things" in captured.out

# ────────────────────────────────────────────────────────────────────────────────
# 6. Tests for run_summary_trackers and run_summary_time
# ────────────────────────────────────────────────────────────────────────────────


def test_run_summary_trackers_invokes_summary(monkeypatch):
    """
    Monkeypatch summary_trackers to set a flag, then call run_summary_trackers.
    """
    import lifelog.commands.report as repmod
    called = {"summary": False}
    monkeypatch.setattr(repmod, "summary_trackers",
                        lambda: called.update({"summary": True}))

    # Call run_summary_trackers with any stdscr (None is fine)
    run_summary_trackers(None)
    assert called["summary"], "run_summary_trackers should invoke summary_trackers"


def test_run_summary_time_invokes_summary(monkeypatch):
    """
    Monkeypatch summary_time to set a flag, then call run_summary_time.
    """
    import lifelog.commands.report as repmod
    called = {"summary_time": False}
    monkeypatch.setattr(repmod, "summary_time",
                        lambda: called.update({"summary_time": True}))

    run_summary_time(None)
    assert called["summary_time"], "run_summary_time should invoke summary_time"

# ────────────────────────────────────────────────────────────────────────────────
# 7. Tests for run_daily_tracker
# ────────────────────────────────────────────────────────────────────────────────


def test_run_daily_tracker_no_metric(monkeypatch, patch_global):
    """
    If popup_input returns empty, run_daily_tracker should invoke popup_error and not call daily_tracker.
    """
    # popup_input returns "" by default (from fixture)
    import lifelog.commands.report as repmod
    called = patch_global  # from fixture

    # Monkeypatch daily_tracker so that if it were called, it would raise
    monkeypatch.setattr(repmod, "daily_tracker", lambda metric: (
        _ for _ in ()).throw(AssertionError("Should not call daily_tracker")))

    run_daily_tracker(None)
    # popup_error should have been called once
    assert called["popup_error"], "Popup error should be called when metric is empty"


def test_run_daily_tracker_with_metric(monkeypatch, patch_global):
    """
    If popup_input returns a non-empty metric, run_daily_tracker should call daily_tracker via _drop_to_console.
    """
    # 7a. Patch popup_input to return a non-empty string
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda stdscr, msg: "metric1")

    import lifelog.commands.report as repmod
    called = {"daily": False}
    monkeypatch.setattr(repmod, "daily_tracker",
                        lambda m: called.update({"daily": True}))

    # Call run_daily_tracker
    run_daily_tracker(None)
    assert called["daily"], "run_daily_tracker should invoke daily_tracker when metric provided"

# ────────────────────────────────────────────────────────────────────────────────
# 8. Tests for run_insights
# ────────────────────────────────────────────────────────────────────────────────


def test_run_insights_invokes_show_insights(monkeypatch):
    """
    run_insights should simply call show_insights via _drop_to_console.
    """
    import lifelog.commands.report as repmod
    called = {"insights": False}
    monkeypatch.setattr(repmod, "show_insights",
                        lambda: called.update({"insights": True}))

    run_insights(None)
    assert called["insights"], "run_insights should invoke show_insights"

# ────────────────────────────────────────────────────────────────────────────────
# 9. Tests for run_clinical_insights
# ────────────────────────────────────────────────────────────────────────────────


def test_run_clinical_insights_success(monkeypatch, patch_global):
    """
    If show_clinical_insights does not raise, run_clinical_insights should not call log_and_popup_error.
    """
    # Patch show_clinical_insights to set a flag
    import lifelog.commands.report as repmod
    called_flag = {"ran": False}
    monkeypatch.setattr(repmod, "show_clinical_insights",
                        lambda stdscr=None: called_flag.update({"ran": True}))

    run_clinical_insights(None)
    assert called_flag["ran"], "run_clinical_insights should call show_clinical_insights"
    assert not patch_global["log_and_popup_error"], "log_and_popup_error should not be called on success"


def test_run_clinical_insights_exception(monkeypatch, patch_global):
    """
    If show_clinical_insights raises, run_clinical_insights should call log_and_popup_error.
    """
    import lifelog.commands.report as repmod

    def bad_insights(stdscr=None):
        raise RuntimeError("oops")
    monkeypatch.setattr(repmod, "show_clinical_insights", bad_insights)

    run_clinical_insights(None)
    assert patch_global["log_and_popup_error"], "Should call log_and_popup_error on exception"

# ────────────────────────────────────────────────────────────────────────────────
# 10. Tests for draw_report()
# ────────────────────────────────────────────────────────────────────────────────


def test_draw_report_normal():
    """
    Verify that draw_report writes the title and menu lines without error.
    """
    pane = DummyWin(h=12, w=50)
    draw_report(pane, h=12, w=50)

    # First calls: 'erase', 'border'
    assert pane.calls[0][0] == 'erase'
    assert pane.calls[1][0] == 'border'

    # Third call should be addstr for the centered title " Reports "
    addstr_calls = [c for c in pane.calls if c[0] == 'addstr']
    assert addstr_calls, "draw_report should call addstr at least once"
    title_call = addstr_calls[0]
    _, y, x, text, attr = title_call
    assert y == 0 and "Reports" in text and attr == DummyCurses.A_BOLD

    # Subsequent lines should include the menu entries,
    # e.g., "1. Tracker Summary" and "2. Time Summary"
    lines = [c[3] for c in addstr_calls[1:]]
    assert any("1. Tracker Summary" in ln for ln in lines)
    assert any("2. Time Summary" in ln for ln in lines)

    # The last call should be noutrefresh
    assert pane.calls[-1][0] == 'noutrefresh'


def test_draw_report_exception(monkeypatch, patch_global):
    """
    Simulate an exception inside draw_report to verify the error path.
    We can force pane.getmaxyx to raise.
    """
    pane = DummyWin(h=5, w=20)
    # Monkeypatch getmaxyx to raise
    monkeypatch.setattr(pane, "getmaxyx", lambda: (
        _ for _ in ()).throw(ValueError("bad dims")))

    # Call draw_report and inspect for the error addstr
    draw_report(pane, h=5, w=20)

    # There should be an addstr call containing "Report err: bad dims"
    error_calls = [c for c in pane.calls if c[0] ==
                   'addstr' and "Report err: bad dims" in c[3]]
    assert error_calls, "draw_report should catch exception and display error message"
    assert patch_global["log_exception"], "log_exception should have been called on draw_report error"

# ────────────────────────────────────────────────────────────────────────────────
# 11. Tests for draw_burndown()
# ────────────────────────────────────────────────────────────────────────────────


def test_draw_burndown_normal(monkeypatch):
    """
    Provide a small list of tasks with due dates:
      - One task due yesterday (overdue)
      - One task due today (open but not overdue)
      - One task done (should be ignored)
    Verify that bars (# or !) are drawn correctly, and stats line appears.
    """
    pane = DummyWin(h=15, w=60)

    # Create three fake tasks
    now = datetime.now()
    yesterday = (now - timedelta(days=1)).isoformat()
    today = now.isoformat()
    tomorrow = (now + timedelta(days=1)).isoformat()

    fake_tasks = [
        {"id": 1, "due": yesterday, "status": "backlog"},   # overdue
        {"id": 2, "due": today, "status": "backlog"},       # open, not overdue
        {"id": 3, "due": tomorrow, "status": "done"},       # done → ignore
    ]
    monkeypatch.setattr(task_repository, "get_all_tasks", lambda: fake_tasks)

    draw_burndown(pane, h=15, w=60)

    # Verify first calls: 'erase', 'border', addstr for title " Task Burndown "
    assert pane.calls[0][0] == 'erase'
    assert pane.calls[1][0] == 'border'
    title_calls = [c for c in pane.calls if c[0]
                   == 'addstr' and "Task Burndown" in c[3]]
    assert title_calls, "Burndown title should appear"

    # Now find the stats line near the end: it should contain "Outstanding:" and "Overdue:"
    stats_calls = [c for c in pane.calls if c[0]
                   == 'addstr' and "Outstanding:" in c[3]]
    assert stats_calls, "draw_burndown should display Outstanding and Overdue counts"

    # Additionally, check that at least one bar character ("#" or "!") was drawn
    bar_calls = [c for c in pane.calls if c[0] ==
                 'addstr' and ("#" in c[3] or "!" in c[3])]
    assert bar_calls, "draw_burndown should draw bars (# or !)"


def test_draw_burndown_invalid_dates(monkeypatch):
    """
    Include a task with an invalid due date string; ensure it is skipped without crashing.
    """
    pane = DummyWin(h=10, w=40)
    fake_tasks = [
        {"id": 1, "due": "not-a-date", "status": "backlog"},
        {"id": 2, "due": None,          "status": "backlog"},
    ]
    monkeypatch.setattr(task_repository, "get_all_tasks", lambda: fake_tasks)

    # Should not raise; stats line appears with zero counts
    draw_burndown(pane, h=10, w=40)
    stats_calls = [c for c in pane.calls if c[0]
                   == 'addstr' and "Outstanding:" in c[3]]
    assert stats_calls, "Even with invalid dates, stats line should be displayed"


def test_draw_burndown_exception(monkeypatch, patch_global):
    """
    Simulate task_repository.get_all_tasks raising an exception.
    Ensure draw_burndown catches it and calls safe_addstr with error message.
    """
    pane = DummyWin(h=8, w=30)
    monkeypatch.setattr(task_repository, "get_all_tasks", lambda: (
        _ for _ in ()).throw(RuntimeError("fail fetch")))

    draw_burndown(pane, h=8, w=30)
    # Look for an addstr containing "Burndown err: fail fetch"
    error_calls = [c for c in pane.calls if c[0] ==
                   'addstr' and "Burndown err: fail fetch" in c[3]]
    assert error_calls, "draw_burndown should catch exception and display error"
    assert patch_global["log_exception"], "log_exception should have been called on burndown error"
