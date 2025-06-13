#!/usr/bin/env python3
import uuid
from datetime import datetime, timedelta, timezone

from lifelog.utils.db import (
    task_repository,
    time_repository,
    track_repository,
    report_repository,
    environment_repository,
)
from lifelog.utils.db.database_manager import initialize_schema, get_connection


def seed_test_data():
    """
    Wipe and re-create schema, then insert:
      - 10 tasks spanning last 7 days
      - 1–3 time entries per task
      - 5 trackers + one sum-goal + daily entries
      - A dummy weather environment record
    """

    # --- deferred imports to avoid circularity ---
    from lifelog.utils.db.database_manager import initialize_schema
    from lifelog.utils.db.db_helper import get_connection
    from lifelog.utils.db import (
        task_repository,
        time_repository,
        track_repository,
        environment_repository,
    )

    # 1) Fresh DB
    conn = get_connection()
    conn.close()
    initialize_schema()

    now = datetime.now(timezone.utc)

    # 2) Tasks
    tasks = []
    for i in range(1, 11):
        created = (now - timedelta(days=i)).isoformat()
        due = (now - timedelta(days=i-5)).isoformat()
        data = {
            "uid": str(uuid.uuid4()),
            "title": f"Test Task {i}",
            "created": created,
            "due": due,
            "status": "done" if i % 3 == 0 else "backlog",
            "importance": (i % 5) + 1,
            "priority": 0,
            "tags": None,
            "notes": f"Auto‐seeded note {i}",
        }
        task = task_repository.add_task(data)
        tasks.append(task)

    # 3) Time entries
    for t in tasks:
        for j in range(1, (t.id % 3) + 2):
            start = now - timedelta(days=j, hours=j*2)
            end = start + timedelta(minutes=15 * j)
            time_repository.start_time_entry({
                "title": t.title,
                "task_id": t.id,
                "start": start.isoformat(),
                "category": getattr(t, "category", None),
                "project": getattr(t, "project", None),
                "notes": f"Session {j}",
            })
            time_repository.stop_active_time_entry(end_time=end.isoformat())

    # 4) Dummy weather
    environment_repository.add_environment_data("weather", {
        "uid": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "latitude": 37.7749,
        "longitude": -122.4194,
        "data": {"dummy": True},
    })

    # 5) Trackers, goals & entries
    for k in range(1, 6):
        tr = track_repository.add_tracker({
            "title": f"Metric {k}",
            "type": "range",
            "category": None,
        })
        # one “sum” goal
        track_repository.add_goal(tr.id, {
            "kind": "sum",
            "period": "day",
            "amount": 100 + k * 10,
            "unit": "units",
            "target": 7 * (100 + k * 10),
        })
        # 7 days of entries
        for d in range(7):
            ts = (now - timedelta(days=d)).isoformat()
            val = (k * 5) + d
            track_repository.add_tracker_entry(
                tracker_id=tr.id, timestamp=ts, value=val
            )

    print("✅ Seed complete (10 tasks, time-logs, 5 trackers+goals, weather).")


if __name__ == "__main__":
    seed_test_data()
