# lifelog/ui_helpers.py
from datetime import datetime
import traceback
import curses

from lifelog.ui_views.popups import popup_input, popup_show

# -------------------------------------------------------------------
# Helper: draw the top menu tabs
# -------------------------------------------------------------------
# ─── Single, contextual status‐bar ───────────────────────────────────


def draw_status(stdscr, h, w, current_tab):
    status_y = h - 1
    stdscr.attron(curses.color_pair(3))
    stdscr.hline(status_y, 0, " ", w)
    # Minimal hints, 1 line, with '?' for more help
    if current_tab == 0:  # Home
        hint = "←/→: Switch  ↑/↓: Move"
    elif current_tab == 1:  # Tasks
        hint = "a:Add  e:Edit  v:View  s:Start  p:Stop  o:Done  f:Filter F:Focus  ?:Help  Q:Quit"
    elif current_tab == 2:  # Time
        hint = "s:Start  a:Manual  p:Stop  y:Sum  w:Watch  ?:Help  Q:Quit"
    elif current_tab == 3:  # Trackers
        hint = "a:Add  l:Log  g:Goal  v:View  x:Del  ?:Help  Q:Quit"
    elif current_tab == 4:  # Reports
        hint = "1-4:Run Report C:Insights B:Burndown  ?:Help  Q:Quit"
    else:
        hint = "←/→: Switch  ↑/↓: Move Q:Quit  ?:Help"
    stdscr.addstr(status_y, 1, hint[: w - 2])
    stdscr.attroff(curses.color_pair(3))


def draw_menu(stdscr, tabs, current, w, color_pair=0):
    stdscr.attron(curses.color_pair(color_pair))
    stdscr.hline(2, 0, ' ', w)
    stdscr.attroff(curses.color_pair(color_pair))
    x = 2
    for idx, name in enumerate(tabs):
        attr = curses.A_REVERSE if idx == current else curses.A_NORMAL
        stdscr.addstr(1, x, f" {name} ", attr)
        x += len(name)+4


def create_pane(stdscr, menu_h, h, w, title, x=0, color_pair=0):
    """Make a bordered pane under the menu, above the status line."""
    body_h = h - menu_h - 1
    win = curses.newwin(body_h, w, menu_h, x)
    if color_pair:
        win.attron(curses.color_pair(color_pair))
    win.border()
    if color_pair:
        win.attroff(curses.color_pair(color_pair))
    # title centered
    win.addstr(0, (w - len(title))//2, title, curses.A_BOLD)
    return win


def tag_picker_tui(stdscr, existing_tags):
    """
    UI helper to pick from existing tags or enter new ones.
    """
    selected = []
    while True:
        tag_menu = [f"[{i}] {tag}" for i, tag in enumerate(existing_tags)]
        tag_menu.append("[+] Add new tag")
        tag_menu.append("[Done] Finish selection")
        popup_show(stdscr, tag_menu, title="Select Tags")
        idx = popup_input(stdscr, "Choose tag number, + for new, or done:")
        if idx == "done":
            break
        if idx == "+" or idx == str(len(existing_tags)):
            new_tag = popup_input(stdscr, "New tag name:")
            if new_tag and new_tag not in existing_tags:
                existing_tags.append(new_tag)
                selected.append(new_tag)
        elif idx.isdigit() and int(idx) < len(existing_tags):
            selected.append(existing_tags[int(idx)])
    return ",".join(selected) if selected else None


def log_exception(context, exc):
    """Log any exception with traceback to the main log file."""
    try:
        with open("/tmp/lifelog_tui.log", "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {context}: {exc}\n")
            f.write(traceback.format_exc())
            f.write("\n\n")
    except Exception as e:
        # If logging itself fails, print to stderr (last resort)
        print(f"LOGGING ERROR in {context}: {e}")
