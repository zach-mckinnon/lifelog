from lifelog.utils.db.gamify_repository import add_xp, apply_xp_bonus
import os
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from lifelog.utils.db.db_helper import safe_query
from lifelog.utils.db.gamify_repository import _ensure_profile, add_notification, add_skill_xp, award_badge, get_skill_level

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".lifelog" / "hooks"
HOOKS_DIR = Path(os.getenv("LIFELOG_HOOKS_DIR", _DEFAULT_DIR))


def ensure_hooks_dir() -> Path:
    """
    Guarantee that the hooks directory exists (after resolving $LIFELOG_HOOKS_DIR).
    Returns the resolved path.
    """
    try:
        HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("Could not create hooks directory %s: %s", HOOKS_DIR, e)
    return HOOKS_DIR
# ---------------------------------------------------------------------------


def run_hooks(module: str, action: str, entity: Any) -> None:
    """Execute all hooks for a module+action combination"""
    if not HOOKS_DIR.exists():
        return

    hook_prefix = f"post-{module}-{action}"
    hooks = sorted([
        f for f in HOOKS_DIR.iterdir()
        if f.name.startswith(hook_prefix) and os.access(f, os.X_OK)
    ])

    if not hooks:
        return

    payload = build_payload(module, action, entity)
    json_payload = json.dumps(payload)

    for hook in hooks:
        try:
            process = subprocess.Popen(
                [str(hook)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            _, stderr = process.communicate(input=json_payload, timeout=30)

            if process.returncode != 0:
                logger.error(
                    f"Hook {hook.name} failed with code {process.returncode}: "
                    f"{stderr.strip() or 'No error message'}"
                )
            try:
                gamify(module, action, payload)
            except Exception:
                logger.exception("Gamification hook error")
        except Exception as e:
            logger.exception(f"Error executing hook {hook.name}: {str(e)}")


def build_payload(module: str, action: str, entity: Any) -> Dict[str, Any]:
    """Construct standardized hook payload"""
    return {
        "event": f"{module}_{action}",
        "module": module,
        "action": action,
        "timestamp": datetime.utc_now().isoformat() + "Z",
        "entity": entity_to_dict(entity),
        "context": {
            "user": os.getenv("USER", "unknown"),
            "app_version": "1.0.0"
        }
    }


def entity_to_dict(entity) -> Dict[str, Any]:
    """Convert entity to serializable dict"""
    if hasattr(entity, "__dict__"):
        return entity.to_dict()
    if hasattr(entity, "_asdict"):
        return entity.to_dict()
    if isinstance(entity, dict):
        return entity
    return {"raw": str(entity)}


def gamify(module: str, event: str, payload):
    """
    Master hook for all gamification events.
    Awards XP, skill XP, and badges; prints notifications along the way.
    """

    # 1) Determine base XP and context
    base_xp = 0
    context = None

    if module == "task" and event == "completed":
        on_time = (payload.finished <= payload.due)
        base_xp = 50 if on_time else 20
        context = "task_on_time" if on_time else "task_late"

    elif module == "task" and event == "pomodoro_done":
        base_xp = 10
        context = "pomodoro"

    elif module == "tracker" and event == "logged":
        base_xp = 5
        context = "tracker"

    else:
        # we don't award XP for other hooks
        return

    # 2) Double-XP if they have the "mind_mastery" skill
    mind_lvl = add_skill_xp("mind_mastery", 0).level  # just fetch level
    if context == "pomodoro" and mind_lvl > 0:
        base_xp *= 2
    profile = add_xp(base_xp)
    add_notification(profile.id,
                     f"You earned {base_xp} XP for {context.replace('_',' ')}!")
    # 4) Award skill XP for the relevant skill
    #    e.g. "task_mastery" for tasks, "focus_mastery" for pomodoros, "tracker_mastery" for trackers
    skill_map = {
        "task_on_time":      "task_mastery",
        "task_late":         "task_mastery",
        "pomodoro":          "focus_mastery",
        "tracker":           "tracker_mastery",
    }
    skill_uid = skill_map.get(context)
    if skill_uid:
        old_lvl = get_skill_level(skill_uid)
        new_skill = add_skill_xp(skill_uid, base_xp // 2)
        if new_skill.level > old_lvl:
            add_notification(profile.id,
                             f"Your '{new_skill.name}' skill just leveled up to {new_skill.level}!")
    # 5) Context-specific badges
    #    e.g. first on-time task, first pomodoro, first tracker
    user = _ensure_profile()

    def _has_badge(uid: str) -> bool:
        rows = safe_query(
            "SELECT 1 FROM profile_badges pb JOIN badges b ON pb.badge_id=b.id WHERE pb.profile_id=? AND b.uid=?",
            (user.id, uid)
        )
        return bool(rows)

    # first on-time task badge
    if context == "task_on_time" and not _has_badge("first_task_on_time"):
        award_badge("first_task_on_time")
        add_notification(
            profile.id, "🏅 You’ve earned the “First On-Time Task” badge!")

    # first pomodoro badge
    if context == "pomodoro":
        total_poms = safe_query(
            "SELECT COUNT(*) AS c FROM time_logs WHERE event='pomodoro_done'", ())[0]["c"]
        if total_poms == 1 and not _has_badge("first_pomodoro"):
            award_badge("first_pomodoro")

    # first tracker badge
    if context == "tracker":
        total_logs = safe_query(
            "SELECT COUNT(*) AS c FROM tracker_entries", ())[0]["c"]
        if total_logs == 1 and not _has_badge("first_tracker_log"):
            award_badge("first_tracker_log")
