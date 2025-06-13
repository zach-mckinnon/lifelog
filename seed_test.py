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
      - 10 tasks spanning last 7 days with varied status/due dates
      - For each task: 1–3 time entries of 15–90min
      - 5 trackers with daily entries over past week
      - 1 goal per tracker (sum over week) 
      - A fake weather env record
    """
    # 1) Fresh DB
    conn = get_connection()
    conn.close()
    initialize_schema()

    now = datetime.now(timezone.utc)
    # 2) Seed tasks
    tasks = []
    for i in range(1, 11):
        created = (now - timedelta(days=i)).isoformat()
        due = (now - timedelta(days=i-5)).isoformat()  # some past, some future
        data = {
            "uid": str(uuid.uuid4()),
            "title": f"Test Task {i}",
            "created": created,
            "due": due,
            "status": "backlog" if i % 3 else "done",
            "importance": (i % 5) + 1,
            "priority": 0,            # let repo fill via calculate_priority()
            "tags": None,
            "notes": f"Auto‐seeded note {i}",
        }
        # :contentReference[oaicite:0]{index=0}
        task = task_repository.add_task(data)
        tasks.append(task)

    # 3) Seed time entries for each task
    for t in tasks:
        # 1–3 entries per task
        for j in range(1, (t.id % 3) + 2):
            start = now - timedelta(days=j, hours=j*2)
            end = start + timedelta(minutes=15 * j)
            time_repository.start_time_entry({
                "title": t.title,
                "task_id": t.id,
                "start": start.isoformat(),
                "category": t.category,
                "project": t.project,
                "notes": f"Session {j}",
            })
            time_repository.stop_active_time_entry(end_time=end.isoformat())

    # 4) Fake‐sync a weather record for start-day flows
    environment_repository.add_environment_data("weather", {
        "uid": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "latitude": 37.7749,
        "longitude": -122.4194,
        "data": {"dummy": True},
    })

    # 5) Seed 5 trackers
    trackers = []
    for k in range(1, 6):
        tr = track_repository.add_tracker({
            "title": f"Metric {k}",
            "type": "range",
            "category": None,
        })  # :contentReference[oaicite:1]{index=1}
        trackers.append(tr)

        # 6) One “sum” goal per tracker: sum over past 7 days
        goal = track_repository.add_goal(tr.id, {
            "kind": "sum",
            "period": "day",
            "amount": 100 + k*10,
            "unit": "units",
            "target": 7 * (100 + k*10),
        })

        # 7) Daily entries over past week
        for d in range(7):
            ts = (now - timedelta(days=d)).isoformat()
            val = (k * 5) + d
            track_repository.add_tracker_entry(
                tracker_id=tr.id, timestamp=ts, value=val)

    print("✅ Seeded 10 tasks, time entries, 5 trackers + goals + weather.")


if __name__ == "__main__":
    seed_test_data()
