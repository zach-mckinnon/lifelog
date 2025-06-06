# tests/test_popups.py

import curses
from lifelog.ui_views.popups import popup_confirm, popup_error, popup_input, popup_multiline_input, popup_select_option
import pytest

# Again, ensure our DummyCurses is used
import sys
from types import SimpleNamespace


class DummyCurses:
    # Provide just enough to allow popups to run
    A_BOLD = 1
    A_DIM = 2
    A_REVERSE = 4
    KEY_BACKSPACE = 127
    ascii = SimpleNamespace(EOT=4)

    def __init__(self):
        pass

    def newwin(self, h, w, y, x):
        raise NotImplementedError("Monkeypatch newwin in tests")

    def curs_set(self, v):
        pass


# Inject DummyCurses
sys.modules['curses'] = DummyCurses()
sys.modules['curses.ascii'] = SimpleNamespace(EOT=4)


class DummyWin:
    """
    Dummy window with a queue of getch responses.
    Also logs addstr calls so we can assert what was drawn.
    """

    def __init__(self, h=10, w=40, input_sequence=None):
        self._h = h
        self._w = w
        self.calls = []
        self._input_seq = input_sequence or []
        self._cursor = 0

    def getmaxyx(self):
        return (self._h, self._w)

    def border(self):
        self.calls.append(('border',))

    def addstr(self, y, x, s, attr=0):
        self.calls.append(('addstr', y, x, s, attr))

    def refresh(self):
        self.calls.append(('refresh',))

    def clear(self):
        self.calls.append(('clear',))

    def touchwin(self):
        self.calls.append(('touchwin',))

    def keypad(self, v):
        self.calls.append(('keypad', v))

    def getch(self, *args, **kwargs):
        # Return next character code from sequence, or Enter if done
        if self._cursor < len(self._input_seq):
            c = self._input_seq[self._cursor]
            self._cursor += 1
            return c
        return 10  # Enter by default

    def nodelay(self, v):
        pass

    def move(self, y, x):
        pass

    def clrtoeol(self):
        pass


@pytest.fixture(autouse=True)
def patch_newwin(monkeypatch):
    """
    Monkeypatch curses.newwin to return DummyWin. For each popup,
    we can pass a different input_sequence by reassigning DummyWin._input_seq.
    """
    monkeypatch.setattr(curses, 'newwin', lambda h, w, y,
                        x: DummyWin(h, w, patch_newwin.input_seq))
    patch_newwin.input_seq = []
    return patch_newwin


def test_popup_confirm_yes(monkeypatch):
    # Simulate the user pressing 'y'
    patch_newwin.input_seq = [ord('y')]
    stdscr = DummyWin()
    result = popup_confirm(stdscr, "Confirm? (Y/n)")
    assert result is True

    # Simulate the user pressing 'n'
    patch_newwin.input_seq = [ord('n')]
    stdscr2 = DummyWin()
    result2 = popup_confirm(stdscr2, "Confirm? (Y/n)")
    assert result2 is False

    # Simulate ESC (27)
    patch_newwin.input_seq = [27]
    stdscr3 = DummyWin()
    result3 = popup_confirm(stdscr3, "Confirm? (Y/n)")
    assert result3 is False


def test_popup_input_simple(monkeypatch):
    # Provide “h”, “i”, Enter
    patch_newwin.input_seq = [ord('h'), ord('i'), 10]
    stdscr = DummyWin()
    response = popup_input(stdscr, "Enter text:", max_length=5)
    assert response == "hi"

    # Test backspace: “a”, backspace, “b”, Enter → should yield “b”
    patch_newwin.input_seq = [ord('a'), 127, ord('b'), 10]
    stdscr2 = DummyWin()
    response2 = popup_input(stdscr2, "Enter text:", max_length=5)
    assert response2 == "b"

    # Test ESC immediately → returns None
    patch_newwin.input_seq = [27]
    stdscr3 = DummyWin()
    response3 = popup_input(stdscr3, "Enter text:", max_length=5)
    assert response3 is None


def test_popup_multiline_input_basic(monkeypatch):
    # Simulate: “H”, “i”, Enter, “T”, “e”, “s”, “t”, Ctrl+D (EOT = 4)
    patch_newwin.input_seq = [ord('H'), ord('i'), 10, ord(
        'T'), ord('e'), ord('s'), ord('t'), curses.ascii.EOT]
    stdscr = DummyWin()
    result = popup_multiline_input(stdscr, "Enter notes:", initial="")
    assert "Hi" in result
    assert "Test" in result

    # Simulate ESC at start → returns initial (which we set to “Old”)
    patch_newwin.input_seq = [27]
    stdscr2 = DummyWin()
    result2 = popup_multiline_input(stdscr2, "Enter notes:", initial="Old")
    assert result2 == "Old"


def test_popup_select_option_basic(monkeypatch):
    # options=["A","B"], allow_new=False, user inputs “1”
    patch_newwin.input_seq = [ord('1')]
    stdscr = DummyWin()
    result = popup_select_option(stdscr, "Pick:", ["A", "B"], allow_new=False)
    assert result == "A"

    # options=["A","B"], allow_new=True, user inputs “3” to add new, then types “C”, Enter
    patch_newwin.input_seq = [ord('3'), ord('C'), 10]
    stdscr2 = DummyWin()
    result2 = popup_select_option(stdscr2, "Pick:", ["A", "B"], allow_new=True)
    assert result2 == "C"

    # Invalid digit → returns None
    patch_newwin.input_seq = [ord('9')]
    stdscr3 = DummyWin()
    result3 = popup_select_option(
        stdscr3, "Pick:", ["A", "B"], allow_new=False)
    assert result3 is None


def test_popup_error_shows_and_closes(monkeypatch):
    # Simulate an Exception instance
    patch_newwin.input_seq = [10]  # just press Enter to close
    stdscr = DummyWin()
    try:
        raise ValueError("Something bad")
    except ValueError as e:
        # Should not raise further
        popup_error(stdscr, e)

    # Simulate passing a multiline string
    patch_newwin.input_seq = [10]
    stdscr2 = DummyWin()
    popup_error(stdscr2, "Line1\nLine2")
    # We expect that border and addstr calls were made (at least one)
    assert any(call[0] == 'border' for call in stdscr2.calls)
    assert any("Line1" in call[3] or "Line2" in call[3]
               for call in stdscr2.calls)
