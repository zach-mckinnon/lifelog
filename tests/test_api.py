# tests/test_api.py

import json
import uuid
import pytest
from datetime import datetime, timedelta

from lifelog.app import app as flask_app


from lifelog.config import config_manager as cfg
from lifelog.utils.db.database_manager import initialize_schema, get_connection
from lifelog.utils.db import database_manager as dbman

# -------------------------------------------------------------------------------------------------
# Fixture: create a Flask test client pointing at a fresh temp SQLite DB, with API key and host mode
# -------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """
    SAME as before, but we create our own MonkeyPatch instance rather
    than declaring `monkeypatch` in the signature.
    """
    mp = pytest.MonkeyPatch()
    try:
        # 1) Create a temp DB file
        db_dir = tmp_path_factory.mktemp("api_test_db")
        test_db = db_dir / "flask_test.db"

        # 2) Force LIFELOG_DB_PATH → our test_db
        mp.setenv("LIFELOG_DB_PATH", str(test_db))

        # 3) Monkey-patch cfg.load_config() and cfg.is_host_server()
        import lifelog.config.config_manager as cfg

        def fake_load_config():
            return {
                "api": {"key": "testkey"},
                "deployment": {
                    "mode": "host",
                    "server_url": "http://localhost:5000",
                    "host_server": True
                },
            }
        mp.setattr(cfg, "load_config", lambda: {
            "deployment": {"mode": "server", "server_url": "http://localhost:5000", "host_server": True},
            "api":        {"key": "testkey"}
        })

        mp.setattr(cfg, "is_host_server", lambda: True)
        # no need to patch is_direct_db_mode or is_client_mode, they derive from mode

        # 4) initialize_schema()
        from lifelog.utils.db.database_manager import initialize_schema
        initialize_schema()

        # 5) build Flask test client
        from lifelog.app import app as flask_app
        flask_app.config["TESTING"] = True
        flask_app.config["DEBUG"] = True                 # optional, but useful
        flask_app.config["PROPAGATE_EXCEPTIONS"] = True
        yield flask_app.test_client()
    finally:
        mp.undo()

    # teardown: nothing special; tmp_path is auto‐deleted


# -------------------------------------------------------------------------------------------------
# Helper: always include the API key header
# -------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def api_key_header():
    """
    Returns a dict with the correct X-API-Key header. Automatically used by tests
    if they accept `api_key_header` as an argument.
    """
    return {"X-API-Key": "testkey"}


# -------------------------------------------------------------------------------------------------
# TASK ENDPOINTS
# -------------------------------------------------------------------------------------------------

def test_create_list_get_update_delete_task(client, api_key_header):
    # 1) POST /tasks to create a new task
    task_payload = {
        "title": "API‐Created Task",
        "project": "TestProj",
        "category": "TestCat",
        "importance": 1,
        "created": "2025-06-10T12:00:00",
        "due": None,
        "status": "backlog",
        "priority": 5,
        "recur_interval": None,
        "recur_unit": None,
        "recur_days_of_week": None,
        "recur_base": None,
        "tags": "tag1,tag2",
        "notes": "This is a test",
        "uid": "api-uid-1234",
    }
    rv = client.post("/tasks/", headers=api_key_header, json=task_payload)
    assert rv.status_code == 201
    created = rv.get_json()
    assert "id" in created
    task_id = created["id"]
    assert created["title"] == "API‐Created Task"
    assert created["uid"] == "api-uid-1234"

    # 2) GET /tasks should list at least that one task
    rv2 = client.get("/tasks/?sort=priority", headers=api_key_header)
    assert rv2.status_code == 200
    tasks = rv2.get_json()
    assert any(t["id"] == task_id and t["uid"]
               == "api-uid-1234" for t in tasks)

    # 3) GET /tasks/<id> fetch single by numeric ID
    rv3 = client.get(f"/tasks/{task_id}", headers=api_key_header)
    assert rv3.status_code == 200
    single = rv3.get_json()
    assert single["title"] == "API‐Created Task"

    # 4) GET /tasks/uid/<uid> fetch single by UID
    rv4 = client.get(f"/tasks/uid/{created['uid']}", headers=api_key_header)
    assert rv4.status_code == 200
    fetched_by_uid = rv4.get_json()
    assert fetched_by_uid["id"] == task_id

    # 5) PUT /tasks/<id> to change status to "done"
    update_payload = {"status": "done"}
    rv5 = client.put(f"/tasks/{task_id}",
                     headers=api_key_header, json=update_payload)
    assert rv5.status_code == 200
    updated = rv5.get_json()
    assert updated["status"] == "done"

    # 6) PUT /tasks/uid/<uid> (host only) to change title
    rv6 = client.put(
        f"/tasks/uid/{created['uid']}", headers=api_key_header, json={"title": "Renamed Task"})
    assert rv6.status_code == 200
    updated2 = rv6.get_json()
    assert updated2["title"] == "Renamed Task"

    # 7) POST /tasks/<id>/done convenience endpoint
    rv7 = client.post(f"/tasks/{task_id}/done", headers=api_key_header)
    assert rv7.status_code == 200
    done_resp = rv7.get_json()
    assert done_resp["status"] == "success"
    assert done_resp["task"]["status"] == "done"

    # 8) DELETE /tasks/<id>
    rv8 = client.delete(f"/tasks/{task_id}", headers=api_key_header)
    # In your code, DELETE returns status 200 if successful
    assert rv8.status_code == 200
    # Confirm GET now returns 404
    rv9 = client.get(f"/tasks/{task_id}", headers=api_key_header)
    assert rv9.status_code == 404

    # 9) DELETE /tasks/uid/<uid> on a non‐existent UID should 404 or 400; but here it's host mode, so returns success if it was present
    rv10 = client.delete(
        f"/tasks/uid/{created['uid']}", headers=api_key_header)
    # Since it’s already gone, our code may return 404 or 400. Accept either.
    assert rv10.status_code in (400, 404)


def test_list_tasks_with_filters(client, api_key_header):
    # Create 2 tasks with different categories/importance
    now_iso = datetime.now().isoformat()
    t1 = {"uid": str(uuid.uuid4()), "title": "Alpha", "project": "P1", "category": "CatA",
          "importance": 2, "created": now_iso, "due": None, "status": "backlog",
          "priority": 0, "recur_interval": None, "recur_unit": None,
          "recur_days_of_week": None, "recur_base": None, "tags": None, "notes": None}
    t2 = {"uid": str(uuid.uuid4()), "title": "Beta", "project": "P2", "category": "CatB",
          "importance": 3, "created": now_iso, "due": None, "status": "done",
          "priority": 1, "recur_interval": None, "recur_unit": None,
          "recur_days_of_week": None, "recur_base": None, "tags": None, "notes": None}
    client.post("/tasks/", headers=api_key_header, json=t1)
    client.post("/tasks/", headers=api_key_header, json=t2)

    # Filter by category=CatA → should return only t1
    rv = client.get("/tasks/?category=CatA", headers=api_key_header)
    assert rv.status_code == 200
    tasks = rv.get_json()
    assert len(tasks) == 1 and tasks[0]["category"] == "CatA"

    # Filter by status=done → should return only t2
    rv2 = client.get("/tasks/?status=done", headers=api_key_header)
    tasks2 = rv2.get_json()
    assert len(tasks2) == 1 and tasks2[0]["status"] == "done"

    # Filter by importance=2 → returns t1
    rv3 = client.get("/tasks/?importance=2", headers=api_key_header)
    tasks3 = rv3.get_json()
    assert len(tasks3) == 1 and tasks3[0]["importance"] == 2


# -------------------------------------------------------------------------------------------------
# SYNC ENDPOINTS (host‐only)
# -------------------------------------------------------------------------------------------------

def test_sync_create_update_delete_tasks(client, api_key_header):
    # 1) Use POST /sync/tasks to create a new task on host
    sync_payload = {
        "operation": "create",
        "data": {
            "uid": "sync-uid-9999",
            "title": "Synced Task",
            "project": "SyncP",
            "category": "SyncC",
            "importance": 1,
            "created": "2025-06-10T12:00:00",
            "due": None,
            "status": "backlog",
            "priority": 0,
            "recur_interval": None,
            "recur_unit": None,
            "recur_days_of_week": None,
            "recur_base": None,
            "tags": None,
            "notes": None
        }
    }
    rv = client.post("/sync/tasks", headers=api_key_header, json=sync_payload)
    assert rv.status_code == 200
    resp = rv.get_json()
    assert resp["status"] == "success"

    # Confirm that GET /tasks now includes it
    rv2 = client.get("/tasks/", headers=api_key_header)
    tasks = rv2.get_json()
    assert any(t["uid"] == "sync-uid-9999" for t in tasks)

    # 2) Update via sync: change status to "done"
    sync_upd = {
        "operation": "update",
        "data": {
            "uid": "sync-uid-9999",
            "status": "done"
        }
    }
    rv3 = client.post("/sync/tasks", headers=api_key_header, json=sync_upd)
    assert rv3.status_code == 200

    # Confirm updated in GET
    rv4 = client.get("/tasks/?status=done", headers=api_key_header)
    tasks2 = rv4.get_json()
    assert any(t["uid"] == "sync-uid-9999" and t["status"]
               == "done" for t in tasks2)

    # 3) Delete via sync
    sync_del = {"operation": "delete", "data": {"uid": "sync-uid-9999"}}
    rv5 = client.post("/sync/tasks", headers=api_key_header, json=sync_del)
    assert rv5.status_code == 200

    # Confirm gone
    rv6 = client.get("/tasks/", headers=api_key_header)
    tasks3 = rv6.get_json()
    assert not any(t["uid"] == "sync-uid-9999" for t in tasks3)


# -------------------------------------------------------------------------------------------------
# TIME ENDPOINTS
# -------------------------------------------------------------------------------------------------

def test_create_list_get_stop_time_entry(client, api_key_header):
    # 1) GET /time/entries?since=<ISO> should initially return []
    rv0 = client.get("/time/entries?since=2000-01-01T00:00:00",
                     headers=api_key_header)
    assert rv0.status_code == 200
    assert rv0.get_json() == []

    # 2) POST /time/entries to start a new time log (active, end=None)
    now_iso = datetime.now().isoformat()
    time_payload = {
        "title": "API Time Test",
        "start": now_iso,
        "end": None,
        "duration_minutes": None,
        "task_id": None,
        "category": "Work",
        "project": "ProjX",
        "tags": None,
        "notes": "Starting work session",
        "uid": "time-uid-1234",
    }
    rv1 = client.post(
        "/time/entries", headers=api_key_header, json=time_payload)
    assert rv1.status_code == 201
    created = rv1.get_json()
    assert "id" in created
    time_id = created["id"]
    assert created["uid"] == "time-uid-1234"
    assert created["end"] is None

    # 3) GET /time/entries/?since=<some old timestamp> should list that active entry
    rv2 = client.get(f"/time/entries?since=2000-01-01T00:00:00",
                     headers=api_key_header)
    logs = rv2.get_json()
    assert any(log["id"] == time_id for log in logs)

    # 4) GET /time/entries/uid/<uid> to fetch by UID
    rv3 = client.get(
        f"/time/entries/uid/{created['uid']}", headers=api_key_header)
    assert rv3.status_code == 200
    single = rv3.get_json()
    assert single["id"] == time_id

    # 5) PUT /time/entries/current to stop the active time log
    stop_payload = {"end": datetime.now().isoformat(
    ), "tags": "tagA", "notes": "Stopped work"}
    rv4 = client.put("/time/entries/current",
                     headers=api_key_header, json=stop_payload)
    assert rv4.status_code == 200
    stopped = rv4.get_json()
    assert stopped["end"] is not None
    assert stopped["tags"] == "tagA"
    assert stopped["notes"] == "Stopped work"

    # Confirm that get_all now shows it as completed (with duration_minutes)
    rv5 = client.get("/time/entries", headers=api_key_header)
    logs2 = rv5.get_json()
    found = next((l for l in logs2 if l["id"] == time_id), None)
    assert found is not None
    assert found["duration_minutes"] is not None

    # 6) PUT /time/entries/<uid> to update by UID (host only)
    # Change notes again
    upd_payload = {"notes": "Updated via UID"}
    rv6 = client.put(
        f"/time/entries/{created['uid']}", headers=api_key_header, json=upd_payload)
    assert rv6.status_code == 200
    updated = rv6.get_json()
    assert updated["notes"] == "Updated via UID"

    # 7) DELETE /time/entries/<uid> to delete by UID (host only)
    rv7 = client.delete(
        f"/time/entries/{created['uid']}", headers=api_key_header)
    assert rv7.status_code == 200
    # Confirm 404 on next fetch by UID
    rv8 = client.get(
        f"/time/entries/uid/{created['uid']}", headers=api_key_header)
    assert rv8.status_code == 404


# -------------------------------------------------------------------------------------------------
# TRACKER & ENTRY & GOAL ENDPOINTS
# -------------------------------------------------------------------------------------------------

def test_tracker_crud_and_entries_and_goals(client, api_key_header):
    # TRACKER: initial GET /trackers should return []
    rv0 = client.get("/trackers/", headers=api_key_header)
    assert rv0.status_code == 200
    assert rv0.get_json() == []

    # CREATE tracker via POST /trackers
    now_iso = datetime.now().isoformat()
    tracker_payload = {
        "uid": "trk-uid-1",
        "title": "Health Tracker",
        "type": "sum",
        "category": "Wellness",
        "created": now_iso,
        "tags": "fit,health",
        "notes": "Track daily activity"
    }
    rv1 = client.post("/trackers/", headers=api_key_header,
                      json=tracker_payload)
    assert rv1.status_code == 201
    created_tr = rv1.get_json()
    assert "id" in created_tr
    tracker_id = created_tr["id"]
    assert created_tr["uid"] == "trk-uid-1"

    # GET /trackers should list 1
    rv2 = client.get("/trackers/", headers=api_key_header)
    trackers = rv2.get_json()
    assert len(trackers) == 1 and trackers[0]["id"] == tracker_id

    # GET /trackers/<id>
    rv3 = client.get(f"/trackers/{tracker_id}", headers=api_key_header)
    assert rv3.status_code == 200
    single_tr = rv3.get_json()
    assert single_tr["title"] == "Health Tracker"

    # GET /trackers/uid/<uid>
    rv4 = client.get(
        f"/trackers/uid/{created_tr['uid']}", headers=api_key_header)
    assert rv4.status_code == 200
    assert rv4.get_json()["id"] == tracker_id

    # UPDATE /trackers/<id>
    rv5 = client.put(
        f"/trackers/{tracker_id}", headers=api_key_header, json={"notes": "Updated notes"})
    assert rv5.status_code == 200
    upd_tr = rv5.get_json()
    assert upd_tr["notes"] == "Updated notes"

    # UPDATE /trackers/uid/<uid> (host only)
    rv6 = client.put(
        f"/trackers/uid/{created_tr['uid']}", headers=api_key_header, json={"category": "Fitness"})
    assert rv6.status_code == 200
    upd2 = rv6.get_json()
    assert upd2["category"] == "Fitness"

    # ADD TRACKER ENTRY: POST /trackers/<id>/entries
    entry_payload = {"timestamp": datetime.now().isoformat(), "value": 42.0}
    rv7 = client.post(f"/trackers/{tracker_id}/entries",
                      headers=api_key_header, json=entry_payload)
    assert rv7.status_code == 201
    created_entry = rv7.get_json()
    assert created_entry["tracker_id"] == tracker_id
    assert pytest.approx(created_entry["value"], rel=1e-6) == 42.0

    # LIST TRACKER ENTRIES: GET /trackers/<id>/entries
    rv8 = client.get(f"/trackers/{tracker_id}/entries", headers=api_key_header)
    entries = rv8.get_json()
    assert len(entries) == 1
    assert pytest.approx(entries[0]["value"], rel=1e-6) == 42.0

    # GOALS: initial GET /trackers/<id>/goals should return []
    rv9 = client.get(f"/trackers/{tracker_id}/goals", headers=api_key_header)
    assert rv9.status_code == 200
    assert rv9.get_json() == []

    # CREATE a SUM goal under that tracker
    goal_sum_payload = {
        "title": "Drink Water",
        "kind": "sum",
        "period": "day",
        "amount": 2000.0,
        "unit": "ml"
    }
    rv10 = client.post(
        f"/trackers/{tracker_id}/goals", headers=api_key_header, json=goal_sum_payload)
    assert rv10.status_code == 201
    created_goal = rv10.get_json()
    assert created_goal["kind"] == "sum"
    goal_uid = created_goal["uid"]

    # GET /trackers/<id>/goals should now list 1
    rv11 = client.get(f"/trackers/{tracker_id}/goals", headers=api_key_header)
    goals = rv11.get_json()
    assert len(goals) == 1 and goals[0]["uid"] == goal_uid

    # GET /trackers/goals/uid/<uid>
    rv12 = client.get(
        f"/trackers/goals/uid/{goal_uid}", headers=api_key_header)
    assert rv12.status_code == 200
    single_goal = rv12.get_json()
    assert single_goal["title"] == "Drink Water"

    # UPDATE /trackers/goals/<uid> (host only)
    upd_goal_payload = {"amount": 2500.0}
    rv13 = client.put(
        f"/trackers/goals/{goal_uid}", headers=api_key_header, json=upd_goal_payload)
    assert rv13.status_code == 200
    upd_goal = rv13.get_json()
    assert pytest.approx(upd_goal["amount"], rel=1e-6) == 2500.0

    # DELETE /trackers/goals/<uid> (host only)
    rv14 = client.delete(f"/trackers/goals/{goal_uid}", headers=api_key_header)
    assert rv14.status_code == 200

    # Confirm goal is gone
    rv15 = client.get(
        f"/trackers/goals/uid/{goal_uid}", headers=api_key_header)
    assert rv15.status_code == 404

    # DELETE /trackers/<id>
    rv16 = client.delete(f"/trackers/{tracker_id}", headers=api_key_header)
    assert rv16.status_code == 200

    # Confirm tracker is gone
    rv17 = client.get(f"/trackers/{tracker_id}", headers=api_key_header)
    assert rv17.status_code == 404


# -------------------------------------------------------------------------------------------------
# SYNC ENDPOINTS FOR TIME, TRACKERS, GOALS
# -------------------------------------------------------------------------------------------------

def test_sync_time_history(client, api_key_header):
    # Use POST /sync/time_history to create a new time entry on the host
    now_iso = datetime.now().isoformat()
    sync_payload = {
        "operation": "create",
        "data": {
            "uid": "sync-time-1",
            "title": "Synced Timer",
            "start": now_iso,
            "end": None,
            "duration_minutes": None,
            "task_id": None,
            "category": None,
            "project": None,
            "tags": None,
            "notes": None
        }
    }
    rv = client.post("/sync/time_history",
                     headers=api_key_header, json=sync_payload)
    assert rv.status_code == 200

    # Confirm GET /time/entries?since=<old> includes it
    rv2 = client.get("/time/entries?since=2000-01-01T00:00:00",
                     headers=api_key_header)
    logs = rv2.get_json()
    assert any(l["uid"] == "sync-time-1" for l in logs)

    # Update via sync (change notes)
    sync_upd = {
        "operation": "update",
        "data": {"uid": "sync-time-1", "notes": "Updated via sync"}
    }
    rv3 = client.post("/sync/time_history",
                      headers=api_key_header, json=sync_upd)
    assert rv3.status_code == 200

    # Confirm via GET /time/entries/uid/<uid>
    rv4 = client.get("/time/entries/uid/sync-time-1", headers=api_key_header)
    assert rv4.status_code == 200
    updated_log = rv4.get_json()
    assert updated_log["notes"] == "Updated via sync"

    # Delete via sync
    sync_del = {"operation": "delete", "data": {"uid": "sync-time-1"}}
    rv5 = client.post("/sync/time_history",
                      headers=api_key_header, json=sync_del)
    assert rv5.status_code == 200

    # Confirm deletion
    rv6 = client.get("/time/entries/uid/sync-time-1", headers=api_key_header)
    assert rv6.status_code == 404


def test_sync_trackers_and_goals(client, api_key_header):
    # 1) Create tracker via sync
    sync_tr_create = {
        "operation": "create",
        "data": {
            "uid": "sync-tr-1",
            "title": "Sync Tracker",
            "type": "count",
            "category": "SyncC",
            "created": datetime.now().isoformat(),
            "tags": None,
            "notes": None
        }
    }
    rv1 = client.post("/sync/trackers",
                      headers=api_key_header, json=sync_tr_create)
    assert rv1.status_code == 200

    # Confirm GET /trackers/?uid=sync-tr-1 returns it
    rv2 = client.get("/trackers/?uid=sync-tr-1", headers=api_key_header)
    trackers = rv2.get_json()
    assert len(trackers) == 1
    tr = trackers[0]
    assert tr["uid"] == "sync-tr-1"
    tracker_id = tr["id"]

    # 2) Update via sync
    sync_tr_upd = {"operation": "update", "data": {
        "uid": "sync-tr-1", "notes": "Synced note"}}
    rv3 = client.post("/sync/trackers",
                      headers=api_key_header, json=sync_tr_upd)
    assert rv3.status_code == 200

    # Confirm via GET /trackers/<id>
    rv4 = client.get(f"/trackers/{tracker_id}", headers=api_key_header)
    assert rv4.status_code == 200
    assert rv4.get_json()["notes"] == "Synced note"

    # 3) Create a GOAL under that tracker via sync
    sync_goal_create = {
        "operation": "create",
        "data": {
            "uid": "sync-goal-1",
            "tracker_id": tracker_id,
            "title": "SyncGoal",
            "kind": "sum",
            "period": "day",
            "amount": 100.0,
            "unit": "units"
        }
    }
    rv5 = client.post("/sync/goals", headers=api_key_header,
                      json=sync_goal_create)
    assert rv5.status_code == 200

    # Confirm GET /trackers/<id>/goals returns it
    rv6 = client.get(f"/trackers/{tracker_id}/goals", headers=api_key_header)
    goals = rv6.get_json()
    assert any(g["uid"] == "sync-goal-1" for g in goals)
    goal_uid = "sync-goal-1"

    # 4) Update goal via sync
    sync_goal_upd = {"operation": "update",
                     "data": {"uid": goal_uid, "amount": 150.0}}
    rv7 = client.post("/sync/goals", headers=api_key_header,
                      json=sync_goal_upd)
    assert rv7.status_code == 200

    # Confirm via GET /trackers/goals/uid/<uid>
    rv8 = client.get(f"/trackers/goals/uid/{goal_uid}", headers=api_key_header)
    assert rv8.status_code == 200
    assert pytest.approx(rv8.get_json()["amount"], rel=1e-6) == 150.0

    # 5) Delete goal via sync
    sync_goal_del = {"operation": "delete", "data": {"uid": goal_uid}}
    rv9 = client.post("/sync/goals", headers=api_key_header,
                      json=sync_goal_del)
    assert rv9.status_code == 200

    # Confirm gone
    rv10 = client.get(
        f"/trackers/goals/uid/{goal_uid}", headers=api_key_header)
    assert rv10.status_code == 404

    # 6) Delete tracker via sync
    sync_tr_del = {"operation": "delete", "data": {"uid": "sync-tr-1"}}
    rv11 = client.post(
        "/sync/trackers", headers=api_key_header, json=sync_tr_del)
    assert rv11.status_code == 200

    # Confirm tracker is gone
    rv12 = client.get(f"/trackers/{tracker_id}", headers=api_key_header)
    assert rv12.status_code == 404
