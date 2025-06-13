
import datetime
import uuid


def seed_test_data():
    # defer imports so __init__.py won’t run at module‐load time
    from lifelog.utils.db.database_manager import initialize_schema, _resolve_db_path
    from lifelog.utils.db.db_helper import get_connection

    # 1) Rebuild schema
    conn = get_connection()
    conn.close()
    initialize_schema()

    now = datetime.now(datetime.timezone.utc).isoformat()

    # helper to execute SQL
    def exec_sql(sql, params=()):
        with get_connection() as c:
            c.execute(sql, params)

    # 2) Insert 10 fake tasks
    for i in range(1, 11):
        uid = str(uuid.uuid4())
        title = f"Seed Task {i}"
        created = (datetime.now(datetime.timezone.utc) -
                   datetime.datetime.timedelta(days=i)).isoformat()
        due = (datetime.now(datetime.timezone.utc) -
               datetime.timedelta(days=i-5)).isoformat()
        status = "done" if i % 3 == 0 else "backlog"
        importance = (i % 5) + 1
        notes = f"Auto-seed note {i}"
        exec_sql(
            "INSERT INTO tasks (uid, title, created, due, status, importance, priority, tags, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, title, created, due, status, importance, 0, None, notes)
        )

    # 3) Insert time_entries for each task
    #    We'll grab their IDs back from the DB
    with get_connection() as c:
        rows = c.execute("SELECT id, title FROM tasks").fetchall()
    for task_id, title in rows:
        # 1–3 entries per task
        for j in range(1, (task_id % 3) + 2):
            start = (datetime.now(datetime.timezone.utc) -
                     datetime.timedelta(days=j, hours=j*2)).isoformat()
            end = (datetime.fromisoformat(start) +
                   datetime.timedelta(minutes=15*j)).isoformat()
            exec_sql(
                "INSERT INTO time_logs (uid, title, task_id, start, end, duration_minutes, category, project, tags, notes, distracted_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), title, task_id, start, end,
                 15*j, None, None, None, f"Session {j}", 0)
            )

    # 4) Insert one dummy environment record
    exec_sql(
        "INSERT INTO environment_data (uid, table_name, timestamp, data) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), "weather", now,
         '{"latitude":37.7749,"longitude":-122.4194}')
    )

    # 5) Insert 5 trackers + one sum‐goal + 7 daily entries
    for k in range(1, 6):
        # tracker
        exec_sql(
            "INSERT INTO trackers (uid, title, type, category, tags, notes, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), f"Metric {k}", "range", None, None, None, now)
        )
    # fetch tracker ids
    with get_connection() as c:
        trackers = c.execute("SELECT id FROM trackers ORDER BY id").fetchall()
    for idx, (tr_id,) in enumerate(trackers, start=1):
        # goal
        amount = 100 + idx*10
        target = amount * 7
        exec_sql(
            "INSERT INTO goals (uid, tracker_id, kind, period, amount, unit, target) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), tr_id, "sum", "day", amount, "units", target)
        )
        # entries – one per day
        for d in range(7):
            ts = (datetime.now(datetime.timezone.utc) -
                  datetime.timedelta(days=d)).isoformat()
            val = idx*5 + d
            exec_sql(
                "INSERT INTO tracker_entries (tracker_id, timestamp, value) VALUES (?, ?, ?)",
                (tr_id, ts, val)
            )

    print("✅ Seed complete: 10 tasks + time_logs, 5 trackers+goals+entries, weather.")


if __name__ == "__main__":
    seed_test_data()
