# tests/test_ui_helpers.py

from lifelog.ui_views.ui_helpers import draw_status, draw_menu, create_pane, tag_picker_tui, log_exception, safe_addstr
import sys
import pytest

# We will monkeypatch the curses module attributes used by ui_helpers.py
import builtins

# Create a dummy curses namespace to inject


class DummyCurses:
    A_BOLD = 1
    A_NORMAL = 0
    A_REVERSE = 2
    A_UNDERLINE = 3
    COLOR_WHITE = 0
    COLOR_BLUE = 1
    COLOR_BLACK = 2
    COLOR_CYAN = 3

    def __init__(self):
        self._color_pairs = {}

    def color_pair(self, idx):
        # Just return idx for simplicity
        return idx

    def curs_set(self, v):
        # no-op
        pass

    def newwin(self, h, w, y, x):
        # This will be monkeypatched in tests if needed
        raise NotImplementedError("newwin should be monkeypatched in tests")

    def hline(self, *args, **kwargs):
        # In tests, stdscr.hline is often called
        pass


# Insert DummyCurses into sys.modules so that ui_helpers.py sees it
_dummy = DummyCurses()
sys.modules['curses'] = _dummy

# Now import the functions under test


class SimpleWindow:
    """
    A minimal 'window-like' object that collects calls to addstr, hline, border, etc.
    """

    def __init__(self, h=10, w=40):
        self._h = h
        self._w = w
        self.calls = []

    def getmaxyx(self):
        return (self._h, self._w)

    def addstr(self, y, x, s, attr=0):
        # Record each call for assertions
        self.calls.append(('addstr', y, x, s, attr))

    def hline(self, y, x, ch, n):
        self.calls.append(('hline', y, x, ch, n))

    def attron(self, cp):
        self.calls.append(('attron', cp))

    def attroff(self, cp):
        self.calls.append(('attroff', cp))

    def border(self):
        self.calls.append(('border',))

    def keypad(self, flag):
        self.calls.append(('keypad', flag))

    def refresh(self):
        self.calls.append(('refresh',))

    def touchwin(self):
        self.calls.append(('touchwin',))

    def erase(self):
        self.calls.append(('erase',))

    def clrtoeol(self):
        self.calls.append(('clrtoeol',))

    def getch(self):
        # Not used in ui_helpers
        return -1


@pytest.fixture(autouse=True)
def patch_newwin(monkeypatch):
    """
    Monkey‐patch curses.newwin so that create_pane calls our SimpleWindow.
    Also ensure curses.color_pair returns the same index.
    """
    monkeypatch.setattr(_dummy, 'newwin', lambda h,
                        w, y, x: SimpleWindow(h, w))
    monkeypatch.setattr(_dummy, 'color_pair', lambda idx: idx)
    yield


def test_draw_menu_highlights_current_tab():
    stdscr = SimpleWindow(h=5, w=50)
    tabs = ["H", "TSK", "TM", "TRK", "R"]
    current = 2  # Should highlight the third tab ("TM")
    # Call draw_menu
    draw_menu(stdscr, tabs, current, stdscr._w, color_pair=42)

    # Expected sequence:
    #  - attron(42)
    #  - hline at row=2
    #  - attroff(42)
    #  - then five addstr calls, one per tab label
    calls = stdscr.calls

    # 1) attron
    assert calls[0][0] == 'attron' and calls[0][1] == 42

    # 2) hline (row=2)
    assert calls[1][0] == 'hline' and calls[1][1] == 2

    # 3) attroff(42)
    assert calls[2][0] == 'attroff' and calls[2][1] == 42

    # 4) Five addstr calls for each tab. The 'TM' tab (index=2) should use A_REVERSE (2).
    addstr_calls = [c for c in calls if c[0] == 'addstr']
    assert len(addstr_calls) == len(tabs)
    # Verify that the third addstr uses A_REVERSE
    _, y, x, text, attr = addstr_calls[2]
    assert "TM" in text
    assert attr == _dummy.A_REVERSE


def test_draw_status_displays_correct_hint_for_each_tab():
    stdscr = SimpleWindow(h=6, w=80)

    # Tab 0: Home
    draw_status(stdscr, 6, 80, 0)
    home_call = stdscr.calls[-1]
    assert "←/→" in home_call[3]

    # Tab 1: Tasks
    stdscr.calls.clear()
    draw_status(stdscr, 6, 80, 1)
    tasks_call = stdscr.calls[-1]
    assert "a:Add" in tasks_call[3] and "s:Start" in tasks_call[3]

    # Tab 2: Time
    stdscr.calls.clear()
    draw_status(stdscr, 6, 80, 2)
    time_call = stdscr.calls[-1]
    assert "s:Start" in time_call[3] and "p:Stop" in time_call[3]

    # Tab 3: Trackers
    stdscr.calls.clear()
    draw_status(stdscr, 6, 80, 3)
    trk_call = stdscr.calls[-1]
    assert "a:Add" in trk_call[3] and "g:Goal" in trk_call[3]

    # Tab 4: Reports
    stdscr.calls.clear()
    draw_status(stdscr, 6, 80, 4)
    rep_call = stdscr.calls[-1]
    assert "1-4:Run Report" in rep_call[3] and "C:Insights" in rep_call[3]


def test_create_pane_returns_bordered_window():
    stdscr = SimpleWindow(h=20, w=80)
    # menu_h=3, so body_h = 20 - 3 - 1 = 16
    pane = create_pane(stdscr, menu_h=3, h=20, w=80,
                       title="Test", x=5, color_pair=7)
    # Should be a SimpleWindow with height=16, width=80
    assert isinstance(pane, SimpleWindow)
    assert pane._h == 16 and pane._w == 80

    # The pane should have had a border() call and an addstr for the title
    found_border = any(c[0] == 'border' for c in pane.calls)
    found_title = any("Test" in c[3] for c in pane.calls if c[0] == 'addstr')
    assert found_border
    assert found_title


def test_safe_addstr_truncates_and_ignores_out_of_bounds():
    pane = SimpleWindow(h=3, w=10)  # small window
    # Call safe_addstr with out-of-bounds coordinates
    safe_addstr(pane, y=5, x=1, s="Hello", attr=0)
    # Should not raise, and not record a call since y=5 >= h=3
    assert all(call[0] != 'addstr' for call in pane.calls)

    # In‐bounds but string too long: it should truncate so that x + len(s) < max_x
    pane.calls.clear()
    long_text = "X" * 20  # much wider than w=10
    safe_addstr(pane, y=1, x=2, s=long_text, attr=0)
    recorded = [c for c in pane.calls if c[0] == 'addstr']
    assert recorded, "safe_addstr should have recorded an addstr call"
    y, x, text, attr = recorded[0][1:]
    assert y == 1 and x == 2
    # The truncated text length must be ≤ (max_x - x - 1) = 10 - 2 - 1 = 7
    assert len(text) <= 7


def test_tag_picker_tui_select_and_add_new(monkeypatch):
    """
    For tag_picker_tui, we simulate user interactions via popup_show and popup_input.
    We'll monkeypatch popup_show to do nothing, and popup_input to return specific sequences.
    """
    from lifelog.ui_views.ui_helpers import tag_picker_tui
    from lifelog.ui_views.popups import popup_show, popup_input

    stdscr = SimpleWindow(h=15, w=40)
    existing_tags = ["tag1", "tag2", "tag3"]

    sequence = ["0",    # select 'tag1'
                "+",    # choose to add new
                "newTag",  # input new tag
                "done"]    # finish
    inputs = iter(sequence)

    monkeypatch.setattr(
        'livelog.ui_views.ui_helpers.popup_show', lambda *args, **kwargs: None)
    monkeypatch.setattr('livelog.ui_views.ui_helpers.popup_input',
                        lambda *args, **kwargs: next(inputs))

    result = tag_picker_tui(stdscr, existing_tags.copy())
    # It should return "tag1,newTag"
    assert "tag1" in result and "newTag" in result
