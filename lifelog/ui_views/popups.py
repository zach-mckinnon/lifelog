# ─── Popups & Helpers ─────────────────────────────────────────────────

from datetime import datetime
import textwrap
import curses
import traceback
from lifelog.utils.shared_utils import now_utc
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


def popup_error(stdscr, error, title=" Error! "):
    import curses
    import textwrap
    h, w = stdscr.getmaxyx()
    # Try to use color pair 2 for errors (red on black or white)
    try:
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        color = curses.color_pair(2) | curses.A_BOLD
    except Exception:
        color = curses.A_BOLD

    # Parse error message (friendly for non-tech)
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

    win_w = min(60, w - 4)
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=win_w - 4) or [""])

    win_h = min(5 + len(wrapped), h - 2)
    starty = max((h - win_h) // 2, 0)
    startx = max((w - win_w) // 2, 0)

    win = curses.newwin(win_h, win_w, starty, startx)
    win.border()
    # Draw high-contrast error title
    if win_w - len(title) > 4:
        win.addstr(0, (win_w - len(title)) // 2, title, color)
    # Friendly intro
    intro = "Whoops! Something went wrong:"
    win.addstr(1, 2, intro, color)
    # Error details
    for idx, line in enumerate(wrapped[:win_h-4]):
        win.addstr(2 + idx, 2, line[:win_w-4], color)
    prompt = "Press any key to close"
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
            f.write(f"[{now_utc()}] {message}\n")
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
    # Set max width and height based on terminal
    # Never overflow screen, max 80 cols for readability
    max_pw = min(w - 4, 80)
    # 5 = room for border/title/prompt, but not taller than screen
    ph = min(len(lines) + 5, h - 2)
    pw = max([len(line)
             for line in lines + [title, "Press any key to close"]]) + 4
    pw = min(max_pw, pw)
    y, x = max((h - ph) // 2, 0), max((w - pw) // 2, 0)
    win = curses.newwin(ph, pw, y, x)
    curses.curs_set(0)
    win.border()
    if title:
        win.addstr(0, max((pw - len(title)) // 2, 1), title, curses.A_BOLD)
    for i, l in enumerate(lines[:ph-3], start=1):  # leave space for border/prompt
        win.addstr(i, 2, l[:pw-4])
    prompt = "Press any key to close"
    win.addstr(ph-2, max((pw - len(prompt)) // 2, 1), prompt, curses.A_DIM)
    win.refresh()
    win.getch()
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()


def popup_input(stdscr, prompt, max_length=48, required=False, default=None):
    h, w = stdscr.getmaxyx()
    pw = min(max(len(prompt) + 10, 32), w - 4)
    ph = 7
    y, x = max((h - ph) // 2, 0), max((w - pw) // 2, 0)
    win = curses.newwin(ph, pw, y, x)
    win.border()
    win.addstr(1, 2, prompt[:pw-4])
    if default:
        win.addstr(2, 2, f"Default: {default}", curses.A_DIM)
    win.addstr(3, 2, "> ")
    curses.echo()
    curses.curs_set(1)
    inp = list(default) if default else []
    err = ""
    while True:
        win.move(3, 4 + len(inp))
        win.clrtoeol()
        win.addstr(3, 4, "".join(inp)[:pw-8])
        if err:
            win.addstr(4, 2, err[:pw-4], curses.A_BOLD | curses.color_pair(1))
        win.refresh()
        c = win.getch()
        if c in (10, 13):  # Enter
            val = "".join(inp).strip()
            if required and not val:
                err = "Required!"
                continue
            break
        if c in (27,):     # ESC
            inp = []
            break
        if c in (curses.KEY_BACKSPACE, 127, 8):
            if inp:
                inp.pop()
        elif len(inp) < max_length and 32 <= c <= 126:
            inp.append(chr(c))
        err = ""
    curses.noecho()
    curses.curs_set(0)
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()
    val = "".join(inp).strip() or default
    return val if val else None


def popup_multiline_input(stdscr, prompt, initial="", max_lines=10):
    from curses import ascii
    h, w = stdscr.getmaxyx()
    ph = min(h - 2, max_lines + 5)  # prompt, instructions, border
    pw = min(w - 4, 80)
    y, x = max((h - ph) // 2, 0), max((w - pw) // 2, 0)
    win = curses.newwin(ph, pw, y, x)
    win.border()
    win.addstr(1, 2, prompt[:pw-4])
    win.addstr(2, 2, "Ctrl+D = save, ESC = cancel")
    lines = initial.splitlines() if initial else [""]
    curr = len(lines) - 1
    curses.curs_set(1)
    while True:
        # Display as many lines as fit
        for i in range(max_lines):
            lidx = curr - (max_lines-1) + i
            win.move(3+i, 2)
            win.clrtoeol()
            win.addstr(3+i, 2, (lines[lidx] if 0 <=
                       lidx < len(lines) else "")[:pw-4])
        win.move(3 + (max_lines-1), 2 + len(lines[curr]) if lines else 2)
        win.refresh()
        c = win.getch()
        if c == 27:  # ESC
            curses.curs_set(0)
            win.clear()
            stdscr.touchwin()
            stdscr.refresh()
            return initial  # Cancel: keep old
        if c in (ascii.EOT,):  # Ctrl+D to finish
            break
        elif c in (10, 13):  # Enter: add new line
            lines.append("")
            curr += 1
        elif c in (curses.KEY_BACKSPACE, 127, 8):
            if lines[curr]:
                lines[curr] = lines[curr][:-1]
            elif curr > 0:
                lines.pop(curr)
                curr -= 1
        elif c == curses.KEY_UP and curr > 0:
            curr -= 1
        elif c == curses.KEY_DOWN and curr < len(lines) - 1:
            curr += 1
        elif 32 <= c <= 126:
            lines[curr] += chr(c)
    curses.curs_set(0)
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()
    return "\n".join(lines)


def popup_select_option(stdscr, prompt, options, allow_new=False):
    h, w = stdscr.getmaxyx()
    all_options = options + (["[Add New]"] if allow_new else [])
    opt_lines = [f"{i+1}: {opt}" for i, opt in enumerate(all_options)]
    ph = len(opt_lines) + 5
    pw = min(max(len(prompt) + 4, max(len(ol) for ol in opt_lines) + 4), w - 4)
    y, x = max((h - ph) // 2, 0), max((w - pw) // 2, 0)
    win = curses.newwin(ph, pw, y, x)
    win.border()
    win.addstr(1, 2, prompt[:pw-4], curses.A_BOLD)
    for i, ol in enumerate(opt_lines):
        win.addstr(2+i, 2, ol[:pw-4])
    win.addstr(ph-2, 2, "Choose number (ESC=skip):", curses.A_DIM)
    win.refresh()
    curses.echo()
    curses.curs_set(1)
    choice = win.getstr(ph-2, 24, 4).decode("utf-8").strip()
    curses.noecho()
    curses.curs_set(0)
    win.clear()
    stdscr.touchwin()
    stdscr.refresh()
    if not choice:
        return None
    if choice.isdigit():
        idx = int(choice)-1
        if 0 <= idx < len(options):
            return options[idx]
        elif allow_new and idx == len(options):
            return popup_input(stdscr, "Enter new value:")
    return None


def popup_confirm(stdscr, message) -> bool:
    h, w = stdscr.getmaxyx()
    pw = min(max(len(message) + 12, 32), w - 4)
    ph = 7
    y, x = max((h - ph) // 2, 0), max((w - pw) // 2, 0)
    win = curses.newwin(ph, pw, y, x)
    win.border()
    win.addstr(2, 2, message[:pw-4], curses.A_BOLD)
    prompt = "[y] Yes    [n] No (ESC = Cancel)"
    win.addstr(4, max((pw - len(prompt)) // 2, 1), prompt, curses.A_DIM)
    win.refresh()
    while True:
        c = win.getch()
        if c in (ord("y"), ord("Y")):
            win.clear()
            stdscr.touchwin()
            stdscr.refresh()
            return True
        if c in (ord("n"), ord("N"), 27):
            win.clear()
            stdscr.touchwin()
            stdscr.refresh()
            return False
