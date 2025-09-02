# lifelog/ui_views/hero_ui.py

import curses
from lifelog.ui_views.popups import popup_show, popup_confirm
from lifelog.utils.db.gamify_repository import (
    _ensure_profile,
    list_badges,
    list_skills,
    list_shop_items,
    buy_item,
)
from lifelog.utils.get_quotes import get_feedback_saying


def hero_menu(stdscr):
    """
    Curses‐based menu to inspect your Hero profile.
    """
    options = [
        ("Profile", show_profile_ui),
        ("Badges", show_badges_ui),
        ("Skills", show_skills_ui),
        ("Shop", show_shop_ui),
        ("Buy Item", buy_item_ui),
        ("Exit", lambda s: None),
    ]
    while True:
        choices = [f"{i+1}. {o[0]}" for i, o in enumerate(options)]
        sel = popup_show(stdscr, choices, title="🛡️ Hero Menu", wait=False)
        key = stdscr.getch()
        idx = key - ord('1')
        if 0 <= idx < len(options):
            if options[idx][0] == "Exit":
                break
            options[idx][1](stdscr)
        else:
            continue


def show_profile_ui(stdscr):
    p = _ensure_profile()
    lines = [
        f"Level: {p.level}",
        f"XP: {p.xp}/100",
        f"Gold: {p.gold}"
    ]
    popup_show(stdscr, lines, title="🦸‍♂️ Profile")


def show_badges_ui(stdscr):
    p = _ensure_profile()
    rows = []
    for b in list_badges():
        unlocked = any(
            pb["badge_id"] == b.id
            for pb in __import__("lifelog.utils.db.db_helper", fromlist=["safe_query"])
            .safe_query(
                "SELECT badge_id FROM profile_badges WHERE profile_id=?",
                (p.id,)
            )
        )
        mark = "✔" if unlocked else "✗"
        rows.append(f"[{mark}] {b.name}: {b.description}")
    popup_show(stdscr, rows, title="🏅 Badges")


def show_skills_ui(stdscr):
    rows = []
    for sk in list_skills():
        lvl = __import__("lifelog.utils.db.db_helper", fromlist=["safe_query"]) \
            .safe_query(
            "SELECT level FROM profile_skills ps JOIN skills s ON ps.skill_id=s.id "
            "WHERE ps.profile_id=? AND s.uid=?",
            (_ensure_profile().id, sk.uid)
        )
        level = lvl[0]["level"] if lvl else 0
        rows.append(f"{sk.name} (Lvl {level}): {sk.description}")
    popup_show(stdscr, rows, title="⚔️ Skills")


def show_shop_ui(stdscr):
    rows = [f"{item.uid}: {item.name} — {item.cost_gold} gold"
            for item in list_shop_items()]
    popup_show(stdscr, rows, title="🏪 Shop")


def buy_item_ui(stdscr):
    uid = popup_confirm(stdscr, "Enter UID to buy:", default=False)
    # actually popup_input would be better here; using popup_input:
    from lifelog.ui_views.popups import popup_input
    choice = popup_input(stdscr, "Shop UID:", default="")
    if not choice:
        return
    try:
        inv = buy_item(choice)
        popup_show(
            stdscr, [f"Bought one {choice}! Now have {inv.quantity}."], title="✅ Purchase")
    except Exception as e:
        popup_show(stdscr, [str(e)], title="❌ Error")
