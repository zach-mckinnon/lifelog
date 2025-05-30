# ─── Popups & Helpers ─────────────────────────────────────────────────

from datetime import datetime
import textwrap
import curses
import traceback

LOG_FILE = "/tmp/lifelog_tui.log"


def show_help_popup(stdscr, current_tab):
    lines = []
    if current_tab == 1:
        lines = [
            "Agenda/Tasks Tab:",
            "a: Add Task      q: Quick Add      c: Clone      F: Focus Mode",
            "m: Custom Reminder   d: Delete      e: Edit      v: View",
            "s: Start Timer   p: Stop Timer     o: Mark Done     f: Cycle Filter",
            "r: Edit Recurrence   n: Edit Notes",
            "",
            "↑/↓: Move   ←/→: Switch Tab   ?: Help   Q: Quit"
        ]
    elif current_tab == 2:
        lines = [
            "Time Tab:",
            "s: Start Timer   a/l: Manual Entry   p: Stop Timer   v: Timer Status",
            "t/Enter: View Entry   y: Summary   e: Edit Entry   x: Delete Entry",
            "w: Stopwatch    W/D/M/A: Set Period",
            "",
            "↑/↓: Move   ←/→: Switch Tab   ?: Help   Q: Quit"
        ]
    elif current_tab == 3:
        lines = [
            "Trackers Tab:",
            "a: Add Tracker   d: Delete Tracker   e: Edit Tracker",
            "l: Log Entry     v: View Tracker     g: Add/Edit Goal",
            "x: Delete Goal   V: View All Goals   h: Goal Help",
            "",
            "↑/↓: Move   ←/→: Switch Tab   ?: Help   Q: Quit"
        ]
    elif current_tab == 4:
        lines = [
            "Reports Tab:",
            "1: Trackers Summary    2: Time Summary    3: Daily Tracker",
            "4: Insights            C: Clinical Insights    B: Task Burndown",
            "",
            "←/→: Switch Tab   ?: Help   Q: Quit"
        ]
    else:
        lines = ["Q: Quit   ?: Close Help"]

    popup_show(stdscr, lines, title="Available Hotkeys")


def popup_error(stdscr, error, title=" Error "):
    """
    Show a centered popup window for errors (multi-line-safe).
    - `error`: Can be a string, Exception, or list of strings.
    - Always fits to the screen, with word-wrapped text.
    """
    h, w = stdscr.getmaxyx()
    # Accept Exception, str, or list
    if isinstance(error, Exception):
        lines = [str(error)]
    elif isinstance(error, str):
        lines = error.splitlines()
    elif isinstance(error, list):
        lines = []
        for item in error:
            lines.extend(str(item).splitlines())
    else:
        lines = [repr(error)]

    # Word wrap to fit the popup width (max 60 cols, but not wider than screen)
    win_w = min(60, w - 4)
    win_h = min(3 + len(lines)*2, h - 2)
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=win_w - 4) or [""])

    win_h = min(3 + len(wrapped), h - 2)
    starty = max((h - win_h) // 2, 0)
    startx = max((w - win_w) // 2, 0)

    win = curses.newwin(win_h, win_w, starty, startx)
    win.keypad(True)
    win.border()
    # Draw title
    if win_w - len(title) > 4:
        win.addstr(0, (win_w - len(title)) // 2, title, curses.A_BOLD)
    # Print error lines
    for idx, line in enumerate(wrapped[:win_h-3]):
        win.addstr(1 + idx, 2, line[:win_w-4],
                   curses.A_BOLD | curses.color_pair(0))
    # Prompt to close
    prompt = "<Press any key to close>"
    if win_h > 2:
        win.addstr(win_h-2, max((win_w - len(prompt)) // 2, 1),
                   prompt, curses.A_DIM)
    win.refresh()
    win.getch()
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()


def log_and_popup_error(stdscr, message, exc=None):
    """Unified error popup (TUI) and log to main log file (always)."""
    from lifelog.ui_views.popups import popup_error
    try:
        if stdscr:
            popup_error(stdscr, message)
    except Exception as popup_exc:
        print(f"Popup error: {popup_exc} -- {message}")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {message}\n")
            if exc:
                f.write(f"{exc}\n")
                f.write(traceback.format_exc())
            f.write("\n\n")
    except Exception as log_exc:
        print(f"LOGGING ERROR: {log_exc} -- {message}")


def user_friendly_empty_message(module="insights"):
    """Standardized no-data message."""
    return f"[yellow]No usable {module} data available yet. Please track more to generate valuable insights.[/yellow]"


def handle_no_data(stdscr=None, module="insights"):
    msg = user_friendly_empty_message(module)
    log_and_popup_error(stdscr, msg)
    return None


def try_or_log(fn, *args, stdscr=None, **kwargs):
    """Call fn(*args, **kwargs), logging errors and showing popup if fails."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log_and_popup_error(stdscr, f"Exception in {fn.__name__}", exc=e)
        return None


def popup_show(stdscr, lines, title=""):
    h, w = stdscr.getmaxyx()
    ph = len(lines) + 4
    pw = max(len(l) for l in lines + [title]) + 4
    y, x = (h - ph)//2, (w - pw)//2

    win = curses.newwin(ph, pw, y, x)
    curses.curs_set(0)
    win.border()
    if title:
        win.addstr(0, (pw - len(title))//2, title, curses.A_BOLD)
    for i, l in enumerate(lines, start=1):
        win.addstr(i, 2, l[:pw-4])
    win.addstr(ph-2, 2, "Press any key to close", curses.A_DIM)
    win.refresh()
    win.getch()
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()


def popup_input(stdscr, prompt, max_length=48):
    h, w = stdscr.getmaxyx()
    ph, pw = 5, max(len(prompt), 20) + 4
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    win.addstr(1, 2, prompt)
    win.addstr(2, 2, "> ")
    curses.echo()
    curses.curs_set(1)
    win.refresh()
    inp = []
    while True:
        if len(inp) >= max_length:
            win.addstr(3, 2, f"Max {max_length} chars!", curses.A_DIM)
            win.clrtoeol()
        c = win.getch(2, 4 + len(inp))
        if c in (10, 13):  # Enter
            break
        if c in (27,):     # ESC
            inp = []
            break
        if c in (curses.KEY_BACKSPACE, 127, 8):
            if inp:
                inp.pop()
                win.addstr(2, 4 + len(inp), ' ')
                win.move(2, 4 + len(inp))
        else:
            if 32 <= c <= 126:
                inp.append(chr(c))
                win.addstr(2, 4 + len(inp) - 1, chr(c))
    curses.noecho()
    curses.curs_set(0)
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()
    return "".join(inp).strip() if inp else None


def popup_multiline_input(stdscr, prompt, initial=""):
    """
    Let the user enter multiline text (like notes) in a popup.
    """
    from curses import ascii
    h, w = stdscr.getmaxyx()
    ph, pw = 10, 60
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    win.addstr(1, 2, prompt)
    win.addstr(2, 2, "Ctrl+D = finish, ESC = cancel")
    text = initial.splitlines() if initial else []
    y = 3
    for idx, line in enumerate(text):
        win.addstr(y+idx, 2, line[:pw-4])
    win.move(y+len(text), 2)
    curses.curs_set(1)
    lines = text[:]
    while True:
        c = win.getch()
        if c == 27:  # ESC
            curses.curs_set(0)
            return initial  # Cancel: keep old
        if c in (curses.ascii.EOT,):  # Ctrl+D to finish
            break
        elif c in (10, 13):  # Enter
            lines.append("")
            y += 1
        elif c in (curses.KEY_BACKSPACE, 127, 8):
            if lines and lines[-1]:
                lines[-1] = lines[-1][:-1]
            elif lines:
                lines.pop()
                y -= 1
        elif 32 <= c <= 126:
            if not lines:
                lines.append("")
            lines[-1] += chr(c)
        win.move(3+len(lines)-1, 2+len(lines[-1]) if lines else 2)
        for i in range(len(lines)):
            win.addstr(3+i, 2, " "*(pw-4))  # Clear line
            win.addstr(3+i, 2, lines[i][:pw-4])
        win.refresh()
    curses.curs_set(0)
    return "\n".join(lines)


def popup_select_option(stdscr, prompt, options, allow_new=False):
    lines = [f"{i+1}: {opt}" for i, opt in enumerate(options)]
    if allow_new:
        lines.append(f"{len(options)+1}: [Add New]")
    popup_show(stdscr, [prompt, ""] + lines)
    choice = popup_input(stdscr, "Choose number: ", max_length=3)
    if choice and choice.isdigit() and 1 <= int(choice) <= len(options):
        return options[int(choice)-1]
    elif allow_new and choice == str(len(options)+1):
        new_val = popup_input(stdscr, "Enter new value:")
        return new_val
    return None


def popup_confirm(stdscr, message) -> bool:
    h, w = stdscr.getmaxyx()
    ph, pw = 5, len(message)+10
    win = curses.newwin(ph, pw, (h-ph)//2, (w-pw)//2)
    win.border()
    win.addstr(1, 2, message)
    win.addstr(3, 2, "[y] Yes    [n] No")
    win.refresh()
    while True:
        c = win.getch()
        if c in (ord("y"), ord("Y")):
            return True
        if c in (ord("n"), ord("N"), 27):
            return False
