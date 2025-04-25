# lifelog/config/cron_manager.py
import subprocess
from config_manager import load_config
from pathlib import Path
from tomlkit import parse, document, dumps

CONFIG_PATH = Path.home() / ".config" / "lifelog" / "config.toml"

def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r") as f:
            return parse(f.read())
    else:
        return document()

def save_config(doc):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w") as f:
        f.write(dumps(doc))

def build_cron_lines():
    config = load_config()
    cron_section = config.get("cron", {})
    lines = []
    for name, entry in cron_section.items():
        schedule = entry.get("schedule")
        command = entry.get("command")
        if schedule and command:
            lines.append(f"{schedule} {command}")
    return lines

def apply_cron_jobs():
    current = subprocess.getoutput("crontab -l")
    existing_lines = set(current.strip().split("\n")) if current else set()
    new_lines = build_cron_lines()
    
    all_lines = set(line for line in existing_lines if line and not any("llog" in line for line in new_lines))
    all_lines.update(new_lines)

    final_crontab = "\n".join(sorted(all_lines)) + "\n"
    subprocess.run("crontab", input=final_crontab.encode(), check=True)
    print("✅ Cron jobs updated.")
