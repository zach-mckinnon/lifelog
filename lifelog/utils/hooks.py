import threading
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
_tls = threading.local()

_DEFAULT_DIR = Path.home() / ".lifelog" / "hooks"
HOOKS_DIR = Path(os.getenv("LIFELOG_HOOKS_DIR", _DEFAULT_DIR))


def ensure_hooks_dir() -> Path:
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    return HOOKS_DIR


def run_hooks(module: str, action: str, entity: Any) -> None:
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
            proc = subprocess.Popen(
                [str(hook)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            _, stderr = proc.communicate(input=json_payload, timeout=30)
            if proc.returncode != 0:
                logger.error(
                    "Hook %s errored: %s", hook.name, stderr.strip() or "(no message)"
                )
            try:
                gamify(module, action, payload)
            except Exception:
                logger.exception("Error in gamify()")
        except Exception as e:
            logger.exception("Error executing hook %s: %s", hook.name, e)


def build_payload(module: str, action: str, entity: Any) -> Dict[str, Any]:
    return {
        "event":   f"{module}_{action}",
        "module":  module,
        "action":  action,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "entity":  entity_to_dict(entity),
        "context": {
            "user": os.getenv("USER", "unknown"),
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


def set_current_stdscr(stdscr):
    _tls.stdscr = stdscr


def _notify(lines, title="🔔 Notification"):
    stdscr = getattr(_tls, "stdscr", None)
    if stdscr:
        notify_tui(stdscr, lines, title)
    else:
        for line in lines:
            notify_cli(line)


def gamify(module: str, event: str, payload):
    # 1) Determine base XP & context
    if module == "task" and event == "completed":
        on_time = payload.finished <= payload.due
        base_xp = 50 if on_time else 20
        context = "task_on_time" if on_time else "task_late"
    elif module == "task" and event == "pomodoro_done":
        base_xp = 10
        context = "pomodoro"
    elif module == "tracker" and event == "logged":
        base_xp = 5
        context = "tracker"
    else:
        return  # no XP

    # 2) Apply all bonuses
    adjusted_xp = apply_xp_bonus(base_xp, context)

    # 3) Award profile XP & notify
    profile = add_xp(adjusted_xp)
    add_notification(
        profile.id,
        f"You earned {adjusted_xp} XP for {context.replace('_',' ')}!"
    )

    # 4) Award skill XP & notify on skill-level-up
    skill_map = {
        "task_on_time": "task_mastery",
        "task_late":    "task_mastery",
        "pomodoro":     "focus_mastery",
        "tracker":      "tracker_mastery",
    }
    skill_uid = skill_map.get(context)
    if skill_uid:
        old_lvl = get_skill_level(skill_uid)
        new_skill = add_skill_xp(skill_uid, adjusted_xp // 2)
        if new_skill.level > old_lvl:
            add_notification(
                profile.id,
                f"Your '{new_skill.name}' skill just leveled up to {new_skill.level}!"
            )

    # 5) First-time badges
    user = _ensure_profile()

    def _has_badge(uid: str) -> bool:
        return bool(safe_query(
            "SELECT 1 FROM profile_badges pb JOIN badges b ON pb.badge_id=b.id "
            "WHERE pb.profile_id=? AND b.uid=?", (user.id, uid)
        ))

    if context == "task_on_time" and not _has_badge("first_task_on_time"):
        award_badge("first_task_on_time")
        add_notification(
            profile.id, "🏅 You’ve earned the “First On-Time Task” badge!")

    if context == "pomodoro" and not _has_badge("first_pomodoro"):
        award_badge("first_pomodoro")
        add_notification(
            profile.id, "🏅 You’ve earned the “First Pomodoro” badge!")

    if context == "tracker" and not _has_badge("first_tracker_log"):
        award_badge("first_tracker_log")
        add_notification(
            profile.id, "🏅 You’ve earned the “First Tracker Log” badge!")
