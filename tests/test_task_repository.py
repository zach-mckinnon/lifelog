import pytest
import uuid
from datetime import datetime

# Adjust these imports to match your project structure:
from lifelog.utils.db.task_repository import (
    add_task,
    get_task_by_id,
    update_task,
    delete_task,
    upsert_local_task,
    query_tasks,
    get_all_tasks,
)
from lifelog.utils.db.models import Task
from lifelog.utils.db.db_helper import should_sync
from lifelog.utils.db.db_helper import fetch_from_server, get_last_synced, set_last_synced, process_sync_queue

# A helper to build a minimal valid Task‐payload dict


def make_dummy_task_dict():
    return {
        "uid": str(uuid.uuid4()),
        "title": "Test Task",
        "project": "ProjA",
        "category": "CatA",
        "importance": 2,
        "created": datetime.now().isoformat(),
        "due": None,
        "status": "backlog",
        "priority": 0,
        "recur_interval": None,
        "recur_unit": None,
        "recur_days_of_week": None,
        "recur_base": None,
        "tags": None,
        "notes": None,
    }


@pytest.fixture(autouse=True)
def disable_sync(monkeypatch):
    """
    By default, pretend we're in direct/host mode so that sync‐paths are skipped.
    Tests which need client‐mode can override this.
    """
    monkeypatch.setattr(
        "lifelog.utils.db.db_helper.should_sync", lambda: False)
    yield


def test_add_and_get_task_direct_mode(test_db_file, clean_tables):
    """
    add_task(...) with a Task instance should insert a row, and get_task_by_id(1) should return it.
    """
    data = make_dummy_task_dict()
    t = Task(**data)
    inserted = add_task(t)
    # The first inserted row will have numeric ID = 1
    fetched = get_task_by_id(1)
    assert fetched is not None
    assert fetched.title == data["title"]
    assert fetched.uid == data["uid"]


def test_update_task_direct_mode(test_db_file, clean_tables):
    """
    After inserting, update_task(...) should change the status field.
    """
    d = make_dummy_task_dict()
    add_task(d)
    task = get_task_by_id(1)
    # Update status to "done"
    update_task(task.id, {"status": "done"})
    updated = get_task_by_id(task.id)
    assert updated.status == "done"


def test_delete_task_direct_mode(test_db_file, clean_tables):
    """
    add_task(...) then delete_task(...) should make get_task_by_id return None.
    """
    d = make_dummy_task_dict()
    add_task(d)
    t = get_task_by_id(1)
    assert t is not None
    delete_task(t.id)
    assert get_task_by_id(t.id) is None


def test_upsert_local_task_inserts_and_updates(test_db_file, clean_tables):
    """
    upsert_local_task(...) with a remote payload should insert if new,
    then update if the same UID but different fields.
    """
    # Initially, DB is empty
    remote = make_dummy_task_dict()
    # This should insert a new row
    upsert_local_task(remote)

    all_tasks = query_tasks()
    assert len(all_tasks) == 1
    assert all_tasks[0].uid == remote["uid"]
    assert all_tasks[0].status == "backlog"

    # Now modify the "status" in the payload and upsert again
    remote2 = remote.copy()
    remote2["status"] = "done"
    upsert_local_task(remote2)

    tasks2 = query_tasks()
    assert len(tasks2) == 1
    assert tasks2[0].status == "done"


def test_query_tasks_filters_and_sort(test_db_file, clean_tables):
    """
    Create three tasks with different due dates. query_tasks(...) without filters
    returns all. Filtering by title_contains works.
    """
    now = datetime.now().isoformat()
    older = {
        **make_dummy_task_dict(),
        "uid": str(uuid.uuid4()),
        "title": "Older Task",
        "due": "2020-01-01T00:00:00",
    }
    middle = {
        **make_dummy_task_dict(),
        "uid": str(uuid.uuid4()),
        "title": "Middle Task",
        "due": "2023-01-01T00:00:00",
    }
    future = {
        **make_dummy_task_dict(),
        "uid": str(uuid.uuid4()),
        "title": "Future Task",
        "due": "2025-01-01T00:00:00",
    }

    # Use upsert_local to bypass add_task's "direct_db_mode" logic
    upsert_local_task(older)
    upsert_local_task(middle)
    upsert_local_task(future)

    all_tasks = query_tasks()
    titles = {t.title for t in all_tasks}
    assert titles == {"Older Task", "Middle Task", "Future Task"}

    # Filter by title_contains
    filtered = query_tasks(title_contains="Middle")
    assert len(filtered) == 1
    assert filtered[0].title == "Middle Task"


def test_get_all_tasks_client_mode_pulls_remote(test_db_file, clean_tables, monkeypatch):
    """
    Simulate client mode. get_all_tasks() should call _pull_changed_tasks_from_host(),
    which in turn calls fetch_from_server(...) with since=... and upserts returned rows.
    """
    # Pretend we're in client mode
    monkeypatch.setattr("lifelog.utils.db.db_helper.should_sync", lambda: True)

    # Make fetch_from_server return two dummy payloads
    dummy1 = make_dummy_task_dict()
    dummy2 = make_dummy_task_dict()
    monkeypatch.setattr(
        "lifelog.utils.db.task_repository.fetch_from_server",
        lambda *args, **kwargs: [dummy1, dummy2]
    )
    # Pretend no previous synced timestamp
    monkeypatch.setattr(
        "lifelog.utils.db.task_repository.get_last_synced",
        lambda table: None
    )
    # Spy on set_last_synced so it doesn’t blow up
    monkeypatch.setattr(
        "lifelog.utils.db.task_repository.set_last_synced",
        lambda table, ts: None
    )

    tasks = get_all_tasks()
    # After pull, local DB should contain exactly two tasks
    assert len(tasks) == 2
    uids = {t.uid for t in tasks}
    assert uids == {dummy1["uid"], dummy2["uid"]}

    # If we call get_all_tasks again, fetch_from_server still returns the same,
    # but because get_last_synced() returns None in our stub, we get duplicates.
    # (In real code, set_last_synced would prevent that.)
    tasks2 = get_all_tasks()
    assert len(tasks2) == 4  # duplicates if last_synced never updated


@pytest.mark.parametrize("update_fields", [
    ({"title": "New Title"}),
    ({"project": "NewProj", "status": "active"}),
])
def test_update_task_client_mode_queues_and_upserts(test_db_file, clean_tables, monkeypatch, update_fields):
    """
    Simulate client mode: update_task(...) should update local row, 
    then queue a sync operation with full payload.
    """
    # Insert one row in direct mode
    d = make_dummy_task_dict()
    add_task(d)
    original = get_task_by_id(1)

    # Switch to client mode
    monkeypatch.setattr("lifelog.utils.db.db_helper.should_sync", lambda: True)

    queued = []
    # Capture calls to queue_sync_operation in task_repository
    monkeypatch.setattr(
        "lifelog.utils.db.task_repository.queue_sync_operation",
        lambda table, op, data: queued.append((table, op, data))
    )
    # Stub out process_sync_queue so it’s a no-op
    monkeypatch.setattr(
        "lifelog.utils.db.task_repository.process_sync_queue", lambda: None)

    # Perform update
    update_task(original.id, update_fields)
    # There should be one queued update
    assert len(queued) == 1
    table_name, operation, payload = queued[0]
    assert table_name == "tasks"
    assert operation == "update"
    # Payload must include the "uid" key (full payload read from DB)
    assert "uid" in payload

    # Check local row was updated
    now_local = get_task_by_id(original.id)
    for k, v in update_fields.items():
        assert getattr(now_local, k) == v
