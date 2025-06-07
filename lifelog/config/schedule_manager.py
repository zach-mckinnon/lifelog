from __future__ import annotations
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


# ── NEW: single switch -----------------------------------------------------------------
IS_POSIX = os.name == "posix"                      # ← UPDATED
# ---------------------------------------------------------------------------------------

# ── POSIX-only constants (safe to be None on Windows) ----------------------------------
if IS_POSIX:
    CRON_D_DIR: Path = Path("/etc/cron.d")
    CRON_FILE: Path = CRON_D_DIR / "lifelog_recur_auto"
else:
    CRON_D_DIR: Optional[Path] = None          # ← type Optional[Path]
    CRON_FILE: Optional[Path] = None
# ---------------------------------------------------------------------------------------

CONFIG_PATH = cf.USER_CONFIG

# ----- LINUX Cron Jobs -----


def save_config(doc):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        f.write(dumps(doc))


def build_cron_jobs():
    cfg = cf.load_config()
    cron_section = cfg.get("cron", {})
    jobs = []
    for name, entry in cron_section.items():
        schedule = entry.get("schedule")
        command = entry.get("command")
        if schedule and command:
            jobs.append((name, schedule, command))
    return jobs


def apply_scheduled_jobs():
    """
    Entry-point called by first-time setup & CLI.

    * POSIX → write /etc/cron.d file
    * Windows → use schtasks.exe
    * Anything else → friendly warning
    """
    system = platform.system()
    if system in ("Linux", "Darwin"):
        apply_cron_jobs()
    elif system == "Windows":
        apply_windows_tasks()
    else:
        print(f"⚠️ Scheduled jobs not supported on this OS: {system}")


def apply_cron_jobs():
    """
    Write /etc/cron.d/lifelog_recur_auto with one line per job.
    No-ops on Windows so tests can run there.
    """
    if not IS_POSIX:                                      # ← UPDATED
        print("⚠️ Cron jobs skipped: non-POSIX OS")       # ← UPDATED
        return                                            # ← UPDATED

    jobs = build_cron_jobs()
    lines = [f"{schedule} root {command}"                 # unchanged logic
             for _, schedule, command in jobs]
    final_content = "\n".join(lines) + "\n"

    try:
        CRON_D_DIR.mkdir(parents=True, exist_ok=True)     # POSIX-only path

        with CRON_FILE.open("w", encoding="utf-8") as f:
            f.write(final_content)

        # Ensure readable by cron (rw-r--r--).
        # Only effective on real POSIX filesystems:
        if hasattr(os, "chmod") and IS_POSIX:             # ← UPDATED
            os.chmod(CRON_FILE, 0o644)                    # ← UPDATED

        print("[green]✅ /etc/cron.d/lifelog_recur_auto updated.[/green]")

    except PermissionError:
        print("[red]❌ Permission denied: run as root to edit /etc/cron.d.[/red]")
    except Exception as e:
        print(f"[red]❌ Unexpected error writing cron file: {e}[/red]")


# ────────────────────────────────────────────────────────────────────────────────────────
#  Windows helper (still WIP but now never called on POSIX)
# ────────────────────────────────────────────────────────────────────────────────────────


def apply_windows_tasks():
    """
    Create or update Windows Scheduled Tasks via schtasks.exe.
    Safe to call on POSIX – function is simply never reached.
    """
    jobs = build_cron_jobs()
    for name, schedule, command in jobs:
        fields = schedule.split()
        if len(fields) != 5:
            print(f"⚠️ Cannot parse schedule '{schedule}' for Windows")
            continue

        minute, hour, *_ = fields
        time_str = f"{int(hour):02d}:{int(minute):02d}"

        # Delete any existing task (ignore errors)
        subprocess.run(["schtasks", "/Delete", "/TN",
                       f"Lifelog_{name}", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Create the task
        subprocess.run([
            "schtasks",
            "/Create",
            "/SC", "DAILY",
            "/TN", f"Lifelog_{name}",
            "/TR", command,
            "/ST", time_str,
            "/RI", "1440",
            "/F"
        ], check=True)

    print("[green]✅ Windows scheduled tasks updated.[/green]")
