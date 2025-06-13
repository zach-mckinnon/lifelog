
import datetime
import uuid


#!/usr/bin/env python3
import os
import uuid
import sqlite3
from datetime import datetime, timedelta, timezone

# Figure out where to write the DB
DB = os.environ.get("LIFELOG_DB_PATH", "lifelog.db")

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS trackers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE,
    title TEXT,
    type TEXT,
    category TEXT,
    created DATETIME,
    notes TEXT,
    tags TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE,
    title TEXT,
    project TEXT,
    category TEXT,
    importance INTEGER,
    created DATETIME,
    due DATETIME,
    status TEXT,
    start DATETIME,
    end DATETIME,
    priority FLOAT,
    recur_interval INTEGER,
    recur_unit TEXT,
    recur_days_of_week TEXT,
    recur_base DATETIME,
    notes TEXT,
    tags TEXT
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE,
    tracker_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    period TEXT DEFAULT 'day',
    FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS goal_sum (
    goal_id INTEGER PRIMARY KEY,
    uid TEXT UNIQUE,
    amount REAL NOT NULL,
    unit TEXT,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS goal_count (
    goal_id INTEGER PRIMARY KEY,
    uid TEXT UNIQUE,
    amount INTEGER NOT NULL,
    unit TEXT,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS goal_bool (
    goal_id INTEGER PRIMARY KEY,
    uid TEXT UNIQUE,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS goal_streak (
    goal_id INTEGER PRIMARY KEY,
    uid TEXT UNIQUE,
    target_streak INTEGER,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS goal_range (
    goal_id INTEGER PRIMARY KEY,
    uid TEXT UNIQUE,
    min_amount REAL,
    max_amount REAL,
    unit TEXT,
    mode TEXT,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tracker_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracker_id INTEGER NOT NULL,
    timestamp DATETIME,
    value REAL,
    FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS time_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE,
    title TEXT,
    task_id INTEGER,
    start DATETIME,
    end DATETIME,
    duration_minutes REAL,
    category TEXT,
    project TEXT,
    tags TEXT,
    notes TEXT,
    distracted_minutes INTEGER,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS environment_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE,
    source TEXT,
    timestamp DATETIME,
    data TEXT
);
"""


def seed():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # 1) Create schema
    cur.executescript(SCHEMA_DDL)
    now = datetime.now(timezone.utc).isoformat()

    # 2) Seed 10 tasks
    for i in range(1, 11):
        cur.execute(
            "INSERT INTO tasks (uid,title,created,due,status,importance,priority,notes) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (
                str(uuid.uuid4()),
                f"Seed Task {i}",
                now,
                (datetime.now(timezone.utc)-timedelta(days=i-5)).isoformat(),
                "done" if i % 3 == 0 else "backlog",
                (i % 5)+1,
                f"Auto-note {i}"
            )
        )
    # 3) Time logs for each task
    task_rows = cur.execute("SELECT id,title FROM tasks").fetchall()
    for task_id, title in task_rows:
        for j in range(1, (task_id % 3) + 2):
            start = (datetime.now(timezone.utc) -
                     timedelta(days=j, hours=j*2)).isoformat()
            end = (datetime.fromisoformat(start) +
                   timedelta(minutes=15*j)).isoformat()
            cur.execute(
                "INSERT INTO time_logs (uid,title,task_id,start,end,duration_minutes,notes,distracted_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    str(uuid.uuid4()),
                    title,
                    task_id,
                    start,
                    end,
                    15*j,
                    f"Session {j}"
                )
            )
    # 4) Dummy weather
    cur.execute(
        "INSERT INTO environment_data (uid,source,timestamp,data) VALUES (?, 'weather', ?, ?)",
        (str(uuid.uuid4()), now, '{"latitude":37.7749,"longitude":-122.4194"}')
    )
    # 5) 5 trackers + goals + entries
    for k in range(1, 6):
        cur.execute(
            "INSERT INTO trackers (uid,title,type,created) VALUES (?, ?, 'range', ?)",
            (str(uuid.uuid4()), f"Metric {k}", now)
        )
    tracker_ids = [r[0]
                   for r in cur.execute("SELECT id FROM trackers").fetchall()]
    for idx, tr_id in enumerate(tracker_ids, start=1):
        amount = 100 + idx*10
        target = amount * 7
        cur.execute(
            "INSERT INTO goals (uid,tracker_id,title,kind,period) VALUES (?, ?, ?, 'sum', 'day')",
            (str(uuid.uuid4()), tr_id, f"SumGoal{idx}")
        )
        cur.execute(
            "INSERT INTO goal_sum (goal_id,uid,amount,unit) VALUES (?, ?, ?, 'units')",
            (cur.lastrowid, str(uuid.uuid4()), amount)
        )
        # daily entries
        for d in range(7):
            ts = (datetime.now(timezone.utc)-timedelta(days=d)).isoformat()
            val = idx*5 + d
            cur.execute(
                "INSERT INTO tracker_entries (tracker_id,timestamp,value) VALUES (?, ?, ?)",
                (tr_id, ts, val)
            )

    conn.commit()
    conn.close()
    print("✅ Seed complete — schema + test data in", DB)


if __name__ == "__main__":
    seed()
