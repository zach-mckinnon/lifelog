# tests/test_trackers_ui.py

from lifelog.utils.db.models import Tracker, TrackerEntry
from lifelog.ui_views.trackers_ui import (
    draw_trackers,
    add_tracker_tui,
    log_entry_tui,
    delete_tracker_tui,
    edit_tracker_tui,
    log_tracker_entry_tui,
    view_tracker_tui,
    draw_goal_progress_tui,
    view_goal_tui,
    view_goals_list_tui,
    create_goal_interactive_tui,
    show_goals_help_tui,
    add_or_edit_goal_tui,
    delete_goal_tui,
)
import sys
import pytest
from types import SimpleNamespace
from datetime import datetime

# ────────────────────────────────────────────────────────────────────────────────
# 1. Inject a dummy curses module before importing trackers_ui
# ────────────────────────────────────────────────────────────────────────────────


class DummyCurses:
    A_BOLD = 1
    A_REVERSE = 2
    A_NORMAL = 0
    A_UNDERLINE = 3
    KEY_DOWN = 258
    KEY_UP = 259
    # color_pair simply returns its argument

    def color_pair(self, idx):
        return idx

    def curs_set(self, v):
        pass

    def newwin(self, h, w, y, x):
        raise NotImplementedError("Monkeypatch newwin if needed")


# Replace the real curses module with our dummy
sys.modules['curses'] = DummyCurses()

# ────────────────────────────────────────────────────────────────────────────────
# 2. Now import trackers_ui and its dependencies
# ────────────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────────────
# 3. A minimal “window” stub to capture calls
# ────────────────────────────────────────────────────────────────────────────────


class DummyWin:
    def __init__(self, h=20, w=60):
        self._h = h
        self._w = w
        self.calls = []  # record of (method, *args)

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
        # No key pressed by default
        return -1

    def clear(self):
        self.calls.append(('clear',))

# ────────────────────────────────────────────────────────────────────────────────
# 4. Fixtures: stub out all external dependencies (track_repository, popups, shared_utils)
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def stub_repos_and_popups(monkeypatch):
    """
    Stub out track_repository, popups, and shared_utils so that:
      - get_all_trackers(), get_tracker_by_id(), etc. return predictable data
      - popup_input, popup_select_option, popup_confirm, popup_show never block
      - goal/report generation is stubbed to avoid real DB work
    """
    import lifelog.utils.db.track_repository as trep
    import lifelog.utils.shared_utils as su
    from lifelog.ui_views.popups import popup_input, popup_select_option, popup_confirm, popup_show

    # 4a. Create an in‐memory “database” for trackers, entries, goals
    #    Format: trackers = [ {id, title, type, category, created, tags, notes}, ... ]
    #            entries_by_tracker = {tracker_id: [TrackerEntry, ...]}
    #            goals_by_tracker   = {tracker_id: [goal_dict, ...]}

    trackers = []
    entries_by_tracker = {}
    goals_by_tracker = {}

    # Helper: next tracker ID
    next_tracker_id = {'val': 1}

    # Stub get_all_trackers()
    def fake_get_all_trackers():
        # Return a list of plain dicts (field names as in code)
        return [t.copy() for t in trackers]

    # Stub get_tracker_by_id(id)
    def fake_get_tracker_by_id(tid):
        for t in trackers:
            if t['id'] == tid:
                return t.copy()
        return None

    # Stub add_tracker(Tracker)
    def fake_add_tracker(tracker_obj):
        # tracker_obj is a Tracker dataclass instance
        tid = next_tracker_id['val']
        next_tracker_id['val'] += 1
        tdict = {
            'id': tid,
            'title': tracker_obj.title,
            'type': tracker_obj.type,
            'category': tracker_obj.category,
            'created': tracker_obj.created,
            'tags': tracker_obj.tags,
            'notes': tracker_obj.notes,
        }
        trackers.append(tdict)
        entries_by_tracker[tid] = []
        goals_by_tracker[tid] = []
        # Return nothing (UI code doesn’t use return)
        return

    # Stub update_tracker(id, updates)
    def fake_update_tracker(tid, updates):
        for t in trackers:
            if t['id'] == tid:
                t.update(updates)
                return t.copy()
        raise KeyError(f"No tracker {tid}")

    # Stub delete_tracker(id)
    def fake_delete_tracker(tid):
        nonlocal trackers
        trackers[:] = [t for t in trackers if t['id'] != tid]
        entries_by_tracker.pop(tid, None)
        goals_by_tracker.pop(tid, None)

    # Stub get_all_trackers_with_entries() (for draw_goal_progress)
    def fake_get_all_trackers_with_entries():
        # Return tracker dicts each with an 'entries' list
        out = []
        for t in trackers:
            # For simplicity, return tracker title + type + category + created + tags + notes + id
            d = t.copy()
            # Convert TrackerEntry objects to plain dicts
            ents = [
                {
                    'tracker_id': e.tracker_id,
                    'timestamp': e.timestamp,
                    'value': e.value
                }
                for e in entries_by_tracker.get(t['id'], [])
            ]
            d['entries'] = ents
            out.append(d)
        return out

    # Stub add_tracker_entry(tracker_id, timestamp, value)
    def fake_add_tracker_entry(tracker_id, timestamp, value):
        e = TrackerEntry(
            id=len(entries_by_tracker.get(tracker_id, [])) + 1,
            tracker_id=tracker_id,
            timestamp=timestamp,
            value=value
        )
        entries_by_tracker[tracker_id].append(e)
        return e

    # Stub get_goals_for_tracker(tracker_id)
    def fake_get_goals_for_tracker(tracker_id):
        # Return a shallow copy
        return [g.copy() for g in goals_by_tracker.get(tracker_id, [])]

    # Stub add_goal(tracker_id, goal_data)
    def fake_add_goal(tracker_id, goal_data):
        # Assign a fake goal ID
        goal_data = goal_data.copy()
        goal_data['id'] = len(goals_by_tracker.get(tracker_id, [])) + 1
        goal_data['tracker_id'] = tracker_id
        goals_by_tracker[tracker_id].append(goal_data)
        return goal_data

    # Stub delete_goal(goal_id)
    def fake_delete_goal(goal_id):
        for tid, gl in goals_by_tracker.items():
            if any(g['id'] == goal_id for g in gl):
                goals_by_tracker[tid] = [g for g in gl if g['id'] != goal_id]
                return
        raise KeyError(f"No goal {goal_id}")

    # Stub get_entries_for_tracker(tracker_id)
    def fake_get_entries_for_tracker(tracker_id):
        return list(entries_by_tracker.get(tracker_id, []))

    # Apply all of these to track_repository
    monkeypatch.setattr(trep, "get_all_trackers",
                        lambda: fake_get_all_trackers())
    monkeypatch.setattr(trep, "get_tracker_by_id",
                        lambda tid: fake_get_tracker_by_id(tid))
    monkeypatch.setattr(trep, "add_tracker",
                        lambda tracker: fake_add_tracker(tracker))
    monkeypatch.setattr(trep, "update_tracker", lambda tid,
                        ups: fake_update_tracker(tid, ups))
    monkeypatch.setattr(trep, "delete_tracker",
                        lambda tid: fake_delete_tracker(tid))
    monkeypatch.setattr(trep, "get_all_trackers_with_entries",
                        lambda: fake_get_all_trackers_with_entries())
    monkeypatch.setattr(trep, "add_tracker_entry", lambda tracker_id, timestamp,
                        value: fake_add_tracker_entry(tracker_id, timestamp, value))
    monkeypatch.setattr(trep, "get_goals_for_tracker",
                        lambda tid: fake_get_goals_for_tracker(tid))
    monkeypatch.setattr(trep, "add_goal", lambda tracker_id,
                        gd: fake_add_goal(tracker_id, gd))
    monkeypatch.setattr(trep, "delete_goal", lambda gid: fake_delete_goal(gid))
    monkeypatch.setattr(trep, "get_entries_for_tracker",
                        lambda tid: fake_get_entries_for_tracker(tid))
    # Also stub get_entries_for_tracker used by log_tracker_entry_tui
    monkeypatch.setattr(trep, "add_tracker_entry", lambda **kwargs: fake_add_tracker_entry(
        kwargs['tracker_id'], kwargs['timestamp'], kwargs['value']))

    # 4b. Stub shared_utils for category/tag lists and popup interactions
    import lifelog.utils.shared_utils as su_mod
    monkeypatch.setattr(su_mod, "get_available_categories",
                        lambda: ["CatA", "CatB"])
    monkeypatch.setattr(su_mod, "get_available_tags", lambda: ["tag1", "tag2"])
    monkeypatch.setattr(su_mod, "add_category_to_config", lambda c: None)

    # 4c. Stub all popups so they do not block and return controlled values
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_select_option", lambda *args, **kwargs: None)
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda *args, **kwargs: False)
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda *args, **kwargs: None)

    yield

# ────────────────────────────────────────────────────────────────────────────────
# 5. Test draw_trackers()
# ────────────────────────────────────────────────────────────────────────────────


def test_draw_trackers_empty_list(monkeypatch):
    pane = DummyWin()
    # Ensure get_all_trackers() returns empty (our fixture has an empty `trackers` list)
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [])
    draw_trackers(pane, h=10, w=40, selected_idx=0, color_pair=5)
    # Since no trackers, there should be no 'addstr' calls after border— only erase and border
    methods = [c[0] for c in pane.calls]
    assert methods[:2] == ['erase', 'border']
    # No lines after that
    assert all(m in ('erase', 'border', 'noutrefresh') for m in methods)


def test_draw_trackers_with_items(monkeypatch):
    pane = DummyWin()
    # Populate one tracker in the in‐memory list
    from lifelog.utils.db import track_repository as trep
    # Simulate a single tracker
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [
        {'id': 1, 'title': 'T1', 'type': 'int', 'category': 'CatA',
         'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    ])
    draw_trackers(pane, h=10, w=40, selected_idx=0, color_pair=7)
    # We expect: erase, border, then one addstr with the tracker line, then noutrefresh
    methods = [c[0] for c in pane.calls]
    assert methods[0] == 'erase'
    assert methods[1] == 'border'
    # The third call should be 'addstr'
    assert pane.calls[2][0] == 'addstr'
    # And that line should contain ID “ 1” and title “T1”
    _, _, _, text, attr = pane.calls[2]
    assert " 1" in text and "T1" in text
    # Because selected_idx=0, that addstr used A_REVERSE (2)
    assert attr == 2

# ────────────────────────────────────────────────────────────────────────────────
# 6. Test add_tracker_tui() with and without a goal
# ────────────────────────────────────────────────────────────────────────────────


def test_add_tracker_tui_no_title_shows_nothing(monkeypatch):
    pane = DummyWin()
    # popup_input returns empty string → add_tracker_tui should return immediately
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "")
    # Because popup_input returned "", no calls to repository and no calls to popup_show
    add_tracker_tui(pane)
    assert pane.calls == []


def test_add_tracker_tui_with_title_and_no_goal(monkeypatch):
    pane = DummyWin()
    seq = iter([
        "MyTracker",    # title
        "int",          # type (popup_select_option)
        "CatA",         # category
        "",             # tags from tag_picker_tui
        "",             # notes
        # popup_confirm → says “no” (keep default False), so skip goal creation
    ])
    # First popup_input → “MyTracker”
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq))
    # Next popup_select_option → “int”, then “CatA”
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_select_option", lambda *args, **kwargs: next(seq))
    # popup_confirm returns False by default
    # Stub track_repository.add_tracker so we can see that it was called
    from lifelog.utils.db import track_repository as trep
    called = {'added': False}
    monkeypatch.setattr(trep, "add_tracker",
                        lambda tracker: called.update({'added': True}))
    # Now run:
    add_tracker_tui(pane)
    assert called['added'] is True
    # After adding, popup_show should be called once (to show “Tracker 'MyTracker' added!”)
    # Because we stubbed popup_show to no-op, we only check that popup_show was invoked (monkeypatch replaced it)
    # So pane.calls is still empty (popup_show is no-op), but we know add_tracker ran.


def test_add_tracker_tui_with_goal(monkeypatch):
    pane = DummyWin()
    # Prepare a goal‐creating sequence: title, type, category, tags, notes, then confirm “yes” to add goal.
    seq_input = iter([
        "GoalTracker",   # popup_input → title
        # type via popup_select_option:
        "int",           # popup_select_option → type
        # category via popup_select_option:
        "CatA",          # popup_select_option → category
        # tags from tag_picker_tui:
        "",              # tag_picker_tui returns ""
        "",              # notes
        # popup_confirm → yes
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: next(seq_input))
    monkeypatch.setattr("livelog.ui_views.popups.popup_select_option",
                        lambda *args, **kwargs: next(seq_input))
    # Make popup_confirm return True so we go into create_goal_interactive_tui
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda *args, **kwargs: True)

    # Now override create_goal_interactive_tui to return a dummy goal dict
    dummy_goal = {'title': 'G1', 'kind': 'sum',
                  'period': 'day', 'amount': 5.0, 'unit': 'unit'}
    monkeypatch.setattr(
        "livelog.ui_views.trackers_ui.create_goal_interactive_tui", lambda stdscr, ttype: dummy_goal)

    # Stub repository methods so we see them called
    from lifelog.utils.db import track_repository as trep
    called = {'add_tracker': False, 'add_goal': False}
    monkeypatch.setattr(trep, "add_tracker",
                        lambda tracker: called.update({'add_tracker': True}))
    # The code expects to use tracker.id after insertion; simulate that by setting tracker.id via side‐effect

    def fake_add_tracker_and_set_id(tracker_obj):
        # assign id=99 to the passed dataclass
        tracker_obj.id = 99
        called['add_tracker'] = True
    monkeypatch.setattr(trep, "add_tracker", fake_add_tracker_and_set_id)
    monkeypatch.setattr(trep, "add_goal", lambda tracker_id,
                        gd: called.update({'add_goal': True}))

    # Finally, run:
    add_tracker_tui(pane)
    assert called['add_tracker'] is True
    assert called['add_goal'] is True

# ────────────────────────────────────────────────────────────────────────────────
# 7. Test log_entry_tui() when no trackers exist
# ────────────────────────────────────────────────────────────────────────────────


def test_log_entry_tui_no_trackers(monkeypatch):
    pane = DummyWin()
    # get_all_trackers returns [] by default
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [])
    # popup_show should be invoked with “No trackers found”
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    log_entry_tui(pane)
    assert shown['called']
    assert any("No trackers found" in line for line in shown['lines'])


def test_log_entry_tui_invalid_value(monkeypatch):
    pane = DummyWin()
    # Create a single “bool” tracker so we take that branch
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [
        {'id': 1, 'title': 'Tbool', 'type': 'bool', 'category': 'CatA',
            'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    ])
    # popup_select_option for selecting tracker → returns "Tbool [bool]"
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_select_option", lambda stdscr, msg, opts: opts[0])
    # Now, since type='bool', code calls popup_select_option to ask for True/False. Return invalid by default (None)
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "")
    # popup_show to capture errors
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    log_entry_tui(pane)
    # Because value selection was None, value becomes 0. Code proceeds to timestamp; no exception.
    # We expect a successful “Entry logged for ...” popup
    assert shown['called']
    assert any("Entry logged for Tbool" in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 8. Test delete_tracker_tui() for missing and existing tracker
# ────────────────────────────────────────────────────────────────────────────────


def test_delete_tracker_tui_not_found(monkeypatch):
    pane = DummyWin()
    # No trackers at all
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: None)
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    delete_tracker_tui(pane, sel=5)
    assert shown['called']
    assert any("Tracker ID 5 not found" in line for line in shown['lines'])


def test_delete_tracker_tui_success(monkeypatch):
    pane = DummyWin()
    # Create one tracker
    from lifelog.utils.db import track_repository as trep
    tracker_dict = {'id': 2, 'title': 'TK2', 'type': 'int', 'category': 'CatA',
                    'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    monkeypatch.setattr(trep, "get_tracker_by_id",
                        lambda tid: tracker_dict if tid == 2 else None)
    # popup_confirm should return True
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_confirm", lambda stdscr, msg: True)
    # Stub delete_tracker to record
    called = {'deleted': False}
    monkeypatch.setattr(trep, "delete_tracker",
                        lambda tid: called.update({'deleted': True}))
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    delete_tracker_tui(pane, sel=2)
    assert called['deleted']
    assert shown['called']
    assert any("Tracker 'TK2' deleted" in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 9. Test edit_tracker_tui() for missing and no‐change/edit cases
# ────────────────────────────────────────────────────────────────────────────────


def test_edit_tracker_tui_not_found(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: None)
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    edit_tracker_tui(pane, sel=99)
    assert shown['called']
    assert any("Tracker ID 99 not found" in line for line in shown['lines'])


def test_edit_tracker_tui_no_changes(monkeypatch):
    pane = DummyWin()
    tdict = {'id': 3, 'title': 'T3', 'type': 'int', 'category': 'CatA',
             'created': datetime.now().isoformat(), 'tags': 'tag1', 'notes': 'note1'}
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: tdict.copy())
    # popup_input for new_title returns empty → new_title = old title
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_input", lambda stdscr, msg: "")
    # popup_select_option for category returns empty → no change
    monkeypatch.setattr("livelog.ui_views.popups.popup_select_option",
                        lambda stdscr, msg, opts, allow_new=False: "")
    # tag_picker_tui returns existing tags
    monkeypatch.setattr("livelog.ui_views.ui_helpers.tag_picker_tui",
                        lambda stdscr, tags: tdict['tags'])
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    edit_tracker_tui(pane, sel=3)
    assert shown['called']
    assert any("No changes made." in line for line in shown['lines'])


def test_edit_tracker_tui_with_changes(monkeypatch):
    pane = DummyWin()
    tdict = {'id': 4, 'title': 'OldTitle', 'type': 'int', 'category': 'CatA',
             'created': datetime.now().isoformat(), 'tags': 'tag1', 'notes': 'note1'}
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: tdict.copy())
    # Change title, category, tags, notes
    seq_input = iter([
        "NewTitle",   # new title
        # For category:
        "CatB",       # popup_select_option returns CatB
        # For tags:
        "tag2",       # tag_picker_tui returns "tag2"
        # For notes:
        "newnotes",   # popup_input returns "newnotes"
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda stdscr, msg: next(seq_input))
    monkeypatch.setattr("livelog.ui_views.popups.popup_select_option",
                        lambda stdscr, msg, opts, allow_new=False: next(seq_input))
    monkeypatch.setattr("livelog.ui_views.ui_helpers.tag_picker_tui",
                        lambda stdscr, tags: next(seq_input))
    called = {'updated': False}
    monkeypatch.setattr(trep, "update_tracker", lambda tid,
                        ups: called.update({'updated': True}))
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    edit_tracker_tui(pane, sel=4)
    assert called['updated']
    assert shown['called']
    assert any(
        "Tracker 'NewTitle' updated!" in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 10. Test log_tracker_entry_tui() with invalid and valid value
# ────────────────────────────────────────────────────────────────────────────────


def test_log_tracker_entry_tui_not_found(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: None)
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    log_tracker_entry_tui(pane, sel=10)
    assert shown['called']
    assert any("Tracker ID 10 not found" in line for line in shown['lines'])


def test_log_tracker_entry_tui_invalid_int(monkeypatch):
    pane = DummyWin()
    # Create an “int” tracker
    tdict = {'id': 5, 'title': 'T5', 'type': 'int', 'category': None,
             'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: tdict.copy())
    # Input string that cannot be converted to float/int
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "not_a_number")
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    log_tracker_entry_tui(pane, sel=5)
    assert shown['called']
    # Expect “Invalid integer value.” in popup
    assert any("Invalid integer value." in line for line in shown['lines'])


def test_log_tracker_entry_tui_success(monkeypatch):
    pane = DummyWin()
    tdict = {'id': 6, 'title': 'T6', 'type': 'float', 'category': None,
             'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_tracker_by_id", lambda tid: tdict.copy())
    # Input “12.5” which is valid float
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda *args, **kwargs: "12.5")
    # Stub add_tracker_entry to record
    called = {'added': False}
    monkeypatch.setattr(trep, "add_tracker_entry",
                        lambda entry: called.update({'added': True}))
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    log_tracker_entry_tui(pane, sel=6)
    assert called['added']
    assert shown['called']
    assert any("Entry logged for 'T6'." in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 11. Test view_tracker_tui()
# ────────────────────────────────────────────────────────────────────────────────


def test_view_tracker_tui(monkeypatch):
    pane = DummyWin()
    # Create one tracker and one goal and one entry
    now = datetime.now().isoformat()
    tracker_dict = {'id': 7, 'title': 'T7', 'type': 'int',
                    'category': 'CatA', 'created': now, 'tags': 'tag1', 'notes': 'note1'}
    goal = {'id': 1, 'title': 'Goal1', 'kind': 'sum', 'period': 'day',
            'amount': 5.0, 'unit': 'u', 'tracker_id': 7, 'progress': 2.0, 'current': 2.0}
    entry = {'id': 1, 'tracker_id': 7, 'timestamp': now, 'value': 3.0}

    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_all_trackers",
                        lambda: [tracker_dict.copy()])
    monkeypatch.setattr(trep, "get_goals_for_tracker", lambda tid: [
                        goal.copy()] if tid == 7 else [])
    monkeypatch.setattr(trep, "get_entries_for_tracker", lambda tid: [
                        entry.copy()] if tid == 7 else [])

    # Capture popup_show
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: shown.update({'called': True, 'lines': lines}))
    view_tracker_tui(pane, sel=0)
    assert shown['called']
    # The lines should include “Title:    T7” and “Goals:    1” and “Entries:  1”
    assert any("Title:    T7" in line for line in shown['lines'])
    assert any("Goals:    1" in line for line in shown['lines'])
    assert any("Entries:  1" in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 12. Test draw_goal_progress_tui() calls generate_goal_report
# ────────────────────────────────────────────────────────────────────────────────


def test_draw_goal_progress_tui(monkeypatch):
    pane = DummyWin()
    # Create one Tracker dataclass with id=8
    tracker_obj = Tracker(id=8, title="T8", type="int", category="CatA",
                          created=datetime.now(), tags=None, notes=None, goals=None)
    # Stub get_goals_for_tracker to yield one goal dict
    from lifelog.utils.db import track_repository as trep
    goal_dict = {'id': 2, 'title': 'G2', 'kind': 'sum',
                 'period': 'day', 'amount': 10.0, 'unit': 'u', 'tracker_id': 8}
    monkeypatch.setattr(trep, "get_goals_for_tracker", lambda tid: [
                        goal_dict.copy()] if tid == 8 else [])
    # Stub generate_goal_report to return a known dict
    from lifelog.commands.report import generate_goal_report
    monkeypatch.setattr("livelog.ui_views.trackers_ui.generate_goal_report", lambda tr, g: {
                        'progress': 2, 'target': 10, 'current': 2})
    draw_goal_progress_tui(pane, tracker_obj)
    # We expect three addstr calls (one for each line of lines[])
    adds = [c for c in pane.calls if c[0] == 'addstr']
    assert len(adds) == 3
    # First line should start with "Goal: G2"
    assert "Goal: G2" in adds[0][3]

# ────────────────────────────────────────────────────────────────────────────────
# 13. Test view_goal_tui()
# ────────────────────────────────────────────────────────────────────────────────


def test_view_goal_tui_no_goals(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [
                        {'id': 9, 'title': 'T9', 'type': 'int', 'category': 'CatA', 'created': datetime.now().isoformat(), 'tags': None, 'notes': None}])
    monkeypatch.setattr(trep, "get_goals_for_tracker", lambda tid: [])
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    view_goal_tui(pane, tracker_sel=0, goal_idx=0)
    assert shown['called']
    assert any("No goals found" in line for line in shown['lines'])


def test_view_goal_tui_with_goal(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    # One tracker and one goal of kind “range”
    tracker_dict = {'id': 10, 'title': 'T10', 'type': 'int', 'category': 'CatA',
                    'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    goal_dict = {
        'id': 3, 'title': 'G3', 'kind': 'range', 'period': 'day',
        'min_amount': 1.0, 'max_amount': 5.0, 'unit': 'u', 'mode': 'goal', 'tracker_id': 10
    }
    monkeypatch.setattr(trep, "get_all_trackers",
                        lambda: [tracker_dict.copy()])
    monkeypatch.setattr(trep, "get_goals_for_tracker",
                        lambda tid: [goal_dict.copy()])
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: shown.update({'called': True, 'lines': lines}))
    view_goal_tui(pane, tracker_sel=0, goal_idx=0)
    assert shown['called']
    # Should contain lines “Title:   G3”, “Min:      1.0”, “Max:      5.0”
    assert any("Title:   G3" in line for line in shown['lines'])
    assert any("Min:      1.0" in line for line in shown['lines'])
    assert any("Max:      5.0" in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 14. Test view_goals_list_tui() navigation and view_goal calls
# ────────────────────────────────────────────────────────────────────────────────


def test_view_goals_list_tui_no_goals(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [
                        {'id': 11, 'title': 'T11', 'type': 'int', 'category': 'CatA', 'created': datetime.now().isoformat(), 'tags': None, 'notes': None}])
    monkeypatch.setattr(trep, "get_goals_for_tracker", lambda tid: [])
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None: shown.update({'called': True, 'lines': lines}))
    view_goals_list_tui(pane, tracker_sel=0)
    assert shown['called']
    assert any("No goals found" in line for line in shown['lines'])


def test_view_goals_list_tui_navigation(monkeypatch):
    pane = DummyWin()
    # One tracker with two goals
    from lifelog.utils.db import track_repository as trep
    tracker_dict = {'id': 12, 'title': 'T12', 'type': 'int', 'category': 'CatA',
                    'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    goal1 = {'id': 4, 'title': 'G4', 'kind': 'sum', 'period': 'day',
             'amount': 1.0, 'unit': 'u', 'tracker_id': 12}
    goal2 = {'id': 5, 'title': 'G5', 'kind': 'count',
             'period': 'week', 'amount': 2.0, 'unit': 'u', 'tracker_id': 12}
    monkeypatch.setattr(trep, "get_all_trackers",
                        lambda: [tracker_dict.copy()])
    monkeypatch.setattr(trep, "get_goals_for_tracker",
                        lambda tid: [goal1.copy(), goal2.copy()])

    # We'll simulate: one loop iteration drawing both, then pressing 'q' to exit
    # So we need pane.getch() to return ord('q')
    pane.getch = lambda: ord('q')

    # Capture popup_show calls
    show_calls = []
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines, title=None, wait=True: show_calls.append((lines, title)))
    # We also stub view_goal_tui so that if Enter were pressed, a secondary popup would appear; but since we press 'q', no Enter
    monkeypatch.setattr(
        "livelog.ui_views.trackers_ui.view_goal_tui", lambda stdscr, ts, gi: None)
    view_goals_list_tui(pane, tracker_sel=0)
    # We should have seen at least one popup_show call for listing the goals
    assert len(show_calls) >= 1
    # The first popup should show "G4" and "G5" in its lines
    lines, title = show_calls[0]
    assert any("G4" in line for line in lines)
    assert any("G5" in line for line in lines)

# ────────────────────────────────────────────────────────────────────────────────
# 15. Test create_goal_interactive_tui() for different kinds
# ────────────────────────────────────────────────────────────────────────────────


def test_create_goal_interactive_tui_sum(monkeypatch):
    pane = DummyWin()
    # Tracker type = “int” → allowed_kinds includes “sum”
    from lifelog.utils.goal_util import GoalKind, Period
    # Step-by-step popup inputs:
    # 1) popup_select_option for kind: “sum: ...”
    # 2) popup_input for title: “Gsum”
    # 3) popup_select_option for period: “day”
    # 4) popup_input for amount: “10”
    # 5) popup_input for unit: “u”
    seq_select = iter([f"{GoalKind.SUM.value}: {''}", Period.DAY.value])
    seq_input = iter(["Gsum", "10", "u"])
    monkeypatch.setattr("livelog.ui_views.popups.popup_select_option",
                        lambda stdscr, msg, opts, allow_new=False: next(seq_select))
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda stdscr, msg, max_length=None: next(seq_input))
    result = create_goal_interactive_tui(pane, tracker_type="int")
    assert result['kind'] == GoalKind.SUM.value
    assert result['title'] == "Gsum"
    assert result['amount'] == 10.0
    assert result['unit'] == "u"


def test_create_goal_interactive_tui_bool(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.goal_util import GoalKind, Period
    # For bool, allowed_kinds includes “bool”
    seq_select = iter([f"{GoalKind.BOOL.value}: {''}", Period.DAY.value])
    seq_input = iter(["Gbool"])  # only title; no extra input needed for amount
    monkeypatch.setattr("livelog.ui_views.popups.popup_select_option",
                        lambda stdscr, msg, opts, allow_new=False: next(seq_select))
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda stdscr, msg, max_length=None: next(seq_input))
    result = create_goal_interactive_tui(pane, tracker_type="bool")
    assert result['kind'] == GoalKind.BOOL.value
    assert result['title'] == "Gbool"
    assert result['amount'] is True


def test_create_goal_interactive_tui_invalid_kind(monkeypatch):
    pane = DummyWin()
    # Provide a tracker_type that’s unsupported
    # popup_select_option shouldn’t be called because code immediately calls popup_show & returns None
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    result = create_goal_interactive_tui(pane, tracker_type="unsupported")
    assert result is None
    assert shown['called']
    assert any("Unsupported type for goals" in line for line in shown['lines'])

# ────────────────────────────────────────────────────────────────────────────────
# 16. Test show_goals_help_tui()
# ────────────────────────────────────────────────────────────────────────────────


def test_show_goals_help_tui(monkeypatch):
    pane = DummyWin()
    shown = {'called': False, 'lines': None, 'title': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr, lines,
                        title=None: shown.update({'called': True, 'lines': lines, 'title': title}))
    show_goals_help_tui(pane)
    assert shown['called']
    assert "Goal Kinds:" in shown['lines'][0]
    assert shown['title'].strip() == "Goal Types"

# ────────────────────────────────────────────────────────────────────────────────
# 17. Test add_or_edit_goal_tui() for create and edit flows
# ────────────────────────────────────────────────────────────────────────────────


def test_add_or_edit_goal_tui_create(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    # One existing tracker
    tracker_dict = {'id': 13, 'title': 'T13', 'type': 'int', 'category': 'CatA',
                    'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    monkeypatch.setattr(trep, "get_all_trackers",
                        lambda: [tracker_dict.copy()])
    # Popup_input sequence: kind, title, period, amount, unit
    seq_input = iter([
        "sum",       # kind
        "Gcreate",   # title
        "day",       # period
        "5",         # amount
        "u"          # unit
    ])
    # popup_show to show description of kind
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: None)
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda stdscr, msg: next(seq_input))
    # Stub add_goal
    called = {'added': False}
    monkeypatch.setattr(trep, "add_goal", lambda tid,
                        gd: called.update({'added': True}))
    add_or_edit_goal_tui(pane, tracker_sel=0, edit_goal=None)
    assert called['added']


def test_add_or_edit_goal_tui_edit(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    tracker_dict = {'id': 14, 'title': 'T14', 'type': 'int', 'category': 'CatA',
                    'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    goal_existing = {'id': 6, 'title': 'OldG', 'kind': 'count',
                     'period': 'week', 'amount': 3.0, 'unit': 'u', 'tracker_id': 14}
    # Stub get_all_trackers and get_goals_for_tracker
    monkeypatch.setattr(trep, "get_all_trackers",
                        lambda: [tracker_dict.copy()])
    # For editing, code reads goals to prefill defaults; we can ignore that and just simulate inputs
    monkeypatch.setattr(trep, "get_goals_for_tracker",
                        lambda tid: [goal_existing.copy()])
    # popup_show to show description
    monkeypatch.setattr("livelog.ui_views.popups.popup_show",
                        lambda stdscr, lines, title=None: None)
    # popup_input sequence: keep kind same, new title, new period, new amount, new unit
    seq_input = iter([
        "",          # keep kind
        "NewGoal",   # new title
        "",          # keep period
        "10",        # new amount
        "unit2"      # new unit
    ])
    monkeypatch.setattr("livelog.ui_views.popups.popup_input",
                        lambda stdscr, msg: next(seq_input))
    # Stub delete_goal and add_goal (edit flow deletes then re-add)
    called = {'deleted': False, 'added': False}
    monkeypatch.setattr(trep, "delete_goal",
                        lambda gid: called.update({'deleted': True}))
    monkeypatch.setattr(trep, "add_goal", lambda tid,
                        gd: called.update({'added': True}))
    add_or_edit_goal_tui(pane, tracker_sel=0, edit_goal=goal_existing)
    assert called['deleted'] and called['added']

# ────────────────────────────────────────────────────────────────────────────────
# 18. Test delete_goal_tui() for no goals, cancel, and confirm paths
# ────────────────────────────────────────────────────────────────────────────────


def test_delete_goal_tui_no_goals(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    tracking = {'id': 15, 'title': 'T15', 'type': 'int', 'category': 'CatA',
                'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [tracking.copy()])
    monkeypatch.setattr(trep, "get_goals_for_tracker", lambda tid: [])
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    delete_goal_tui(pane, tracker_sel=0)
    assert shown['called']
    assert any("No goal to delete" in line for line in shown['lines'])


def test_delete_goal_tui_cancel(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    tracking = {'id': 16, 'title': 'T16', 'type': 'int', 'category': 'CatA',
                'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    goal_dict = {'id': 7, 'title': 'G7', 'kind': 'sum',
                 'period': 'day', 'amount': 1.0, 'unit': '', 'tracker_id': 16}
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [tracking.copy()])
    monkeypatch.setattr(trep, "get_goals_for_tracker",
                        lambda tid: [goal_dict.copy()])
    # First popup_confirm (delete)? return False → cancel immediately
    monkeypatch.setattr(
        "livelog.ui_views.popups.popup_confirm", lambda stdscr, msg: False)
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    delete_goal_tui(pane, tracker_sel=0)
    # Because user canceled deletion, only one popup would have happened (Cancel path may not call popup_show further)
    # We simply assert no exception and that no “Goal deleted” message appears
    assert not any("Goal deleted" in line for line in (shown['lines'] or []))


def test_delete_goal_tui_confirm(monkeypatch):
    pane = DummyWin()
    from lifelog.utils.db import track_repository as trep
    tracking = {'id': 17, 'title': 'T17', 'type': 'int', 'category': 'CatA',
                'created': datetime.now().isoformat(), 'tags': None, 'notes': None}
    goal_dict = {'id': 8, 'title': 'G8', 'kind': 'sum',
                 'period': 'day', 'amount': 1.0, 'unit': '', 'tracker_id': 17}
    monkeypatch.setattr(trep, "get_all_trackers", lambda: [tracking.copy()])
    monkeypatch.setattr(trep, "get_goals_for_tracker",
                        lambda tid: [goal_dict.copy()])
    # popup_confirm: first True (delete), second True (really delete)
    seq_conf = iter([True, True])
    monkeypatch.setattr("livelog.ui_views.popups.popup_confirm",
                        lambda stdscr, msg: next(seq_conf))
    called = {'deleted': False}
    monkeypatch.setattr(trep, "delete_goal",
                        lambda gid: called.update({'deleted': True}))
    shown = {'called': False, 'lines': None}
    monkeypatch.setattr("livelog.ui_views.popups.popup_show", lambda stdscr,
                        lines: shown.update({'called': True, 'lines': lines}))
    delete_goal_tui(pane, tracker_sel=0)
    assert called['deleted']
    assert shown['called']
    assert any("Goal deleted" in line for line in shown['lines'])
