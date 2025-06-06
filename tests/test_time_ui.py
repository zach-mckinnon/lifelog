# tests/test_time_ui.py

from lifelog.utils.db.models import TimeLog
from lifelog.ui_views.time_ui import (
    set_time_period,
    get_time_period,
    _format_duration,
    get_since_from_period,
    draw_time,
    start_time_tui,
    add_manual_time_entry_tui,
    add_distracted_time_tui,
    edit_time_entry_tui,
    delete_time_entry_tui,
    stopwatch_tui,
    stop_time_tui,
    view_time_entry_tui,
    status_time_tui,
    summary_time_tui,
    TIME_PERIODS
)
import sys
import pytest
from types import SimpleNamespace
from datetime import datetime, timedelta

# ────────────────────────────────────────────────────────────────────────────────
# 1. Create a dummy curses module and inject it into sys.modules before importing time_ui
# ────────────────────────────────────────────────────────────────────────────────


class DummyCurses:
    A_BOLD = 1
    A_REVERSE = 2
    A_NORMAL = 0
    A_UNDERLINE = 3
    A_DIM = 4
    KEY_ENTER = 10

    def __init__(self):
        pass

    def curs_set(self, v):
        # no-op
        pass

    def newwin(self, h, w, y, x):
        # new windows are not used directly in time_ui; popups create their own windows
        raise NotImplementedError("Should be monkeypatched when needed")


# Make sure curses.ascii.EOT is defined for multiline input popups
DummyCurses.ascii = SimpleNamespace(EOT=4)

# Override the real curses module in sys.modules
sys.modules['curses'] = DummyCurses()
sys.modules['curses.ascii'] = DummyCurses.ascii

# ────────────────────────────────────────────────────────────────────────────────
# 2. Now we can import the functions under test
# ────────────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────────────
# 3. A minimal “window” stub to capture calls to addstr, border, erase, refresh, etc.
# ────────────────────────────────────────────────────────────────────────────────


class DummyWin:
    def __init__(self, h=20, w=60):
        self._h = h
        self._w = w
        self.calls = []  # store tuples of method calls

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

    def refresh(self):
        self.calls.append(('refresh',))

    def getch(self):
        # By default, return “no key” so loops that check getch() break immediately if they check != -1
        return -1

    def nodelay(self, flag):
        self.calls.append(('nodelay', flag))

# ────────────────────────────────────────────────────────────────────────────────
# 4. Fixtures to stub out all external dependencies
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def stub_repos_and_helpers(monkeypatch):
    """
    Stub out:
      - time_repository methods
      - shared_utils functions (parse_date_string, get_available_categories, get_available_projects, add_category_to_config, add_project_to_config)
      - popup functions (popup_input, popup_multiline_input, popup_select_option, popup_show, popup_confirm)
    """
    import lifelog.ui_views.time_ui as tui
    from lifelog.utils.db import time_repository
    from lifelog.utils import shared_utils
    from lifelog.ui_views.popups import popup_input, popup_multiline_input, popup_select_option, popup_show, popup_confirm

    # 4a. Stub time_repository methods
    #   - get_active_time_entry()
    #   - get_all_time_logs(since=...)
    #   - start_time_entry(log)
    #   - add_time_entry(log)
    #   - add_distracted_minutes_to_active(mins) -> return updated total
    #   - update_time_entry(id, **kwargs)
    #   - delete_time_entry(id)
    #   - stop_active_time_entry(end_time=..., tags=..., notes=...) -> return updated entry object

    # We'll store “current active” and “all logs” in local variables to simulate state
    active_entry = None
    all_logs = []

    def fake_get_active_time_entry():
        return active_entry

    def fake_get_all_time_logs(since=None):
        # ignore “since” for simplicity
        return list(all_logs)

    def fake_start_time_entry(log):
        nonlocal active_entry
        # log is a TimeLog instance; assign an id and use now as start if missing
        log.id = 99
        if not getattr(log, 'start', None):
            log.start = datetime.now()
        log.duration_minutes = 0
        log.distracted_minutes = 0
        active_entry = log
        all_logs.append(log)

    def fake_add_time_entry(log):
        # assign id and compute duration if not set
        log.id = 100
        if not getattr(log, 'duration_minutes', None):
            log.duration_minutes = 0
        log.distracted_minutes = getattr(log, 'distracted_minutes', 0)
        all_logs.append(log)

    def fake_add_distracted_minutes_to_active(mins):
        nonlocal active_entry
        if active_entry is None:
            return 0
        active_entry.distracted_minutes = (
            active_entry.distracted_minutes or 0) + mins
        return active_entry.distracted_minutes

    def fake_update_time_entry(entry_id, **kwargs):
        for e in all_logs:
            if e.id == entry_id:
                for k, v in kwargs.items():
                    setattr(e, k, v)
                return e
        raise KeyError("No such entry")

    def fake_delete_time_entry(entry_id):
        nonlocal all_logs
        all_logs = [e for e in all_logs if e.id != entry_id]

    def fake_stop_active_time_entry(end_time=None, tags=None, notes=None):
        nonlocal active_entry
        if active_entry is None:
            return None
        # update end, notes, tags, compute duration
        active_entry.end = end_time or datetime.now()
        active_entry.tags = tags or active_entry.tags
        active_entry.notes = notes or active_entry.notes
        active_entry.duration_minutes = (
            active_entry.end - active_entry.start).total_seconds() / 60
        out = active_entry
        active_entry = None
        return out

    monkeypatch.setattr(time_repository, "get_active_time_entry",
                        lambda: fake_get_active_time_entry())
    monkeypatch.setattr(time_repository, "get_all_time_logs",
                        lambda since=None: fake_get_all_time_logs(since))
    monkeypatch.setattr(time_repository, "start_time_entry",
                        lambda log: fake_start_time_entry(log))
    monkeypatch.setattr(time_repository, "add_time_entry",
                        lambda log: fake_add_time_entry(log))
    monkeypatch.setattr(time_repository, "add_distracted_minutes_to_active",
                        lambda mins: fake_add_distracted_minutes_to_active(mins))
    monkeypatch.setattr(time_repository, "update_time_entry",
                        lambda eid, **kw: fake_update_time_entry(eid, **kw))
    monkeypatch.setattr(time_repository, "delete_time_entry",
                        lambda eid: fake_delete_time_entry(eid))
    monkeypatch.setattr(time_repository, "stop_active_time_entry",
                        lambda **kw: fake_stop_active_time_entry(**kw))

    # 4b. Stub shared_utils functions
    monkeypatch.setattr(shared_utils, "parse_date_string",
                        lambda s: datetime.now())
    monkeypatch.setattr(
        shared_utils, "get_available_categories", lambda: ["Work", "Home"])
    monkeypatch.setattr(shared_utils, "get_available_projects",
                        lambda: ["ProjA", "ProjB"])
    monkeypatch.setattr(shared_utils, "add_category_to_config", lambda c: None)
    monkeypatch.setattr(shared_utils, "add_project_to_config", lambda p: None)

    # 4c. Stub popup functions so they do not block
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_multiline_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_select_option", lambda *args, **kwargs: None)
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda *args, **kwargs: True)

    yield


# ────────────────────────────────────────────────────────────────────────────────
# 5. Tests for simple pure‐functions: set/get, formatting, since logic
# ────────────────────────────────────────────────────────────────────────────────

def test_set_and_get_time_period():
    # Default at import is "week"
    assert get_time_period() == "week"
    set_time_period("day")
    assert get_time_period() == "day"
    set_time_period("month")
    assert get_time_period() == "month"
    set_time_period("all")
    assert get_time_period() == "all"
    # Invalid input should not change
    set_time_period("xyz")
    assert get_time_period() == "all"


@pytest.mark.parametrize("minutes,expected", [
    (30, "30 min"),
    (60, "1 hr 0 min"),
    (90, "1 hr 30 min"),
    (125, "2 hr 5 min"),
])
def test_format_duration(minutes, expected):
    assert _format_duration(minutes) == expected


@pytest.mark.parametrize("period,delta_days", [
    ("day", 1),
    ("week", 7),
    ("month", 30),
    ("all", 3650),  # roughly 10 years
])
def test_get_since_from_period(period, delta_days):
    cutoff = get_since_from_period(period)
    diff = datetime.now() - cutoff
    # Allow a small margin (seconds difference)
    assert abs(diff.total_seconds() / 86400 - delta_days) < 0.01


# ────────────────────────────────────────────────────────────────────────────────
# 6. Tests for draw_time()
# ────────────────────────────────────────────────────────────────────────────────

def test_draw_time_no_active_and_no_history():
    pane = DummyWin(h=10, w=40)
    # Ensure repo returns no active and no logs
    # draw_time should draw "(no history)" and return selected_idx = 0
    sel = draw_time(pane, h=10, w=40, selected_idx=5)
    assert sel == 0

    # Check that at least one addstr call contains "(no history)"
    assert any("(no history)" in call[3]
               for call in pane.calls if call[0] == 'addstr')


def test_draw_time_with_active_and_history(monkeypatch):
    pane = DummyWin(h=15, w=50)
    # Create a fake active entry that started 10 minutes ago
    now = datetime.now()
    fake_active = TimeLog(id=1, title="TestActivity",
                          start=now - timedelta(minutes=10))
    # Monkeypatch get_active_time_entry to return fake_active
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: fake_active)

    # Also monkeypatch get_all_time_logs to return a list of TimeLog instances
    log1 = TimeLog(id=2, title="Log1", start=now -
                   timedelta(hours=2), duration_minutes=120)
    log2 = TimeLog(id=3, title="Log2", start=now -
                   timedelta(days=1), duration_minutes=60)
    monkeypatch.setattr(tr_mod, "get_all_time_logs",
                        lambda since=None: [log1, log2])

    # Call draw_time with a selected_idx out of range; it should clamp to valid range
    sel_out = draw_time(pane, h=15, w=50, selected_idx=10)
    # There are 2 logs, so valid indices are 0 or 1; since 10 > 1, it clamps to 1
    assert sel_out == 1

    # Check that the active entry was printed with "▶ TestActivity"
    assert any("▶ TestActivity" in call[3]
               for call in pane.calls if call[0] == 'addstr')

    # Check that the log lines appear (ID and title and minutes)
    assert any(" 2 Log1" in call[3]
               for call in pane.calls if call[0] == 'addstr')
    assert any(" 3 Log2" in call[3]
               for call in pane.calls if call[0] == 'addstr')


# ────────────────────────────────────────────────────────────────────────────────
# 7. Tests for start_time_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_start_time_tui_empty_title(monkeypatch):
    pane = DummyWin()
    # Stub popup_input so title="" → returns immediately
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "")
    start_time_tui(pane)
    # No exception, and pane.calls remains empty because popup_input returned "" immediately
    assert pane.calls == []


def test_start_time_tui_creates_entry(monkeypatch):
    pane = DummyWin()
    calls = {"started": False}

    # 1) Simulate user inputs for all popups in order:
    #    title, category, project, tags, notes, task_id, past
    seq = iter([
        "MyTask",      # title
        "Work",        # category
        "ProjA",       # project
        "tag1,tag2",   # tags
        "some notes",  # notes
        "42",          # task_id
        "10m ago"      # past
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_select_option", lambda *args, **kwargs: "Work")
    # Stub repository.start_time_entry to record the fact
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "start_time_entry",
                        lambda log: calls.update({"started": True}))
    # Finally, stub popup_confirm to record the confirmation call
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda stdscr, msg: calls.update({"confirm_msg": msg}) or True)

    start_time_tui(pane)
    # Ensure repository was called
    assert calls["started"] is True
    # Ensure popup_confirm was called with a message containing “Started 'MyTask'”
    assert "Started 'MyTask'" in calls["confirm_msg"]


# ────────────────────────────────────────────────────────────────────────────────
# 8. Tests for add_manual_time_entry_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_add_manual_time_entry_tui_invalid_time(monkeypatch):
    pane = DummyWin()
    inputs = iter([
        "TaskA",     # title
        "Work",      # category
        "ProjA",     # project
        "tagX",      # tags
        "notesX",    # notes
        "",          # task_id
        "not-a-time",  # start_str → will trigger invalid parse_date_string
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(inputs))
    # Stub parse_date_string to raise on invalid
    from lifelog.utils import shared_utils as su_mod
    monkeypatch.setattr(su_mod, "parse_date_string", lambda s: (
        _ for _ in ()).throw(ValueError("bad")))
    # Stub popup_show to record calls
    called = {"shown": False}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: called.update({"shown": True}))
    add_manual_time_entry_tui(pane)
    assert called["shown"] is True


def test_add_manual_time_entry_tui_success(monkeypatch):
    pane = DummyWin()
    # Valid sequence:
    #  title, category, project, tags, notes, task_id, start_str, end_str, distracted_str
    now = datetime.now()
    fake_start = (now - timedelta(hours=1)).isoformat()
    fake_end = now.isoformat()
    seq = iter([
        "ManualTask",   # title
        "Work",         # category
        "ProjB",        # project
        "tag1",         # tags
        "note1",        # notes
        "5",            # task_id
        fake_start,     # start_str
        fake_end,       # end_str
        "15"            # distracted_str
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    # Stub parse_date_string to return datetime from isoformat
    from lifelog.utils import shared_utils as su_mod
    monkeypatch.setattr(su_mod, "parse_date_string",
                        lambda s: datetime.fromisoformat(s))
    # Stub time_repository.add_time_entry to record the fact
    import lifelog.utils.db.time_repository as tr_mod
    called = {"added": False}

    def fake_add_time_entry(log):
        called["added"] = True
        log.id = 123
        return log
    monkeypatch.setattr(tr_mod, "add_time_entry", fake_add_time_entry)
    # Stub popup_show to capture
    shown = {"lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: shown.update({"lines": lines}))
    add_manual_time_entry_tui(pane)
    assert called["added"] is True
    # The popup message should mention “Time entry 'ManualTask' added”
    assert any(
        "Time entry 'ManualTask' added" in line for line in shown["lines"])


# ────────────────────────────────────────────────────────────────────────────────
# 9. Tests for add_distracted_time_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_add_distracted_time_tui_invalid(monkeypatch):
    pane = DummyWin()
    # First popup_input returns “abc” → invalid int
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "abc")
    called = {"shown": False}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: called.update({"shown": True}))
    add_distracted_time_tui(pane)
    assert called["shown"] is True


def test_add_distracted_time_tui_no_active(monkeypatch):
    pane = DummyWin()
    # popup_input returns “10” (valid), but get_active_time_entry returns None
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "10")
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: None)
    called = {"shown": False}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: called.update({"shown": True}))
    add_distracted_time_tui(pane)
    assert called["shown"] is True


def test_add_distracted_time_tui_success(monkeypatch):
    pane = DummyWin()
    # popup_input returns “5”
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "5")
    # Provide a fake active entry
    fake_active = SimpleNamespace(
        id=10, title="Test", start=datetime.now(), distracted_minutes=2)
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: fake_active)
    # Stub add_distracted_minutes_to_active to return new total 7
    monkeypatch.setattr(
        tr_mod, "add_distracted_minutes_to_active", lambda m: 7)
    called = {"shown": False, "lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: called.update({"shown": True, "lines": lines}))
    add_distracted_time_tui(pane)
    assert called["shown"] is True
    # The popup line should mention “Added 5 distracted min”
    assert any("Added 5 distracted min" in line for line in called["lines"])


# ────────────────────────────────────────────────────────────────────────────────
# 10. Tests for edit_time_entry_tui() and delete_time_entry_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_edit_time_entry_tui(monkeypatch):
    pane = DummyWin()
    # Create a fake log entry
    now = datetime.now()
    fake_entry = TimeLog(
        id=20,
        title="E1",
        start=now - timedelta(hours=2),
        end=now - timedelta(hours=1),
        duration_minutes=60,
        category="Work",
        project="ProjA",
        tags="t1",
        notes="n1",
        distracted_minutes=5
    )
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_all_time_logs",
                        lambda since=None: [fake_entry])

    # Prepare popup_input sequence to change tags, notes, distracted
    seq = iter([
        "newtags",   # new_tags
        "newnotes",  # new_notes
        "10"         # new distracted
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    called = {"shown": False}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: called.update({"shown": True}))
    edit_time_entry_tui(pane, sel=0)
    # Ensure popup_show was called with “Updated entry #20”
    assert called["shown"] is True


def test_delete_time_entry_tui(monkeypatch):
    pane = DummyWin()
    now = datetime.now()
    fake_entry = TimeLog(
        id=30,
        title="E2",
        start=now - timedelta(hours=3),
        end=now - timedelta(hours=2),
        duration_minutes=60
    )
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_all_time_logs",
                        lambda since=None: [fake_entry])
    # popup_confirm returns True by default (stubbed)
    called = {"shown": False}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: called.update({"shown": True}))
    # Stub delete_time_entry to record
    called2 = {"deleted": False}
    monkeypatch.setattr(tr_mod, "delete_time_entry",
                        lambda eid: called2.update({"deleted": True}))
    delete_time_entry_tui(pane, sel=0)
    assert called2["deleted"] is True
    assert called["shown"] is True


# ────────────────────────────────────────────────────────────────────────────────
# 11. Tests for stopwatch_tui() and stop_time_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_stopwatch_tui_no_active(monkeypatch):
    pane = DummyWin(h=5, w=30)
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: None)
    # Call stopwatch_tui; it should add a warning line and return immediately
    pane.calls.clear()
    stopwatch_tui(pane)
    # Look for "No active timer" in addstr
    assert any("No active timer" in c[3]
               for c in pane.calls if c[0] == 'addstr')


def test_stopwatch_tui_with_active(monkeypatch):
    pane = DummyWin(h=5, w=30)
    now = datetime.now()
    fake_entry = TimeLog(id=40, title="Run", start=now - timedelta(seconds=1))
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: fake_entry)
    # Monkeypatch getch so that the loop breaks immediately
    pane.getch = lambda: ord('q')  # any key != -1
    pane.calls.clear()
    # To avoid real sleep, monkeypatch time.sleep to no-op
    import time as time_mod
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)
    stopwatch_tui(pane)
    # It should have drawn the elapsed time once and then exited
    assert any("Run" in c[3] or ":" in c[3]
               for c in pane.calls if c[0] == 'addstr')


def test_stop_time_tui_no_active(monkeypatch):
    pane = DummyWin()
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: None)
    called = {"confirmed": False}
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda stdscr, msg: called.update({"confirmed": True}) or False)
    stop_time_tui(pane)
    # Since there was no active, popup_confirm would be called (and return False)
    assert called["confirmed"] is True


def test_stop_time_tui_success(monkeypatch):
    pane = DummyWin()
    now = datetime.now()
    fake_entry = SimpleNamespace(
        id=50,
        title="TaskStop",
        start=now - timedelta(minutes=30),
        distracted_minutes=5,
        tags="t1",
        notes="n1"
    )
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: fake_entry)
    # Prepare popup_input for tags, notes, past
    seq = iter([
        "",       # tags (leave as-is)
        "",       # notes
        "5m ago"  # past
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    # Stub parse_date_string to return now - 5m
    from lifelog.utils import shared_utils as su_mod
    monkeypatch.setattr(su_mod, "parse_date_string",
                        lambda s: now - timedelta(minutes=5))
    # Stub stop_active_time_entry to return an updated entry with distracted_minutes
    updated = SimpleNamespace(
        id=50,
        title="TaskStop",
        start=fake_entry.start,
        end=now - timedelta(minutes=5),
        duration_minutes=25,
        distracted_minutes=5
    )
    monkeypatch.setattr(tr_mod, "stop_active_time_entry", lambda **kw: updated)
    # Stub popup_confirm to capture final message
    called = {"msg": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda stdscr, m: called.update({"msg": m}) or True)
    stop_time_tui(pane)
    # The confirmation message should contain "Stopped" and the title
    assert "Stopped. 25" in called["msg"] and "TaskStop" in called["msg"]


# ────────────────────────────────────────────────────────────────────────────────
# 12. Tests for view_time_entry_tui() and status_time_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_view_time_entry_tui(monkeypatch):
    pane = DummyWin()
    now = datetime.now()
    fake_entry = SimpleNamespace(
        id=60,
        title="V1",
        category="Cat",
        project="Proj",
        tags="T1,T2",
        notes="NoteX",
        start=now - timedelta(hours=2),
        end=now - timedelta(hours=1),
        duration_minutes=60,
        distracted_minutes=10
    )
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_all_time_logs",
                        lambda since=None: [fake_entry])
    called = {"shown": False, "lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: called.update({"shown": True, "lines": lines}))
    view_time_entry_tui(pane, sel=0)
    assert called["shown"] is True
    # Lines should contain "Title:" and "Duration:"
    assert any("Title:    V1" in line for line in called["lines"])
    assert any("Duration: 60 min" in line for line in called["lines"])


def test_status_time_tui_no_active(monkeypatch):
    pane = DummyWin()
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: None)
    called = {"shown": False, "lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: called.update({"shown": True, "lines": lines}))
    status_time_tui(pane)
    assert called["shown"] is True
    assert any("No active timer." in line for line in called["lines"])


def test_status_time_tui_with_active(monkeypatch):
    pane = DummyWin()
    now = datetime.now()
    fake_entry = SimpleNamespace(
        id=70,
        title="StatTest",
        start=now - timedelta(minutes=30),
        distracted_minutes=5,
        category=None,
        project=None,
        tags=None,
        notes=None
    )
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_active_time_entry", lambda: fake_entry)
    called = {"shown": False, "lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: called.update({"shown": True, "lines": lines}))
    status_time_tui(pane)
    assert called["shown"] is True
    # Lines should contain Title and Elapsed
    assert any("Title:   StatTest" in line for line in called["lines"])
    assert any("Elapsed:" in line for line in called["lines"])


# ────────────────────────────────────────────────────────────────────────────────
# 13. Tests for summary_time_tui()
# ────────────────────────────────────────────────────────────────────────────────

def test_summary_time_tui_no_records(monkeypatch):
    pane = DummyWin()
    # popup_input sequence: first “group by” = "", second “period” = ""
    seq = iter(["", ""])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    # time_repository.get_all_time_logs returns empty
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_all_time_logs", lambda since=None: [])
    called = {"shown": False, "lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: called.update({"shown": True, "lines": lines}))
    summary_time_tui(pane)
    assert called["shown"] is True
    assert any("No records found." in line for line in called["lines"])


def test_summary_time_tui_with_records(monkeypatch):
    pane = DummyWin()
    now = datetime.now()
    # Create two logs with different categories
    entry1 = SimpleNamespace(
        id=80, title="T1", start=now - timedelta(days=1), duration_minutes=50, category="CatA", project=None, tags=None, notes=None, distracted_minutes=0
    )
    entry2 = SimpleNamespace(
        id=81, title="T2", start=now - timedelta(hours=5), duration_minutes=30, category="CatB", project=None, tags=None, notes=None, distracted_minutes=0
    )
    import lifelog.utils.db.time_repository as tr_mod
    monkeypatch.setattr(tr_mod, "get_all_time_logs",
                        lambda since=None: [entry1, entry2])
    # popup_input: first “group by” = "category", second “period” = "day"
    seq = iter(["category", "day"])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    called = {"shown": False, "lines": None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: called.update({"shown": True, "lines": lines}))
    summary_time_tui(pane)
    assert called["shown"] is True
    # The first line should be "Category        Total"
    first_line = called["lines"][0]
    assert "Category" in first_line and "Total" in first_line
    # There should be lines for CatA and CatB
    assert any("CatA" in line for line in called["lines"])
    assert any("CatB" in line for line in called["lines"])
