# lifelog/config/cron_manager.py
'''
cron_manager.py - Manage cron jobs for lifelog
'''
import platform
import subprocess
from pathlib import Path
import sys
from tomlkit import dumps
import lifelog.config.config_manager as cf


CONFIG_PATH = Path.home() / ".config" / "lifelog" / "config.toml"

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
    if system == "Windows":
        # Windows: use Task Scheduler
        apply_windows_tasks()
    elif system in ["Linux", "Darwin"]:
        # Linux or Mac: use cron
        apply_cron_jobs()
    else:
        print(f"⚠️ Scheduled jobs not supported on this OS: {system}")
              
def apply_cron_jobs():
    try:
        current = subprocess.getoutput("crontab -l")
        existing_lines = set(current.strip().split("\n")) if current else set()

        try:
            jobs = build_cron_jobs()
        except Exception as e:
            print(f"[red]❌ Failed to build cron jobs: {e}[/red]")
            return

        new_lines = [f"{schedule} {command}" for _, schedule, command in jobs]

        all_lines = set(
            line for line in existing_lines if line and not any(command in line for _, _, command in jobs)
        )
        all_lines.update(new_lines)

        final_crontab = "\n".join(sorted(all_lines)) + "\n"

        try:
            subprocess.run("crontab", input=final_crontab.encode(), check=True)
            print("[green]✅ Cron jobs updated successfully.[/green]")
        except subprocess.CalledProcessError as e:
            print(f"[red]❌ Failed to update crontab: {e}[/red]")
        except FileNotFoundError:
            print("[red]❌ 'crontab' command not found. Are you sure cron is installed?[/red]")
    
    except Exception as e:
        print(f"[red]❌ Unexpected error setting up cron jobs: {e}[/red]")

# TODO: Fix windows translation of cron jobs to tasks
def apply_windows_tasks():
    if sys.platform == "win32":
        import win32com.client
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')

        print("⚡ Setting up Windows Scheduled Tasks...")

        for name, schedule, command in build_cron_jobs():
            time_fields = schedule.split()
            try:
                if len(time_fields) >= 6:
                    minute, hour, day, month, _, _ = time_fields[0:6]

                    if "*" in hour and "/" in hour:
                        # Handle */N logic (every N hours)
                        interval = int(hour.split("/")[1])
                        for h in range(0, 24, interval):
                            schedule_task_windows(scheduler, root_folder, h, int(minute), command, name)
                    elif "*" in minute and "/" in minute:
                        # Handle */N minutes if you ever support it
                        interval = int(minute.split("/")[1])
                        # (Extra if you want every N minutes)
                    else:
                        # Normal specific time
                        schedule_task_windows(scheduler, root_folder, int(hour), int(minute), command, name)
                    
                    print(f"✅ Scheduled: {name}")
            except Exception as e:
                print(f"❌ Failed to schedule {name}: {e}")

        print("✅ Windows tasks setup complete!")

def schedule_task_windows(scheduler, root_folder, hour, minute, command, name):
    
    import datetime

    task_def = scheduler.NewTask(0)
    start_time = datetime.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start_time < datetime.datetime.now():
        start_time += datetime.timedelta(days=1)

    trigger = task_def.Triggers.Create(2)  # DAILY
    trigger.StartBoundary = start_time.isoformat()

    action = task_def.Actions.Create(0)  # EXEC
    action.ID = 'Lifelog'
    action.Path = "cmd.exe"
    action.Arguments = f'/c {command}'

    task_def.RegistrationInfo.Description = 'Lifelog Auto Scheduled Task'
    task_def.Settings.Enabled = True
    task_def.Settings.StopIfGoingOnBatteries = False

    TASK_CREATE_OR_UPDATE = 6
    TASK_LOGON_INTERACTIVE_TOKEN = 3 
    root_folder.RegisterTaskDefinition(
        f"Lifelog_{name}",
        task_def,
        TASK_CREATE_OR_UPDATE,
        '', '', TASK_LOGON_INTERACTIVE_TOKEN 
    )
