import os
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

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
        except Exception as e:
            logger.exception(f"Error executing hook {hook.name}: {str(e)}")


def build_payload(module: str, action: str, entity: Any) -> Dict[str, Any]:
    """Construct standardized hook payload"""
    return {
        "event": f"{module}_{action}",
        "module": module,
        "action": action,
        "timestamp": datetime.utcnow().isoformat() + "Z",
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
