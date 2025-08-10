# lifelog/utils/db/gamify_repository.py

import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from rich.console import Console

from lifelog.utils.db import (
    normalize_for_db,
    safe_query,
    safe_execute,
    add_record,
    update_record,
    get_connection,
)
from lifelog.utils.db.models import (
    UserProfile,
    Badge,
    Skill,
    ProfileSkill,
    ShopItem,
    InventoryItem,
    get_profile_fields,
    get_profile_badge_fields,
    get_profile_skill_fields,
    get_shop_item_fields,
    get_inventory_fields,
)

console = Console()


# ── Profile bootstrap ─────────────────────────────────────────────────────────


def _ensure_profile() -> UserProfile:
    """Fetch the single user profile, or create it if missing."""
    rows = safe_query("SELECT * FROM user_profiles LIMIT 1", ())
    if rows:
        return UserProfile(**dict(rows[0]))

    data = {
        "uid": str(uuid.uuid4()),
        "xp": 0,
        "level": 1,
        "gold": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_level_up": None
    }
    new_id = add_record(
        "user_profiles", normalize_for_db(data), get_profile_fields()
    )
    row = safe_query("SELECT * FROM user_profiles WHERE id = ?", (new_id,))[0]
    return UserProfile(**dict(row))


# ── XP & Leveling ─────────────────────────────────────────────────────────────

def add_xp(amount: int) -> UserProfile:
    """
    Add `amount` XP to the profile. Levels up every 100 XP.
    On level-up, prints a congrats message and awards any level_N badges.
    """
    profile = _ensure_profile()
    old_level = profile.level

    total = profile.xp + amount
    level_gain, rem = divmod(total, 100)
    new_level = profile.level + level_gain

    updates = {
        "xp": rem,
        "level": new_level,
        "last_level_up": (
            datetime.now(timezone.utc).isoformat()
            if level_gain else profile.last_level_up
        )
    }
    update_record("user_profiles", profile.id, normalize_for_db(updates))

    updated = UserProfile(**dict(
        safe_query("SELECT * FROM user_profiles WHERE id = ?",
                   (profile.id,))[0]
    ))

    # 1) Notify on level-up
    if updated.level > old_level:
        console.print(
            f":tada: [bold green]Congratulations! "
            f"You've reached level {updated.level}![/bold green]"
        )
        # 2) Award any level_N badges
        _award_level_badges(old_level, updated.level)

    return updated


def _award_level_badges(old_level: int, new_level: int) -> None:
    """
    For each badge with uid 'level_<N>' where old_level < N <= new_level,
    award it (if not already) and print a medal message.
    """
    all_b = safe_query(
        "SELECT id, uid, name FROM badges WHERE uid LIKE 'level_%'", ()
    )
    for b in all_b:
        try:
            lvl = int(b["uid"].split("_", 1)[1])
        except ValueError:
            continue
        if old_level < lvl <= new_level:
            exists = safe_query(
                "SELECT 1 FROM profile_badges WHERE badge_id = ?", (b["id"],)
            )
            if not exists:
                # award it
                data = {
                    "profile_id": _ensure_profile().id,
                    "badge_id":   b["id"],
                    "awarded_at": datetime.now(timezone.utc).isoformat()
                }
                add_record(
                    "profile_badges", normalize_for_db(data),
                    get_profile_badge_fields()
                )
                console.print(
                    f":medal: [bold yellow]New badge earned:[/] {b['name']}"
                )


# ── Badges & Skills ──────────────────────────────────────────────────────────

def list_badges() -> List[Badge]:
    rows = safe_query("SELECT * FROM badges", ())
    return [Badge(**dict(r)) for r in rows]


def award_badge(badge_uid: str) -> None:
    profile = _ensure_profile()
    br = safe_query("SELECT * FROM badges WHERE uid = ?", (badge_uid,))
    if not br:
        raise ValueError(f"No badge '{badge_uid}'")
    badge = dict(br[0])
    data = {
        "profile_id": profile.id,
        "badge_id":   badge["id"],
        "awarded_at": datetime.now(timezone.utc).isoformat()
    }
    add_record(
        "profile_badges", normalize_for_db(data),
        get_profile_badge_fields()
    )


def list_earned_badges() -> List[Tuple[Badge, datetime]]:
    """
    Returns all badges the user has earned, in the order they were awarded.
    Each element is a tuple of (Badge, awarded_at).
    """
    profile_id = _ensure_profile().id
    rows = safe_query(
        """
        SELECT
          b.id    AS badge_id,
          b.uid,
          b.name,
          b.description,
          b.icon,
          pb.awarded_at
        FROM badges b
        JOIN profile_badges pb
          ON b.id = pb.badge_id
        WHERE pb.profile_id = ?
        ORDER BY pb.awarded_at
        """,
        (profile_id,)
    )

    result: List[Tuple[Badge, datetime]] = []
    for r in rows:
        # build the Badge dataclass
        badge = Badge(
            id=r["badge_id"],
            uid=r["uid"],
            name=r["name"],
            description=r["description"],
            icon=r["icon"],
        )
        # parse the timestamp string into a datetime
        awarded_at = datetime.fromisoformat(r["awarded_at"])
        result.append((badge, awarded_at))

    return result


def list_skills() -> List[Skill]:
    rows = safe_query("SELECT * FROM skills", ())
    return [Skill(**dict(r)) for r in rows]


def get_skill_level(skill_uid: str) -> int:
    rows = safe_query(
        """
        SELECT ps.level
          FROM profile_skills ps
          JOIN skills s ON s.id = ps.skill_id
         WHERE ps.profile_id=? AND s.uid=?
        """,
        (_ensure_profile().id, skill_uid)
    )
    return rows[0]["level"] if rows else 0


def add_skill_xp(skill_uid: str, amount: int) -> ProfileSkill:
    profile = _ensure_profile()
    sr = safe_query("SELECT * FROM skills WHERE uid = ?", (skill_uid,))
    if not sr:
        raise ValueError(f"No skill '{skill_uid}'")
    skill = dict(sr[0])

    ps = safe_query(
        "SELECT * FROM profile_skills WHERE profile_id=? AND skill_id=?",
        (profile.id, skill["id"])
    )
    if ps:
        ps_obj = ProfileSkill(**dict(ps[0]))
        new_xp = ps_obj.xp + amount
        level_gain, rem = divmod(new_xp, 100)
        new_lvl = ps_obj.level + level_gain

        # Use direct SQL update for composite key table
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE profile_skills SET xp = ?, level = ? WHERE profile_id = ? AND skill_id = ?",
            (rem, new_lvl, profile.id, skill["id"])
        )
        conn.commit()
    else:
        data = {
            "profile_id": profile.id,
            "skill_id":   skill["id"],
            "xp":          amount,
            "level":       1
        }
        add_record(
            "profile_skills",
            normalize_for_db(data),
            get_profile_skill_fields()
        )

    row = safe_query(
        "SELECT * FROM profile_skills WHERE profile_id=? AND skill_id=?",
        (profile.id, skill["id"])
    )[0]
    return ProfileSkill(**dict(row))


# ── XP Modifiers & Pomodoro Adjust ───────────────────────────────────────────

def apply_xp_bonus(base_xp: int, context: str) -> int:
    """
    Returns adjusted XP:
      - 'pomodoro': +1% per level of focus_wizardry
      - 'tracker':  +2% per level of tracker_tactics
      - 'task_late':+1% per level of time_alchemy on base_xp
    """
    xp = base_xp
    if context == "pomodoro":
        lvl = get_skill_level("focus_wizardry")
        xp += (xp * lvl) // 100
    if context == "tracker":
        lvl = get_skill_level("tracker_tactics")
        xp += (xp * 2 * lvl) // 100
    if context == "task_late":
        lvl = get_skill_level("time_alchemy")
        xp = base_xp + (base_xp * lvl) // 100
    return xp


def modify_pomodoro_lengths(focus: int, brk: int) -> Tuple[int, int]:
    """
    Returns (focus+time_alchemy, max(1, brk–stamina_endurance)).
    """
    t_lvl = get_skill_level("time_alchemy")
    s_lvl = get_skill_level("stamina_endurance")
    return focus + t_lvl, max(1, brk - s_lvl)


# ── Shop & Inventory ─────────────────────────────────────────────────────────

def list_shop_items() -> List[ShopItem]:
    rows = safe_query("SELECT * FROM shop_items", ())
    return [ShopItem(**dict(r)) for r in rows]


def create_shop_item(uid: str, name: str, desc: str, cost: int) -> ShopItem:
    data = {"uid": uid, "name": name, "description": desc, "cost_gold": cost}
    add_record("shop_items", data, get_shop_item_fields())
    r = safe_query("SELECT * FROM shop_items WHERE uid = ?", (uid,))[0]
    return ShopItem(**dict(r))


def buy_item(item_uid: str) -> InventoryItem:
    profile = _ensure_profile()
    row = safe_query("SELECT * FROM shop_items WHERE uid = ?", (item_uid,))
    if not row:
        raise ValueError(f"No shop item '{item_uid}'")
    item = dict(row[0])
    if profile.gold < item["cost_gold"]:
        raise RuntimeError("Not enough gold")

    # deduct gold
    update_record(
        "user_profiles", profile.id,
        normalize_for_db({"gold": profile.gold - item["cost_gold"]})
    )
    inv = safe_query(
        "SELECT * FROM inventory WHERE profile_id=? AND item_id=?",
        (profile.id, item["id"])
    )
    if inv:
        qty = inv[0]["quantity"] + 1
        update_record("inventory", (profile.id, item["id"]), {"quantity": qty})
    else:
        add_record(
            "inventory",
            {"profile_id": profile.id, "item_id": item["id"], "quantity": 1},
            get_inventory_fields()
        )

    new = safe_query(
        "SELECT * FROM inventory WHERE profile_id=? AND item_id=?",
        (profile.id, item["id"])
    )[0]
    return InventoryItem(**dict(new))


# ── Notifications ────────────────────────────────────────────────────────────

def add_notification(profile_id: int, message: str) -> None:
    """Enqueue a new notification for the user."""
    safe_execute(
        "INSERT INTO notifications (profile_id, message, created_at) VALUES (?, ?, ?)",
        (profile_id, message, datetime.now().isoformat())
    )


def get_unread_notifications(profile_id: int) -> List[dict]:
    """Return all unread notifications, oldest first."""
    rows = safe_query(
        "SELECT id, message, created_at FROM notifications "
        "WHERE profile_id=? AND read=0 ORDER BY created_at",
        (profile_id,)
    )
    return [dict(r) for r in rows]


def mark_notifications_read(ids: List[int]) -> None:
    """Mark the given notification IDs as read."""
    for nid in ids:
        safe_execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))
