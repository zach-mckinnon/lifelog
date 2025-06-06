# tests/test_scheduler.py

import os
import stat
import platform
import subprocess
import tempfile
import json
import shutil

import pytest

# Adjust these imports to your code’s actual paths:
from lifelog.config import schedule_manager as sm
from lifelog.config import config_manager as cfg
from lifelog.config.schedule_manager import apply_scheduled_jobs, apply_cron_jobs, apply_windows_tasks, build_cron_jobs
from lifelog.first_time_run import setup_scheduled_tasks

# --------------------------------------
# FIXTURE: patch the USER_CONFIG path
# --------------------------------------


@pytest.fixture(autouse=True)
def fake_user_config(tmp_path, monkeypatch):
    """
    Redirect USER_CONFIG (and any calls to load_config()/save_config()) 
    into a temporary TOML file. We'll store and retrieve its contents via a dict.
    """
    # Create a real file under tmp_path, then monkey‐patch cf.USER_CONFIG to point at it.
    fake = tmp_path / "config.toml"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LIFELOG_DB_PATH", str(tmp_path / "fake_db.sqlite"))
    monkeypatch.setattr(cfg, "USER_CONFIG", fake)
    # Now when load_config() or save_config() is called, it will use this tmp file.
    # We also force is_host_server() to True for testing.
    monkeypatch.setattr(cfg, "is_host_server", lambda: True)
    yield


# --------------------------------------
# TEST: apply_cron_jobs() on “Unix”
# --------------------------------------
def test_apply_cron_jobs_creates_file_and_contents(tmp_path, monkeypatch):
    """
    - Monkey‐patch CRON_D_DIR so that cron_manager writes to tmp_path/cron.d
    - Build a fake [cron] section in config.toml
    - Call apply_cron_jobs() and verify:
        1. A file named lifelog_recur_auto appears under that temp directory
        2. File contents match “<schedule> root <command>\n” for each job
        3. File permissions are 0o644
    """
    # 1) Prepare a temporary “/etc/cron.d” substitute
    fake_cron_dir = tmp_path / "etc_cron_d"
    monkeypatch.setattr(sm, "CRON_D_DIR", fake_cron_dir)
    # Monkey‐patch CRON_FILE to be inside our fake dir
    monkeypatch.setattr(sm, "CRON_FILE", fake_cron_dir / "lifelog_recur_auto")

    # 2) Create a fake TOML config with 2 jobs under [cron]
    #    We’ll monkey‐patch cfg.load_config() to return exactly this dict.
    fake_conf = {
        "cron": {
            "recur_auto": {
                "schedule": "0 4 * * *",
                "command": "/usr/bin/llog task auto_recur"
            },
            "env_sync": {
                "schedule": "30 2 */4 * *",
                "command": "/usr/bin/llog env sync-all"
            }
        }
    }
    monkeypatch.setattr(cfg, "load_config", lambda: fake_conf)

    # 3) Call apply_cron_jobs() (under the assumption platform.system() in ["Linux","Darwin"])
    #    But first force platform.system() to return “Linux”
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    # Now actually create the directory and run
    fake_cron_dir.mkdir(parents=True, exist_ok=True)
    apply_cron_jobs()

    # 4) Inspect the resulting file
    cron_file = fake_cron_dir / "lifelog_recur_auto"
    assert cron_file.exists(), "Expected /etc/cron.d/lifelog_recur_auto to be created"

    text = cron_file.read_text(encoding="utf-8").strip().splitlines()
    # We expect exactly two lines, order not guaranteed
    expected_lines = {
        "0 4 * * * root /usr/bin/llog task auto_recur",
        "30 2 */4 * * root /usr/bin/llog env sync-all"
    }
    assert set(text) == expected_lines

    # 5) Permissions: must be 0o644
    st = cron_file.stat()
    # Mask out file type bits, compare only permission bits
    assert stat.S_IMODE(st.st_mode) == 0o644


# --------------------------------------
# TEST: apply_windows_tasks() on “Windows”
# --------------------------------------
def test_apply_windows_tasks_invokes_schtasks(tmp_path, monkeypatch):
    """
    - Monkey‐patch platform.system() → “Windows”
    - Build a fake [cron] section with two jobs
    - Stub subprocess.run to just record calls
    - Call apply_windows_tasks() and assert subprocess.run invoked with:
         • a “/Delete /TN Lifelog_<jobname> /F” call
         • a “/Create /SC DAILY /TN Lifelog_<jobname> /TR <command> /ST HH:MM /RI 1440 /F” call
    """
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        # Simulate successful execution

        class Dummy:
            returncode = 0
        return Dummy()

    # 1) Stub out subprocess.run
    monkeypatch.setattr(subprocess, "run", fake_run)

    # 2) Stub platform.system to “Windows”
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    # 3) Fake config with two cron‐style entries
    fake_conf = {
        "cron": {
            "recur_auto": {
                "schedule": "15 06 * * *",  # 06:15 every day
                "command": r"C:\path\to\llog task auto_recur"
            },
            "env_sync": {
                "schedule": "00 03 */4 * *",  # 03:00 every 4 hours
                "command": r"C:\path\to\llog env sync-all"
            }
        }
    }
    monkeypatch.setattr(cfg, "load_config", lambda: fake_conf)

    # 4) Run apply_windows_tasks()
    apply_windows_tasks()

    # 5) Now inspect recorded calls
    # For each job, there should be two calls: delete and create.
    # The names will be “Lifelog_recur_auto” and “Lifelog_env_sync”.
    job_names = {"recur_auto", "env_sync"}
    seen_delete = set()
    seen_create = set()

    for args in calls:
        # The first argument in args should be “schtasks”
        assert args[0].lower() == "schtasks"
        if "/delete" in (a.lower() for a in args):
            # e.g. ["schtasks","/Delete","/TN","Lifelog_recur_auto","/F"]
            # Extract “Lifelog_recur_auto”
            tn_index = next(i for i, a in enumerate(args)
                            if a.lower() == "/tn")
            task_name = args[tn_index+1]
            assert task_name.startswith("Lifelog_")
            seen_delete.add(task_name[len("Lifelog_"):])
        elif "/create" in (a.lower() for a in args):
            # e.g. ["schtasks","/Create","/SC","DAILY","/TN","Lifelog_recur_auto",
            #       "/TR","C:\path\to\llog task auto_recur","/ST","06:15","/RI","1440","/F"]
            tn_index = next(i for i, a in enumerate(args)
                            if a.lower() == "/tn")
            task_name = args[tn_index+1]
            assert task_name.startswith("Lifelog_")
            seen_create.add(task_name[len("Lifelog_"):])
            # Check that we have /TR, /ST, /SC, /RI, /F
            assert "/TR" in (a.upper() for a in args)
            assert "/SC" in (a.upper() for a in args)
            assert "/ST" in (a.upper() for a in args)
            assert "/RI" in (a.upper() for a in args)
        else:
            pytest.skip(f"Unexpected schtasks args: {args}")

    assert seen_delete == job_names
    assert seen_create == job_names


# --------------------------------------
# TEST: setup_scheduled_tasks() (CLI/wizard)
# --------------------------------------
def test_setup_scheduled_tasks_updates_config_and_calls_apply(tmp_path, monkeypatch):
    """
    - Monkey‐patch shutil.which("llog") to return a dummy path
    - Monkey‐patch typer.prompt and Confirm.ask so that “04:00” and “02:00” are chosen
    - Monkey‐patch apply_scheduled_jobs() so we can detect that it was invoked
    - Call setup_scheduled_tasks({}) directly
    - Inspect returned config dict to ensure:
        • “recur_auto” has schedule “0 4 * * *” and correct command path
        • “env_sync” has schedule “<minute> */4 * * *” and correct command path
    """
    # 1) Prepare a fresh, empty config dict
    initial_config = {
        "meta": {},
        "deployment": {"host_server": True}
    }

    # 2) Monkey‐patch shutil.which → return “/usr/local/bin/llog”
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/local/bin/llog")

    # 3) Stub out typer.prompt to return fixed values (“04:00” then “02:00”)
    answers = iter(["04:00", "02:00"])
    monkeypatch.setattr("typer.prompt", lambda *args, **kwargs: next(answers))

    # 4) Stub Confirm.ask to always return True (though this code path doesn’t prompt for Confirm)
    monkeypatch.setattr("rich.prompt.Confirm.ask",
                        lambda *args, **kwargs: True)

    # 5) Monkey‐patch apply_scheduled_jobs() so that we record a flag
    called = {"yes": False}
    monkeypatch.setattr("livelog.config.schedule_manager.apply_scheduled_jobs",
                        lambda: called.update({"yes": True}))

    # 6) Call the function
    cfg_after = setup_scheduled_tasks(initial_config.copy())

    # 7) The returned config should now have a “cron” section with “recur_auto” and “env_sync”
    assert "cron" in cfg_after
    cron = cfg_after["cron"]
    assert "recur_auto" in cron
    assert "env_sync" in cron

    # Check “recur_auto” contents
    ra = cron["recur_auto"]
    # “04:00” → minute=0, hour=4
    assert ra["schedule"] == "0 4 * * *"
    assert "llog task auto_recur" in ra["command"]

    # Check “env_sync” contents
    es = cron["env_sync"]
    # “02:00” → minute=0, hour=2/4 → in code: f"{minute} */4 * * *"
    assert es["schedule"] == "0 */4 * * *"
    assert "llog env sync-all" in es["command"]

    # 8) Finally, apply_scheduled_jobs() should have been invoked
    assert called["yes"] is True
