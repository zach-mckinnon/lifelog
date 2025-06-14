# lifelog/utils/db/gamification_seed.py

import uuid
from datetime import datetime, timezone
from lifelog.utils.db.db_helper import safe_query
from lifelog.utils.db.database_manager import add_record, update_record
from lifelog.utils.db.models import (
    Badge, Skill,
    get_badge_fields, get_skill_fields
)


def _badge_exists(uid: str) -> bool:
    rows = safe_query("SELECT 1 FROM badges WHERE uid = ?", (uid,))
    return bool(rows)


def _skill_exists(uid: str) -> bool:
    rows = safe_query("SELECT 1 FROM skills WHERE uid = ?", (uid,))
    return bool(rows)


def seed_badges() -> None:
    """
    Upsert 50 badges spanning:
     - Task completion counts
     - Pomodoro counts
     - Daily streaks
     - XP milestones
     - Gold milestones
    """
    now = datetime.now(timezone.utc).isoformat()
    badges = []

    # 1) Task completed badges
    task_counts = [1, 5, 10, 20, 50, 100, 200]
    for n in task_counts:
        badges.append({
            "uid": f"tasks_{n}",
            "name": f"{n} Task{'s' if n>1 else ''} Done",
            "description": f"Complete {n} tasks in total",
            "icon": "✅",
        })

    # 2) Pomodoro badges
    pom_counts = [1, 5, 10, 25, 50, 100]
    for n in pom_counts:
        badges.append({
            "uid": f"pomodoros_{n}",
            "name": f"{n} Pomodoro{'s' if n>1 else ''}",
            "description": f"Finish {n} pomodoro sessions",
            "icon": "⏲️",
        })

    # 3) Streak badges
    streaks = [2, 3, 5, 7, 14, 21, 30]
    for n in streaks:
        badges.append({
            "uid": f"streak_{n}",
            "name": f"{n}-Day Streak",
            "description": f"Complete at least one task for {n} days in a row",
            "icon": "🔥",
        })

    # 4) XP milestone badges
    xp_milestones = [100, 500, 1000, 2000, 5000]
    for xp in xp_milestones:
        badges.append({
            "uid": f"xp_{xp}",
            "name": f"{xp} XP Earned",
            "description": f"Accumulate {xp} experience points",
            "icon": "⭐",
        })

    # 5) Gold milestone badges
    gold_milestones = [50, 100, 250, 500]
    for g in gold_milestones:
        badges.append({
            "uid": f"gold_{g}",
            "name": f"{g} Gold Hoarded",
            "description": f"Collect {g} gold pieces",
            "icon": "💰",
        })

    # Trim to 50 if necessary
    badges = badges[:50]

    for b in badges:
        if not _badge_exists(b["uid"]):
            data = {
                "uid": b["uid"],
                "name": b["name"],
                "description": b["description"],
                "icon": b["icon"],
                "created_at": now
            }
            add_record("badges", data, get_badge_fields())
            print(f"Seeded badge: {b['uid']}")


def seed_skills() -> None:
    """
    Upsert a set of Adventurer‐themed skills:
     - Focus Wizardry
     - Time Alchemy
     - Tracker Tactics
     - Mind Mastery
     - Stamina Endurance
    """
    now = datetime.now(timezone.utc).isoformat()
    skills = [
        {
            "uid": "focus_wizardry",
            "name": "Focus Wizardry",
            "description": "Increase XP gain from Pomodoros by 1% per level",
        },
        {
            "uid": "time_alchemy",
            "name": "Time Alchemy",
            "description": "Reduce late‐task XP penalty and extend session length",
        },
        {
            "uid": "tracker_tactics",
            "name": "Tracker Tactics",
            "description": "Boost XP for tracker entries and goal completions",
        },
        {
            "uid": "mind_mastery",
            "name": "Mind Mastery",
            "description": "Unlock advanced insights and double‐XP events",
        },
        {
            "uid": "stamina_endurance",
            "name": "Stamina Endurance",
            "description": "Shorten break time by 1 minute per level",
        },
    ]

    for s in skills:
        if not _skill_exists(s["uid"]):
            data = {
                "uid": s["uid"],
                "name": s["name"],
                "description": s["description"],
                "created_at": now
            }
            add_record("skills", data, get_skill_fields())
            print(f"Seeded skill: {s['uid']}")


def run_seed():
    print("Seeding badges and skills…")
    seed_badges()
    seed_skills()
    print("Seeding complete.")


if __name__ == "__main__":
    run_seed()
