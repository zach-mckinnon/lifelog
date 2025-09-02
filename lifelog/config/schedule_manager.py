from __future__ import annotations

# lifelog/config/cron_manager.py
'''
cron_manager.py - Manage cron jobs for lifelog
'''
import os
import platform
import subprocess
from pathlib import Path
from tomlkit import dumps
import lifelog.config.config_manager as cf
import logging
from shlex import quote
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

IS_POSIX = os.name == "posix"

# ── POSIX-only constants (safe to be None on Windows) ----------------------------------
if IS_POSIX:
    CRON_D_DIR: Path = Path("/etc/cron.d")
    CRON_FILE: Path = CRON_D_DIR / "lifelog_recur_auto"
else:
    CRON_D_DIR: Optional[Path] = None
    CRON_FILE: Optional[Path] = None
# ---------------------------------------------------------------------------------------

CONFIG_PATH = cf.USER_CONFIG

# ----- LINUX Cron Jobs -----


def save_config(doc: dict) -> bool:
    """
    Write the given config dict to CONFIG_PATH in TOML format.
    - Ensures parent directory exists.
    - Returns True on success, False on failure.
    """
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(
            f"Failed to ensure config directory {CONFIG_PATH.parent}: {e}", exc_info=True)
        # Continue to attempt write; may still fail.

    try:
        toml_str = dumps(doc)
    except Exception as e:
        logger.error(
            f"Failed to serialize config to TOML in save_config: {e}", exc_info=True)
        return False

    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            f.write(toml_str)
        logger.info(f"Configuration saved to {CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(
            f"Failed to write config to {CONFIG_PATH}: {e}", exc_info=True)
        return False


def build_cron_jobs() -> list[tuple[str, str, str]]:
    """
    Read the [cron] section from config and build a list of jobs.
    Each job is a tuple (name, schedule, command).
    - If config load fails or format unexpected, returns empty list.
    """
    try:
        cfg = cf.load_config()
    except Exception as e:
        logger.error(
            f"Failed to load config in build_cron_jobs: {e}", exc_info=True)
        return []

    try:
        cron_section = cfg.get("cron", {})
        if not isinstance(cron_section, dict):
            logger.warning(
                f"[cron] section is not a dict in config: {cron_section!r}. Skipping.")
            return []
        jobs: list[tuple[str, str, str]] = []
        for name, entry in cron_section.items():
            if not isinstance(entry, dict):
                logger.warning(
                    f"Ignoring cron entry '{name}': not a dict: {entry!r}")
                continue
            schedule = entry.get("schedule")
            command = entry.get("command")
            if schedule and command:
                jobs.append((name, schedule, command))
            else:
                logger.warning(
                    f"Cron entry '{name}' missing 'schedule' or 'command'; skipping.")
        return jobs
    except Exception as e:
        logger.error(
            f"Unexpected error building cron jobs: {e}", exc_info=True)
        return []


def apply_scheduled_jobs() -> None:
    """
    Entry point: install/update scheduled jobs according to OS.
    - On POSIX (Linux or Darwin), calls apply_cron_jobs.
    - On Windows, calls apply_windows_tasks.
    - Otherwise, logs a warning.
    """
    try:
        system = platform.system()
    except Exception as e:
        logger.error(
            f"Failed to detect platform.system() in apply_scheduled_jobs: {e}", exc_info=True)
        return

    if system in ("Linux", "Darwin"):
        apply_cron_jobs()
    elif system == "Windows":
        apply_windows_tasks()
    else:
        logger.warning(f"Scheduled jobs not supported on this OS: {system}")


def _apply_user_cron_jobs(lines: str) -> bool:
    """
    Install the given cron lines into the *current user's* crontab,
    stripping out any old Lifelog entries first.
    """
    try:
        # TODO: Add timeout and error handling for Raspberry Pi subprocess calls
        # Subprocess calls can hang on slow systems
        # 1) read existing crontab (may be empty)
        p = subprocess.run(
            ["crontab", "-l"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True,
            timeout=30  # Add timeout for Raspberry Pi
        )
        old = p.stdout.splitlines() if p.returncode == 0 else []

        # 2) drop any previous Lifelog lines
        filtered = [
            ln for ln in old
            if "llog task auto_recur" not in ln
               and "llog env sync-all" not in ln
               and not ln.strip().startswith("# Lifelog")
        ]

        # 3) convert any "… root cmd" entries into user‐cron format
        user_lines = []
        for ln in lines.splitlines():
            parts = ln.split()
            if len(parts) >= 6 and parts[5] == "root":
                parts = parts[:5] + parts[6:]
            user_lines.append(" ".join(parts))

        # 4) assemble new crontab
        header = "# Lifelog scheduled jobs"
        newtab = "\n".join(filtered + [header] + user_lines) + "\n"

        # 5) install  
        # TODO: Add timeout to prevent hanging on slow Raspberry Pi systems
        subprocess.run(["crontab", "-"], input=newtab, text=True, check=True, timeout=30)
        logger.info("Installed Lifelog jobs into user crontab")
        return True

    except Exception as e:
        logger.error(f"Failed to write user crontab: {e}", exc_info=True)
        return False


def apply_cron_jobs() -> bool:
    """
    Try to write /etc/cron.d/lifelog_recur_auto; if that fails,
    silently fall back into the current user's crontab.
    Returns True if **either** method succeeds.
    """
    if not IS_POSIX:
        logger.info("Skipping cron setup on non-POSIX OS")
        return False

    jobs = build_cron_jobs()
    if not jobs:
        logger.info("No cron entries to apply")
        return True

    # build the raw text
    lines = [f"{sched} root {cmd}" for (_n, sched, cmd) in jobs]
    content = "\n".join(lines) + "\n"

    # 1️⃣ Try system‐wide /etc/cron.d
    try:
        CRON_D_DIR.mkdir(parents=True, exist_ok=True)
        with CRON_FILE.open("w", encoding="utf-8") as f:
            f.write(content)
        try:
            CRON_FILE.chmod(0o644)
        except Exception:
            pass
        logger.info(f"Wrote system cron file: {CRON_FILE}")
        return True

    except PermissionError:
        # no sudo: drop silently into user crontab
        logger.warning(
            f"No permission to write {CRON_FILE}; using user crontab")

    except Exception as e:
        logger.warning(
            f"Error writing {CRON_FILE}: {e}; falling back", exc_info=True)

    # 2️⃣ Fallback
    return _apply_user_cron_jobs(content)

# ────────────────────────────────────────────────────────────────────────────────────────
#  Windows helper (still WIP but now never called on POSIX)
# ────────────────────────────────────────────────────────────────────────────────────────


def apply_windows_tasks() -> bool:
    """
    Create or update Windows Scheduled Tasks via schtasks.exe.
    - Reads jobs from config. For each job:
      * Expects a cron-like schedule of 5 fields (minute hour day month weekday).
      * Only supports daily schedules at given hour:minute; warns/skips others.
      * Deletes any existing task named 'Lifelog_<name>' then creates a daily task.
    - Returns True if all applicable tasks succeeded, False if any failure.
    """
    try:
        jobs = build_cron_jobs()
    except Exception as e:
        logger.error(
            f"Failed to build cron jobs in apply_windows_tasks: {e}", exc_info=True)
        return False

    if not jobs:
        logger.info(
            "No scheduled jobs to apply on Windows (empty [cron] section).")
        return True

    all_ok = True
    for name, schedule, command in jobs:
        # Simple cron parsing: expecting 5 fields
        fields = schedule.split()
        if len(fields) != 5:
            logger.warning(
                f"Cannot parse schedule '{schedule}' for Windows: not 5 fields. Skipping job '{name}'.")
            all_ok = False
            continue

        minute_str, hour_str, day_str, month_str, weekday_str = fields
        # Only support daily tasks: day_str, month_str, weekday_str should be "*"
        if not (day_str == "*" and month_str == "*" and weekday_str == "*"):
            logger.warning(
                f"Schedule '{schedule}' for job '{name}' is not a simple daily schedule. "
                "Windows scheduling limited; skipping."
            )
            all_ok = False
            continue

        # Convert hour/minute to int; guard against invalid ints
        try:
            minute = int(minute_str)
            hour = int(hour_str)
            if not (0 <= minute < 60 and 0 <= hour < 24):
                raise ValueError("Hour/minute out of range")
            time_str = f"{hour:02d}:{minute:02d}"
        except Exception as e:
            logger.warning(
                f"Invalid hour/minute in schedule '{schedule}' for job '{name}': {e}. Skipping.")
            all_ok = False
            continue

        task_name = f"Lifelog_{name}"
        # Delete existing task, ignoring errors
        try:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", task_name, "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=30
            )
        except Exception as e:
            logger.warning(
                f"Failed to delete existing scheduled task '{task_name}': {e}", exc_info=True)
            # continue to creation attempt anyway

        # Create the task
        try:
            subprocess.run([
                "schtasks",
                "/Create",
                "/SC", "DAILY",
                "/TN", task_name,
                "/TR", command,
                "/ST", time_str,
                "/RI", "1440",
                "/F"
            ], check=True, timeout=30)
            logger.info(
                f"Windows scheduled task created/updated: {task_name} at {time_str}")
        except subprocess.CalledProcessError as e:
            logger.error(
                f"schtasks failed for job '{name}': {e}", exc_info=True)
            all_ok = False
        except FileNotFoundError as e:
            logger.error(f"schtasks.exe not found: {e}", exc_info=True)
            all_ok = False
        except Exception as e:
            logger.error(
                f"Unexpected error creating scheduled task '{task_name}': {e}", exc_info=True)
            all_ok = False

    if all_ok:
        logger.info("Windows scheduled tasks updated successfully.")
    else:
        logger.warning(
            "Some Windows scheduled tasks failed to update; check logs.")
    return all_ok


def build_linux_notifier(cmd_msg: str) -> str:
    """
    Build a bash-safe one-liner that sends a persistent critical notification
    and plays a sound. 
    """
    # timeout 0 = until dismissed; urgency critical = high visibility
    notify = f"notify-send -u critical -t 0 {quote(cmd_msg)}"
    # try canberra-gtk-play if installed, otherwise paplay, otherwise bell
    if shutil.which("canberra-gtk-play"):
        sound = "canberra-gtk-play --id='message'"
    elif shutil.which("paplay"):
        sound = "paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
    else:
        # fallback to terminal bell
        sound = "printf '\\a'"
    # run both
    return f"bash -lc {quote(notify + ' && ' + sound)}"


def build_windows_notifier(cmd_msg: str) -> list[str]:
    """
    Returns a PowerShell command array that:
     - plays the system Exclamation sound,
     - shows a blocking MessageBox until user clicks OK.
    """
    ps = [
        "powershell.exe", "-NoProfile", "-Command",
        # load forms and media, play sound, then MessageBox
        (
            "[Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;"
            "[Reflection.Assembly]::LoadWithPartialName('System.Drawing') | Out-Null;"
            "[System.Media.SystemSounds]::Exclamation.Play();"
            f"[void][System.Windows.Forms.MessageBox]::Show({quote(cmd_msg)},"
            "'Lifelog Reminder',"
            "[System.Windows.Forms.MessageBoxButtons]::OK,"
            "[System.Windows.Forms.MessageBoxIcon]::Warning,"
            "[System.Windows.Forms.MessageBoxDefaultButton]::Button1,"
            "[System.Windows.Forms.MessageBoxOptions]::DefaultDesktopOnly)"
        )
    ]
    return ps
