from contextlib import contextmanager
import json
import logging
import sqlite3
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Database paths
LOCAL_DB_PATH = Path.home() / ".lifelog" / "lifelog.db"
SYNC_QUEUE_PATH = Path.home() / ".lifelog" / "sync_queue.db"
logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """
    Yields an sqlite3.Connection that:
      • has PRAGMA foreign_keys=ON
      • will COMMIT on normal exit,
      • ROLLBACK on exception,
      • and ALWAYS CLOSE.
    """
    from lifelog.utils.db.database_manager import _resolve_db_path
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_mode() -> Tuple[str, str]:
    """Returns (mode, server_url)"""
    from lifelog.config.config_manager import get_deployment_mode_and_url
    return get_deployment_mode_and_url()


def is_direct_db_mode() -> bool:
    """Check if we should write directly to DB (local or host)"""
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
    from lifelog.config.config_manager import load_config
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
                logger = logging.getLogger(__name__)
                logger.info("process_sync_queue: synced %s id=%d", table, id)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                "process_sync_queue: Sync error for table %s id=%d: %s", table, id, e, exc_info=True)

    conn.close()


def auto_sync():
    logger = logging.getLogger(__name__)
    if should_sync():
        from lifelog.utils.db.task_repository import _pull_changed_tasks_from_host
        from lifelog.utils.db.time_repository import _pull_changed_time_logs_from_host
        from lifelog.utils.db.track_repository import _pull_changed_trackers_from_host, _pull_changed_goals_from_host
        # 1) Push local queued changes, then pull updates for each table:
        try:
            _pull_changed_tasks_from_host()
            logger.info("auto_sync: Pulled changed tasks from host")
        except Exception as e:
            logger.error(
                "auto_sync: Failed to pull changed tasks: %s", e, exc_info=True)
        try:
            _pull_changed_time_logs_from_host()
            logger.info("auto_sync: Pulled changed time logs from host")
        except Exception as e:
            logger.error(
                "auto_sync: Failed to pull changed time logs: %s", e, exc_info=True)
        try:
            _pull_changed_trackers_from_host()
            logger.info("auto_sync: Pulled changed trackers from host")
        except Exception as e:
            logger.error(
                "auto_sync: Failed to pull changed trackers: %s", e, exc_info=True)
        try:
            _pull_changed_goals_from_host()
            logger.info("auto_sync: Pulled changed goals from host")
        except Exception as e:
            logger.error(
                "auto_sync: Failed to pull changed goals: %s", e, exc_info=True)


def get_local_db_connection() -> sqlite3.Connection:
    """Get connection to local DB (works for all modes)"""
    return sqlite3.connect(str(LOCAL_DB_PATH))


def get_sync_queue_connection() -> sqlite3.Connection:
    """Get connection to sync queue DB"""
    return sqlite3.connect(str(SYNC_QUEUE_PATH))


def fetch_from_server(endpoint: str, params: Dict = None) -> List[Dict]:
    """Fetch data from server in client mode"""
    from lifelog.config.config_manager import load_config
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

# ───────────────────────────────────────────────────────────────────────────────
# Helpers for tracking the last‐sync timestamp per table
# ───────────────────────────────────────────────────────────────────────────────


def get_last_synced(table_name: str) -> Optional[str]:
    """
    Return the ISO‐8601 timestamp (string) for when we last synced `table_name`.
    If no entry exists, returns None.
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT last_synced_at FROM sync_state WHERE table_name = ?", (table_name,))
        row = cur.fetchone()
        conn.close()
        return row["last_synced_at"] if row else None


def set_last_synced(table_name: str, iso_ts: str) -> None:
    """
    Upsert `sync_state(table_name, last_synced_at = iso_ts)`.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Try an update first
    cur.execute(
        "UPDATE sync_state SET last_synced_at = ? WHERE table_name = ?",
        (iso_ts, table_name)
    )
    if cur.rowcount == 0:
        # no existing row → insert
        cur.execute(
            "INSERT INTO sync_state (table_name, last_synced_at) VALUES (?, ?)",
            (table_name, iso_ts)
        )
    conn.commit()
    conn.close()


def safe_execute(
    sql: str,
    params: Tuple[Any, ...] = (),
    retries: int = 5,
    backoff: float = 0.1
) -> sqlite3.Cursor:
    """
    Execute a write operation with retry on OperationalError.
    Commits on success (via get_connection), rolls back on exception.
    Returns the cursor so you can inspect lastrowid, rowcount, etc.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql, params)
                return cur
        except sqlite3.OperationalError as e:
            last_exc = e
            logger.warning(
                "safe_execute: DB locked, attempt %d/%d: %s",
                attempt, retries, e, exc_info=False
            )
            time.sleep(backoff * attempt)
        except sqlite3.DatabaseError as e:
            logger.error(
                "safe_execute: unrecoverable DB error: %s", e, exc_info=True)
            raise
    logger.error(
        "safe_execute: failed after %d retries, last error: %s",
        retries, last_exc, exc_info=True
    )
    raise last_exc  # type: ignore


def safe_query(
    sql: str,
    params: Tuple[Any, ...] = (),
    retries: int = 5,
    backoff: float = 0.1
) -> List[sqlite3.Row]:
    """
    Execute a read operation with retry on OperationalError.
    Returns a list of sqlite3.Row (cursor.fetchall()).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(sql, params)
                return cur.fetchall()
        except sqlite3.OperationalError as e:
            last_exc = e
            logger.warning(
                "safe_query: DB locked, attempt %d/%d: %s",
                attempt, retries, e, exc_info=False
            )
            time.sleep(backoff * attempt)
        except sqlite3.DatabaseError as e:
            logger.error("safe_query: unrecoverable DB error: %s",
                         e, exc_info=True)
            raise
    logger.error(
        "safe_query: failed after %d retries, last error: %s",
        retries, last_exc, exc_info=True
    )
    raise last_exc
