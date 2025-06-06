# tests/test_tasks_ui.py

from lifelog.ui_views.popups import popup_confirm, popup_input, popup_show
from lifelog.utils.db import task_repository, time_repository, track_repository
import builtins
from lifelog.utils.db.models import Task
from lifelog.ui_views.tasks_ui import draw_agenda, add_task_tui, delete_task_tui, edit_task_tui, quick_add_task_tui, focus_mode_tui, set_task_reminder_tui, done_task_tui
import pytest
from datetime import datetime, timedelta

# Monkeypatch curses again
import sys
from types import SimpleNamespace


class DummyCursesUI:
    A_BOLD = 1
    A_REVERSE = 2
    A_NORMAL = 0
    A_UNDERLINE = 3
    KEY_DOWN = 258
    KEY_UP = 259

    def __init__(self):
        pass

    def newwin(self, h, w, y, x):
        raise NotImplementedError("Monkepatch in test")

    def curs_set(self, v):
        pass

    def use_default_colors(self):
        pass

    def start_color(self):
        pass

    def init_pair(self, a, b, c):
        pass

    def color_pair(self, idx):
        return idx


# Inject DummyCursesUI into sys.modules so that tasks_ui.py sees it
sys.modules['curses'] = DummyCursesUI()


# Create a dummy window for all tests

class DummyWin:
    def __init__(self, h=30, w=80):
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

    def keypad(self, v):
        self.calls.append(('keypad', v))

    def getch(self):
        return -1  # No keypress

    def touchwin(self):
        self.calls.append(('touchwin',))

    def clear(self):
        self.calls.append(('clear',))

    def move(self, y, x):
        self.calls.append(('move', y, x))


# Stub out task_repository and time_repository


@pytest.fixture(autouse=True)
def stub_repos(monkeypatch):
    """
    Provide dummy implementations of task_repository.query_tasks, get_all_tasks, etc.
    """
    # A small set of two tasks with due dates near “today”
    now = datetime.now()
    two_tasks = [
        {
            "id": 1,
            "title": "Task1",
            "due": (now + timedelta(days=1)).isoformat(),
            "status": "backlog",
            "category": None,
            "project": None,
            "priority": 1,
            "notes": None,
            "tags": None,
        },
        {
            "id": 2,
            "title": "Task2",
            "due": (now + timedelta(days=2)).isoformat(),
            "status": "backlog",
            "category": None,
            "project": None,
            "priority": 2,
            "notes": None,
            "tags": None,
        },
    ]
    # query_tasks returns list of dicts
    monkeypatch.setattr(task_repository, "query_tasks",
                        lambda **kwargs: two_tasks)
    monkeypatch.setattr(task_repository, "get_all_tasks",
                        lambda: [Task(**t) for t in two_tasks])

    # For focus_mode_tui, time_repository.get_active_time_entry and others:
    monkeypatch.setattr(time_repository, "get_active_time_entry", lambda: None)
    monkeypatch.setattr(time_repository, "start_time_entry",
                        lambda **kwargs: None)
    monkeypatch.setattr(time_repository, "get_all_time_logs", lambda: [])
    monkeypatch.setattr(
        time_repository, "stop_active_time_entry", lambda **kwargs: None)

    yield


@pytest.fixture(autouse=True)
def patch_popups(monkeypatch):
    """
    Monkeypatch popup_confirm, popup_input, popup_show to no‐ops or fixed returns.
    """
    monkeypatch.setattr(
        'livelog.ui_views.popups.popup_confirm', lambda stdscr, msg: True)
    monkeypatch.setattr('livelog.ui_views.popups.popup_input',
                        lambda *args, **kwargs: "dummy")
    monkeypatch.setattr(
        'livelog.ui_views.popups.popup_multiline_input', lambda *args, **kwargs: "notes")
    monkeypatch.setattr(
        'livelog.ui_views.popups.popup_select_option', lambda *args, **kwargs: None)
    monkeypatch.setattr('livelog.ui_views.popups.popup_show',
                        lambda *args, **kwargs: None)
    yield


def test_draw_agenda_renders_and_returns_index_zero():
    pane = DummyWin(h=20, w=80)
    # Call draw_agenda with selected_idx=0
    idx = draw_agenda(pane, h=20, w=80, selected_idx=0)
    # Should return 0 (since no navigation keys were pressed)
    assert idx == 0
    # We should see that 'Agenda' title was added
    assert any("Agenda" in call[3]
               for call in pane.calls if call[0] == 'addstr')


def test_quick_add_task_tui_adds_and_popups(monkeypatch):
    """
    quick_add_task_tui calls popup_input for the title. We stub that to return “MyTask”.
    Then it constructs a Task and calls task_repository.add_task, followed by a popup_show.
    """
    pane = DummyWin()
    # Stub popup_input to return empty -> test no title path as well
    monkeypatch.setattr('livelog.ui_views.popups.popup_input',
                        lambda *args, **kwargs: "")
    # Should simply popup “Title required.” and return
    quick_add_task_tui(pane)
    assert any("Title required." in call[3]
               for call in pane.calls if call[0] == 'addstr')

    pane.calls.clear()
    # Now stub popup_input to return a valid title
    monkeypatch.setattr('livelog.ui_views.popups.popup_input',
                        lambda *args, **kwargs: "ValidTitle")
    # Also stub task_repository.add_task to record that it was called
    called = {"added": False}
    monkeypatch.setattr(task_repository, "add_task",
                        lambda task: called.update({"added": True}))
    quick_add_task_tui(pane)
    assert called["added"] is True
    # Should see popup “Quick Task 'ValidTitle' added!”
    assert any("Quick Task 'ValidTitle' added!" in call[3]
               for call in pane.calls if call[0] == 'addstr')


def test_delete_task_tui_no_tasks_shows_popup(monkeypatch):
    pane = DummyWin()
    # Stub query_tasks to return empty
    monkeypatch.setattr(task_repository, "query_tasks", lambda **kwargs: [])
    delete_task_tui(pane, sel=0)
    # Should popup “No tasks to delete”
    assert any("No tasks to delete" in call[3]
               for call in pane.calls if call[0] == 'addstr')


def test_delete_task_tui_deletes_when_confirmed(monkeypatch):
    pane = DummyWin()
    # Stub query_tasks to return one task with id=1
    monkeypatch.setattr(task_repository, "query_tasks",
                        lambda **kwargs: [{"id": 1}])
    called = {"deleted": False}
    monkeypatch.setattr(task_repository, "delete_task",
                        lambda tid: called.update({"deleted": True}))
    # popup_confirm has been stubbed to always return True
    delete_task_tui(pane, sel=0)
    assert called["deleted"] is True
    assert any("Deleted task #1" in call[3]
               for call in pane.calls if call[0] == 'addstr')


def test_edit_task_tui_invalid_input_shows_popup(monkeypatch):
    pane = DummyWin()
    # Stub get_all_tasks to return a Task with missing required fields
    # title="" is invalid based on validate_task_inputs
    bad_task = Task(id=5, title="", created=None)
    monkeypatch.setattr(task_repository, "get_all_tasks", lambda: [bad_task])
    # popup_input returns "" for everything
    monkeypatch.setattr('livelog.ui_views.popups.popup_input',
                        lambda *args, **kwargs: "")
    pane.calls.clear()
    edit_task_tui(pane, sel=0)
    # Should catch validation error and popup “Error updating task”
    assert any("Error updating task" in call[3]
               for call in pane.calls if call[0] == 'addstr')


def test_done_task_tui_marks_done_and_stops_time(monkeypatch):
    pane = DummyWin()
    # Prepare a “running” time entry
    now = datetime.now().isoformat()
    active_entry = {"task_id": 7, "start": now}
    monkeypatch.setattr(
        time_repository, "get_active_time_entry", lambda: active_entry)
    # Prepare a corresponding task
    running_task = {"id": 7, "title": "RunMe", "tags": None, "notes": None}
    monkeypatch.setattr(task_repository, "query_tasks",
                        lambda **kwargs: [running_task])
    # Stub task_repository.update_task and time_repository.stop_active_time_entry
    called = {"updated": False, "stopped": False}
    monkeypatch.setattr(time_repository, "stop_active_time_entry",
                        lambda **kwargs: called.update({"stopped": True}))
    monkeypatch.setattr(task_repository, "update_task",
                        lambda tid, ups: called.update({"updated": True}))
    pane.calls.clear()
    done_task_tui(pane, sel=0)
    assert called["stopped"] is True
    assert called["updated"] is True
    assert any("marked done" in call[3]
               for call in pane.calls if call[0] == 'addstr')
