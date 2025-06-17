from __future__ import annotations
import logging
from shlex import quote
import shutil
from typing import Optional
# lifelog/config/cron_manager.py
'''
cron_manager.py - Manage cron jobs for lifelog
'''
import os
import platform
import subprocess
from pathlib import Path
import sys
from tomlkit import dumps
import lifelog.config.config_manager as cf

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


def _apply_user_cron_jobs(final_content: str) -> bool:
    """
    Merge our jobs into the current user's crontab, but first remove
    any existing Lifelog entries to prevent duplicates.
    """
    try:
        # 1) Grab existing crontab (empty string if none)
        proc = subprocess.run(
            ["crontab", "-l"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True
        )
        existing = proc.stdout if proc.returncode == 0 else ""
        lines = existing.splitlines()

        # 2) Filter out any old Lifelog entries (by command substring).
        filtered = [
            line for line in lines
            if "llog task auto_recur" not in line
            and "llog env sync-all" not in line
            and not line.strip().startswith("# Lifelog")
        ]

        # 3) Prepend a comment header so you can spot them in `crontab -l`
        header = "# Lifelog scheduled jobs"
        new_lines = filtered + [header] + final_content.splitlines()

        # 4) Install into user crontab
        new_cron = "\n".join(new_lines) + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=new_cron,
            text=True,
            check=True
        )
        logger.info("Installed Lifelog jobs into user crontab")
        return True

    except Exception as e:
        logger.error(f"Failed to update user crontab: {e}", exc_info=True)
        return False


def apply_cron_jobs() -> bool:
    """
    Install/update /etc/cron.d/lifelog_recur_auto, or user crontab fallback.
    """
    if not IS_POSIX:
        logger.info("Cron jobs skipped: non-POSIX OS")
        return False

    jobs = build_cron_jobs()
    if not jobs:
        logger.info("No cron jobs to apply.")
        return True

    # Build our file content
    lines = [f"{sched} root {cmd}" for (_, sched, cmd) in jobs]
    final_content = "\n".join(lines) + "\n"

    # Try system-wide /etc/cron.d first
    try:
        CRON_D_DIR.mkdir(parents=True, exist_ok=True)
        if CRON_FILE is None:
            logger.error("No CRON_FILE defined.")
            return False
        with CRON_FILE.open("w", encoding="utf-8") as f:
            f.write(final_content)
        CRON_FILE.chmod(0o644)
        logger.info(f"System cron file updated: {CRON_FILE}")
        return True

    except PermissionError as e:
        logger.error(
            f"Permission denied writing {CRON_FILE}: {e}", exc_info=True)
        # Fallback to user crontab
        return _apply_user_cron_jobs(final_content)

    except Exception as e:
        logger.error(
            f"Unexpected error writing cron file {CRON_FILE}: {e}", exc_info=True)
        # Also fallback
        return _apply_user_cron_jobs(final_content)

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
                check=False
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
            ], check=True)
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
