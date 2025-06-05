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

CRON_D_DIR = Path("/etc/cron.d")
CRON_FILE = CRON_D_DIR / "lifelog_recur_auto"
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
    system = platform.system()
    if system in ["Linux", "Darwin"]:
        apply_cron_jobs()
    elif system == "Windows":
        apply_windows_tasks()
    else:
        print(f"⚠️ Scheduled jobs not supported on this OS: {system}")


def apply_cron_jobs():
    jobs = build_cron_jobs()  # list of (name, schedule, command)
    lines = []

    for name, schedule, command in jobs:
        # schedule is “M H * * *”; we append “root <command>”
        lines.append(f"{schedule} root {command}")

    final_content = "\n".join(lines) + "\n"

    try:
        # 1) Ensure /etc/cron.d exists; if it does not, create it (rare on some distros)
        CRON_D_DIR.mkdir(parents=True, exist_ok=True)

        # 2) Write the file as root
        with open(str(CRON_FILE), "w", encoding="utf-8") as f:
            f.write(final_content)

        # 3) Ensure file has correct permissions (0644) so cron can read it
        os.chmod(str(CRON_FILE), 0o644)

        print(f"[green]✅ /etc/cron.d/lifelog_recur_auto updated.[/green]")

    except PermissionError:
        print(
            "[red]❌ Permission denied: Please run as root to write /etc/cron.d files.[/red]")
    except Exception as e:
        print(f"[red]❌ Unexpected error writing /etc/cron.d file: {e}[/red]")


# -- Windows Scheduled Tasks (WIP) -----


def apply_windows_tasks():
    """
    Translate each (name, schedule, command) into a Windows Scheduled Task
    via schtasks.exe or the Win32 COM API. Example below uses `schtasks`.
    """
    jobs = build_cron_jobs()  # list of (name, schedule, command)
    for name, schedule, command in jobs:
        # Expect schedule in cron form “M H * * *” → parse hour and minute
        fields = schedule.split()
        if len(fields) != 5:
            print(f"⚠️ Cannot parse schedule '{schedule}' for Windows")
            continue

        minute, hour, day, month, dow = fields
        # Windows’ schtasks needs a time string “HH:MM”
        time_str = f"{int(hour):02d}:{int(minute):02d}"

        # Example: create or delete old same‐name task, then create a new one
        # 1) Delete existing task
        subprocess.run(["schtasks", "/Delete", "/TN",
                       f"Lifelog_{name}", "/F"], stderr=subprocess.DEVNULL)

        # 2) Create scheduled task to run daily at time_str
        subprocess.run([
            "schtasks",
            "/Create",
            "/SC", "DAILY",
            "/TN", f"Lifelog_{name}",
            "/TR", command,
            "/ST", time_str,
            "/RI", "1440",  # repetition interval: 1440 minutes = 24 hours
            "/F"
        ], check=True)

    print("[green]✅ Windows scheduled tasks updated.[/green]")
