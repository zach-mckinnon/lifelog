import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from lifelog.config.config_manager import get_config, get_deployment_mode_and_url

# Database paths
LOCAL_DB_PATH = Path.home() / ".lifelog" / "lifelog.db"
SYNC_QUEUE_PATH = Path.home() / ".lifelog" / "sync_queue.db"


def get_deployment_mode() -> str:
    """Returns current deployment mode: 'local', 'server', or 'client'"""
    mode, _ = get_deployment_mode_and_url()
    return mode


def is_direct_db_mode() -> bool:
    """Check if we should write directly to DB"""
    return get_deployment_mode() in ['local', 'server']


def should_sync() -> bool:
    """Check if we need to sync with host"""
    return get_deployment_mode() == 'client'


def direct_db_execute(query: str, params: tuple = ()) -> sqlite3.Cursor:
    """Execute SQL directly on local DB (for local/server modes)"""
    if not is_direct_db_mode():
        raise RuntimeError("Direct DB access not allowed in client mode")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    return cursor


def queue_sync_operation(table: str, operation: str, data: Dict[str, Any]):
    """Queue sync operation for client mode"""
    if not should_sync():
        return

    conn = sqlite3.connect(SYNC_QUEUE_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sync_queue "
        "(id INTEGER PRIMARY KEY, table_name TEXT, operation TEXT, data TEXT, created_at TEXT)"
    )

    conn.execute(
        "INSERT INTO sync_queue (table_name, operation, data, created_at) VALUES (?, ?, ?, ?)",
        (table, operation, json.dumps(data), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def process_sync_queue():
    """Process queued sync operations (for client mode)"""
    if not should_sync():
        return

    _, server_url = get_deployment_mode_and_url()
    conn = sqlite3.connect(SYNC_QUEUE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sync_queue ORDER BY created_at ASC")
    queue = cursor.fetchall()

    for item in queue:
        id, table, operation, data, created_at = item
        try:
            # Send to host server
            response = requests.post(
                f"{server_url}/sync/{table}",
                json={
                    'operation': operation,
                    'data': json.loads(data)
                },
                headers={'X-API-Key': get_config()['api']['key']}
            )

            if response.status_code == 200:
                # Remove successful sync
                conn.execute("DELETE FROM sync_queue WHERE id = ?", (id,))
                conn.commit()
        except Exception:
            # Retry later
            pass

    conn.close()

# Example usage in repositories:


def create_task(task_data: Dict) -> Dict:
    if is_direct_db_mode():
        # Direct write to DB
        cursor = direct_db_execute(
            "INSERT INTO tasks (...) VALUES (...) RETURNING *",
            (task_data.values())
        )
        return cursor.fetchone()
    else:
        # Client mode: write to local cache and queue sync
        local_cursor = direct_db_execute(
            "INSERT INTO tasks (...) VALUES (...) RETURNING *",
            (task_data.values())
        )
        result = local_cursor.fetchone()

        # Queue sync operation
        queue_sync_operation('tasks', 'create', task_data)
        return result


def update_task(task_id: int, updates: Dict):
    if is_direct_db_mode():
        # Direct update
        direct_db_execute(
            "UPDATE tasks SET ... WHERE id = ?",
            (updates.values(), task_id)
        )
    else:
        # Client mode: local update + queue sync
        direct_db_execute(
            "UPDATE tasks SET ... WHERE id = ?",
            (updates.values(), task_id)
        )
        queue_sync_operation('tasks', 'update', {'id': task_id, **updates})
