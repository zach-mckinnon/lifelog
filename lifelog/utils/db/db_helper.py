import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from lifelog.config.config_manager import get_deployment_mode_and_url, get_config, load_config

# Database paths
LOCAL_DB_PATH = Path.home() / ".lifelog" / "lifelog.db"
SYNC_QUEUE_PATH = Path.home() / ".lifelog" / "sync_queue.db"


def get_mode() -> Tuple[str, str]:
    """Returns (mode, server_url)"""
    return get_deployment_mode_and_url()


def is_direct_db_mode() -> bool:
    """Check if we should write directly to DB (standalone or host)"""
    mode, _ = get_mode()
    return mode in ['local', 'server']


def should_sync() -> bool:
    """Check if we need to sync with host (client mode)"""
    mode, _ = get_mode()
    return mode == 'client'


def direct_db_execute(query: str, params: tuple = ()) -> sqlite3.Cursor:
    """Execute SQL directly on local DB (for local/server modes)"""
    if not is_direct_db_mode():
        raise RuntimeError("Direct DB access not allowed in client mode")

    conn = sqlite3.connect(str(LOCAL_DB_PATH))
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    return cursor


def queue_sync_operation(table: str, operation: str, data: Dict[str, Any]):
    """Queue sync operation for client mode"""
    if not should_sync():
        return

    conn = sqlite3.connect(str(SYNC_QUEUE_PATH))
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

    _, server_url = get_mode()
    config = load_config()
    api_key = config.get('api', {}).get('key', '')

    if not api_key:
        return

    conn = sqlite3.connect(str(SYNC_QUEUE_PATH))
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
                headers={'X-API-Key': api_key}
            )

            if response.status_code == 200:
                # Remove successful sync
                conn.execute("DELETE FROM sync_queue WHERE id = ?", (id,))
                conn.commit()
        except Exception as e:
            # Log error and retry later
            print(f"Sync error: {e}")

    conn.close()


def auto_sync():
    if should_sync():
        process_sync_queue()


def get_local_db_connection() -> sqlite3.Connection:
    """Get connection to local DB (works for all modes)"""
    return sqlite3.connect(str(LOCAL_DB_PATH))


def get_sync_queue_connection() -> sqlite3.Connection:
    """Get connection to sync queue DB"""
    return sqlite3.connect(str(SYNC_QUEUE_PATH))


def fetch_from_server(endpoint: str, params: Dict = None) -> List[Dict]:
    """Fetch data from server in client mode"""
    if not should_sync():
        return []

    _, server_url = get_mode()
    config = load_config()
    api_key = config.get('api', {}).get('key', '')

    if not api_key:
        return []

    try:
        response = requests.get(
            f"{server_url}/{endpoint}",
            params=params,
            headers={'X-API-Key': api_key}
        )

        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Fetch error: {e}")

    return []
