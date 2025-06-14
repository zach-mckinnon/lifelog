# lifelog/utils/db/gamification_repository.py

import uuid
from datetime import datetime, timezone
from typing import List, Tuple
from rich.console import Console
from lifelog.utils.db.db_helper import normalize_for_db, safe_query, safe_execute
from lifelog.utils.db.database_manager import add_record, update_record
from lifelog.utils.db.models import (
    UserProfile, Badge, ProfileBadge,
    Skill, ProfileSkill, ShopItem, InventoryItem,
    get_profile_fields, get_badge_fields, get_profile_badge_fields,
    get_skill_fields, get_profile_skill_fields,
    get_shop_item_fields, get_inventory_fields
)
console = Console()

# — Ensure a single UserProfile exists


def _ensure_profile() -> UserProfile:
    rows = safe_query("SELECT * FROM user_profiles LIMIT 1", ())
    if rows:
        return UserProfile(**dict(rows[0]))
    data = {
        "uid": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    new_id = add_record("user_profiles", normalize_for_db(
        data), get_profile_fields())
    row = safe_query("SELECT * FROM user_profiles WHERE id = ?", (new_id,))[0]
    return UserProfile(**dict(row))


# — Award XP (and handle level-up)


def add_xp(amount: int) -> UserProfile:
    profile = _ensure_profile()
    total_xp = profile.xp + amount
    # simple threshold: 100 XP per level
    level_gain, rem = divmod(total_xp, 100)
    new_level = profile.level + level_gain
    updates = {
        "xp": rem,
        "level": new_level,
        "last_level_up": datetime.now(timezone.utc).isoformat() if level_gain else profile.last_level_up
    }
    update_record("user_profiles", profile.id, normalize_for_db(updates))
    row = safe_query(
        "SELECT * FROM user_profiles WHERE id = ?", (profile.id,))[0]
    return UserProfile(**dict(row))

# — Fetch all badges


def list_badges() -> List[Badge]:
    rows = safe_query("SELECT * FROM badges", ())
    return [Badge(**dict(r)) for r in rows]

# — Award a badge once


def award_badge(badge_uid: str) -> None:
    profile = _ensure_profile()
    badge_rows = safe_query("SELECT * FROM badges WHERE uid = ?", (badge_uid,))
    if not badge_rows:
        raise ValueError(f"No badge '{badge_uid}'")
    badge = dict(badge_rows[0])
    # idempotent insert
    data = {
        "profile_id": profile.id,
        "badge_id": badge["id"],
        "awarded_at": datetime.now(timezone.utc).isoformat()
    }
    add_record("profile_badges", normalize_for_db(
        data), get_profile_badge_fields())

# — Fetch all skills


def list_skills() -> List[Skill]:
    rows = safe_query("SELECT * FROM skills", ())
    return [Skill(**dict(r)) for r in rows]

# — Allocate XP into a skill


def add_skill_xp(skill_uid: str, amount: int) -> ProfileSkill:
    profile = _ensure_profile()
    sk_rows = safe_query("SELECT * FROM skills WHERE uid = ?", (skill_uid,))
    if not sk_rows:
        raise ValueError(f"No skill '{skill_uid}'")
    skill = dict(sk_rows[0])
    # fetch or create profile_skill
    ps_rows = safe_query(
        "SELECT * FROM profile_skills WHERE profile_id = ? AND skill_id = ?",
        (profile.id, skill["id"])
    )
    if ps_rows:
        ps = ProfileSkill(**dict(ps_rows[0]))
        new_xp = ps.xp + amount
        lvl_gain, rem = divmod(new_xp, 100)
        new_lvl = ps.level + lvl_gain
        updates = {"xp": rem, "level": new_lvl}
        update_record(
            "profile_skills", (profile.id,
                               skill["id"]), normalize_for_db(updates)
        )
    else:
        data = {
            "profile_id": profile.id,
            "skill_id": skill["id"],
            "xp": amount,
            "level": 1
        }
        add_record("profile_skills", normalize_for_db(
            data), get_profile_skill_fields())
    pr = safe_query(
        "SELECT * FROM profile_skills WHERE profile_id = ? AND skill_id = ?",
        (profile.id, skill["id"])
    )[0]
    return ProfileSkill(**dict(pr))

# — Shop browsing & purchase


def list_shop_items() -> List[ShopItem]:
    rows = safe_query("SELECT * FROM shop_items", ())
    return [ShopItem(**dict(r)) for r in rows]


def create_shop_item(uid: str, name: str, desc: str, cost: int) -> ShopItem:
    data = {"uid": uid, "name": name, "description": desc, "cost_gold": cost}
    add_record("shop_items", data, get_shop_item_fields())
    row = safe_query("SELECT * FROM shop_items WHERE uid = ?", (uid,))[0]
    return ShopItem(**dict(row))


def buy_item(item_uid: str) -> InventoryItem:
    profile = _ensure_profile()
    item_rows = safe_query(
        "SELECT * FROM shop_items WHERE uid = ?", (item_uid,))
    if not item_rows:
        raise ValueError(f"No shop item '{item_uid}'")
    item = dict(item_rows[0])
    # check gold
    if profile.gold < item["cost_gold"]:
        raise RuntimeError("Not enough gold")
    # deduct gold
    update_record("user_profiles", profile.id, normalize_for_db({
        "gold": profile.gold - item["cost_gold"]
    }))
    # add to inventory
    inv = safe_query(
        "SELECT * FROM inventory WHERE profile_id = ? AND item_id = ?",
        (profile.id, item["id"])
    )
    if inv:
        qty = inv[0]["quantity"] + 1
        update_record("inventory", (profile.id, item["id"]), {"quantity": qty})
    else:
        data = {
            "profile_id": profile.id,
            "item_id": item["id"],
            "quantity": 1
        }
        add_record("inventory", data, get_inventory_fields())
    row = safe_query(
        "SELECT * FROM inventory WHERE profile_id = ? AND item_id = ?",
        (profile.id, item["id"])
    )[0]
    return InventoryItem(**dict(row))


def get_skill_level(skill_uid: str) -> int:
    """
    Return the user’s current level in a given skill (0 if unallocated).
    """
    profile = _ensure_profile()
    rows = safe_query("""
        SELECT ps.level
          FROM profile_skills ps
          JOIN skills s ON s.id = ps.skill_id
         WHERE ps.profile_id = ? AND s.uid = ?
    """, (profile.id, skill_uid))
    return rows[0]["level"] if rows else 0


def apply_xp_bonus(base_xp: int, context: str) -> int:
    """
    Apply skill-based modifiers to a base XP award.
    context: 'pomodoro', 'task', 'tracker'
    """
    xp = base_xp

    # Focus Wizardry: +1% XP per skill level on Pomodoro XP
    if context == "pomodoro":
        lvl = get_skill_level("focus_wizardry")
        xp = xp + (xp * lvl) // 100

    # Tracker Tactics: +2% XP per level on tracker logs
    if context == "tracker":
        lvl = get_skill_level("tracker_tactics")
        xp = xp + (xp * 2 * lvl) // 100

    # Time Alchemy: reduce late‐task penalty: +1% of base XP per level
    if context == "task_late":
        lvl = get_skill_level("time_alchemy")
        xp = base_xp + (base_xp * lvl) // 100

    return xp


def modify_pomodoro_lengths(focus: int, brk: int) -> Tuple[int, int]:
    """
    Return (new_focus, new_break) adjusted by:
      - Time Alchemy: +1 minute focus per level
      - Stamina Endurance: -1 minute break per level
    """
    t_lvl = get_skill_level("time_alchemy")
    s_lvl = get_skill_level("stamina_endurance")

    new_focus = focus + t_lvl
    new_break = max(1, brk - s_lvl)  # never zero
    return new_focus, new_break


def _ensure_profile() -> UserProfile:
    rows = safe_query("SELECT * FROM user_profiles LIMIT 1", ())
    if rows:
        return UserProfile(**dict(rows[0]))
    data = {
        "uid": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    new_id = add_record("user_profiles", normalize_for_db(
        data), get_profile_fields())
    row = safe_query("SELECT * FROM user_profiles WHERE id = ?", (new_id,))[0]
    return UserProfile(**dict(row))


def add_xp(amount: int) -> UserProfile:
    profile = _ensure_profile()
    old_level = profile.level

    total_xp = profile.xp + amount
    level_gain, rem = divmod(total_xp, 100)
    new_level = profile.level + level_gain

    updates = {
        "xp": rem,
        "level": new_level,
        "last_level_up": datetime.now(timezone.utc).isoformat() if level_gain else profile.last_level_up
    }
    update_record("user_profiles", profile.id, normalize_for_db(updates))
    row = safe_query(
        "SELECT * FROM user_profiles WHERE id = ?", (profile.id,))[0]
    updated = UserProfile(**dict(row))

    # 1) Level-up notification
    if updated.level > old_level:
        console.print(
            f":tada: [bold green]Congratulations! You've reached level {updated.level}![/bold green]")

    # 2) Check for any new level badges
    _award_level_badges(old_level, updated.level)

    return updated


def _award_level_badges(old_level: int, new_level: int):
    """
    For each level L in (old_level, new_level], if a badge with uid="level_L" exists
    and the user has not yet been awarded it, award it and notify.
    """
    console = Console()
    # load badges with uids like level_1, etc.
    all_badges = safe_query(
        "SELECT id, uid, name FROM badges WHERE uid LIKE 'level_%'", ())
    for b in all_badges:
        # parse the numeric part
        try:
            badge_level = int(b["uid"].split("_", 1)[1])
        except Exception:
            continue
        if old_level < badge_level <= new_level:
            # check if already awarded
            exist = safe_query(
                "SELECT 1 FROM profile_badges WHERE badge_id = ?",
                (b["id"],)
            )
            if not exist:
                # award it
                data = {
                    "profile_id": _ensure_profile().id,
                    "badge_id": b["id"],
                    "awarded_at": datetime.now(timezone.utc).isoformat()
                }
                add_record("profile_badges", normalize_for_db(
                    data), get_profile_badge_fields())
                console.print(
                    f":medal: [bold yellow]New badge earned:[/] {b['name']}")


def add_notification(profile_id: int, message: str) -> None:
    """Enqueue a new notification for the user."""
    safe_execute(
        "INSERT INTO notifications (profile_id, message, created_at) VALUES (?, ?, ?)",
        (profile_id, message, datetime.utcnow().isoformat())
    )


def get_unread_notifications(profile_id: int) -> list[dict]:
    """Return all unread notifications for a profile."""
    rows = safe_query(
        "SELECT id, message, created_at FROM notifications WHERE profile_id=? AND read=0 ORDER BY created_at",
        (profile_id,)
    )
    return [dict(r) for r in rows]


def mark_notifications_read(ids: list[int]) -> None:
    """Mark the given notification IDs as read."""
    for nid in ids:
        safe_execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))
