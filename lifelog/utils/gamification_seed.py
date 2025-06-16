# lifelog/utils/db/gamification_seed.py

import uuid
from datetime import datetime, timezone

from lifelog.utils.db import safe_query, add_record
from lifelog.utils.db.models import Badge, Skill, get_badge_fields, get_skill_fields


def _badge_exists(uid: str) -> bool:
    return bool(safe_query("SELECT 1 FROM badges WHERE uid = ?", (uid,)))


def _skill_exists(uid: str) -> bool:
    return bool(safe_query("SELECT 1 FROM skills WHERE uid = ?", (uid,)))


def seed_badges() -> None:
    """
    Upsert all badges your gamification needs:
      • First-time events
      • Level milestones
      • Task/Pomodoro/Streak/Xp/Gold milestones
    """
    badges = []

    # 1) First-time badges
    badges += [
        {"uid": "first_task_on_time",  "name": "First On-Time Task",
            "description": "Complete your first task on time",     "icon": "⏱️"},
        {"uid": "first_pomodoro",      "name": "First Pomodoro",
            "description": "Finish your first Pomodoro session",      "icon": "⏲️"},
        {"uid": "first_tracker_log",   "name": "First Tracker Log",
            "description": "Log your first tracker entry",           "icon": "📊"},
    ]

    # 2) Level badges (1–10)
    for lvl in range(1, 11):
        badges.append({
            "uid": f"level_{lvl}",
            "name": f"Reach Level {lvl}",
            "description": f"Achieve level {lvl}",
            "icon": "🚀",
        })

    # 3) Task completion counts
    for n in [1, 5, 10, 20, 50, 100]:
        badges.append({
            "uid": f"tasks_{n}",
            "name": f"{n} Task{'s' if n>1 else ''} Done",
            "description": f"Complete {n} tasks in total",
            "icon": "✅",
        })

    # 4) Pomodoro counts
    for n in [1, 5, 10, 25, 50]:
        badges.append({
            "uid": f"pomodoros_{n}",
            "name": f"{n} Pomodoro{'s' if n>1 else ''}",
            "description": f"Finish {n} Pomodoro sessions",
            "icon": "⏲️",
        })

    # 5) Streak badges
    for n in [2, 3, 5, 7, 14, 21, 30]:
        badges.append({
            "uid": f"streak_{n}",
            "name": f"{n}-Day Streak",
            "description": f"Complete at least one task for {n} days straight",
            "icon": "🔥",
        })

    # 6) XP milestones
    for xp in [100, 500, 1000, 2000]:
        badges.append({
            "uid": f"xp_{xp}",
            "name": f"{xp} XP Earned",
            "description": f"Accumulate {xp} experience points",
            "icon": "⭐",
        })

    # 7) Gold milestones
    for g in [50, 100, 250, 500]:
        badges.append({
            "uid": f"gold_{g}",
            "name": f"{g} Gold Hoarded",
            "description": f"Collect {g} gold pieces",
            "icon": "💰",
        })

    # Insert any that don’t already exist, validating with the Badge dataclass
    for b in badges:
        if not _badge_exists(b["uid"]):
            badge_obj = Badge(**b)
            data = badge_obj.asdict()
            add_record("badges", data, get_badge_fields())
            print(f"Seeded badge: {badge_obj.uid}")


def seed_skills() -> None:
    """
    Upsert all skills your gamification needs:
      • task_mastery, focus_mastery, tracker_mastery
      • plus any “adventurer” skills you’ve defined
    """
    skills = [
        {"uid": "task_mastery",    "name": "Task Mastery",
            "description": "Gain XP faster for tasks"},
        {"uid": "focus_mastery",   "name": "Focus Mastery",
            "description": "Gain XP faster for Pomodoros"},
        {"uid": "tracker_mastery", "name": "Tracker Mastery",
            "description": "Gain XP faster for track logs"},
        # your existing five:
        {"uid": "focus_wizardry",     "name": "Focus Wizardry",
            "description": "Increase XP gain from Pomodoros"},
        {"uid": "time_alchemy",       "name": "Time Alchemy",
            "description": "Reduce late-task penalty & extend session"},
        {"uid": "tracker_tactics",    "name": "Tracker Tactics",
            "description": "Boost XP for tracker entries"},
        {"uid": "mind_mastery",       "name": "Mind Mastery",
            "description": "Occasional double-XP events"},
        {"uid": "stamina_endurance",  "name": "Stamina Endurance",
            "description": "Shorten your breaks"},
    ]

    # Insert any that don’t already exist, validating with the Skill dataclass
    for s in skills:
        if not _skill_exists(s["uid"]):
            skill_obj = Skill(**s)
            data = skill_obj.asdict()
            add_record("skills", data, get_skill_fields())
            print(f"Seeded skill: {skill_obj.uid}")


def run_seed():
    print("Seeding badges…")
    seed_badges()
    print("Seeding skills…")
    seed_skills()
    print("Seeding complete.")


if __name__ == "__main__":
    run_seed()
