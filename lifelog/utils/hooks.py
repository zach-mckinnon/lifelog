import subprocess
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from lifelog.utils.db import safe_query
from lifelog.utils.db.gamify_repository import (
    add_xp,
    apply_xp_bonus,
    _ensure_profile,
    add_skill_xp,
    award_badge,
    add_notification,
    get_skill_level,
)
from lifelog.utils.notifications import notify_cli, notify_tui

logger = logging.getLogger(__name__)
# Removed unused threading.local() for Pi optimization

_DEFAULT_DIR = Path.home() / ".lifelog" / "hooks"
HOOKS_DIR = Path(os.getenv("LIFELOG_HOOKS_DIR", _DEFAULT_DIR))


def ensure_hooks_dir() -> Path:
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    return HOOKS_DIR


def run_hooks(module: str, action: str, entity: Any) -> None:
    """
    1) Always run our internal gamify logic.
    2) Then, if there are external hook scripts matching
    ~/.lifelog/hooks/post-<module>-<action>*, invoke each of them with the JSON payload returned by build_payload().
    """
    # ——— 1) Internal gamification —————————————————————————————————
    try:
        gamify(module, action, entity)
    except Exception:
        logger.exception("Error in internal gamify()")

    # ——— 2) External hook scripts —————————————————————————————————————
    if not HOOKS_DIR.exists():
        return

    prefix = f"post-{module}-{action}"
    hooks = sorted(
        p for p in HOOKS_DIR.iterdir()
        if p.name.startswith(prefix) and os.access(p, os.X_OK)
    )
    if not hooks:
        return

    # Build JSON payload for external scripts
    payload = build_payload(module, action, entity)
    payload_json = json.dumps(payload)

    for hook in hooks:
        try:
            proc = subprocess.Popen(
                [str(hook)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            _, stderr = proc.communicate(input=payload_json, timeout=30)
            if proc.returncode != 0:
                logger.error(
                    "Hook %s errored: %s",
                    hook.name,
                    stderr.strip() or "(no message)",
                )
        except Exception:
            logger.exception("Error executing hook %s", hook.name)


def build_payload(module: str, action: str, entity: Any) -> Dict[str, Any]:
    """
    Construct the standard JSON payload passed to external hook scripts.
    """
    return {
        "event":     f"{module}_{action}",
        "module":    module,
        "action":    action,
        "timestamp": datetime.now().isoformat() + "Z",
        "entity":    entity_to_dict(entity),
        "context": {
            "user":        os.getenv("USER", "unknown"),
            "app_version": "1.0.0",
        },
    }


def entity_to_dict(entity) -> Dict[str, Any]:
    if hasattr(entity, "to_dict"):
        return entity.to_dict()
    if hasattr(entity, "_asdict"):
        return entity._asdict()
    if isinstance(entity, dict):
        return entity
    return {"raw": str(entity)}


def gamify(module: str, event: str, entity: Any):
    """
    Internal XP/badge logic. Now takes the dataclass directly
    so we can do entity.finished, entity.due, etc.
    """
    # 1) Determine XP context
    if module == "task" and event == "completed":
        on_time = entity.end <= entity.due
        base_xp = 50 if on_time else 20
        context = "task_on_time" if on_time else "task_late"
    elif module == "task" and event == "pomodoro_done":
        base_xp = 10
        context = "pomodoro"
    elif module == "tracker" and event == "logged":
        base_xp = 5
        context = "tracker"
    else:
        return

    # 2) Apply bonuses & award to profile
    adjusted = apply_xp_bonus(base_xp, context)
    profile = add_xp(adjusted)
    add_notification(
        profile.id, f"You earned {adjusted} XP for {context.replace('_',' ')}!")

    # 3) Skill XP
    skill_map = {
        "task_on_time": "task_mastery",
        "task_late":    "task_mastery",
        "pomodoro":     "focus_mastery",
        "tracker":      "tracker_mastery",
    }
    sid = skill_map.get(context)
    if sid:
        old = get_skill_level(sid)
        skill = add_skill_xp(sid, adjusted // 2)
        if skill.level > old:
            add_notification(
                profile.id, f"Your '{skill.name}' skill leveled up to {skill.level}!")

    # 4) First-time badges
    user = _ensure_profile()

    def _has(uid: str) -> bool:
        return bool(safe_query(
            "SELECT 1 FROM profile_badges pb JOIN badges b ON pb.badge_id=b.id "
            "WHERE pb.profile_id=? AND b.uid=?",
            (user.id, uid),
        ))
    if context == "task_on_time" and not _has("first_task_on_time"):
        award_badge("first_task_on_time")
        add_notification(profile.id, "🏅 First On-Time Task badge earned!")
    if context == "pomodoro" and not _has("first_pomodoro"):
        award_badge("first_pomodoro")
        add_notification(profile.id, "🏅 First Pomodoro badge earned!")
    if context == "tracker" and not _has("first_tracker_log"):
        award_badge("first_tracker_log")
        add_notification(profile.id, "🏅 First Tracker Log badge earned!")
