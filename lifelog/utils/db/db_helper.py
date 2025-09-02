from lifelog.config.config_manager import (
    get_deployment_mode_and_url,
    load_config,
)
from datetime import datetime, timezone
from enum import Enum
from contextlib import contextmanager
import json
import logging
import sqlite3
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lifelog.config.config_manager import load_config


def _to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC-aware datetime.
    - If dt is naïve, interpret it as UTC.
    - If dt is aware, convert from its tzinfo to UTC.
    Returns a datetime with tzinfo=datetime.timezone.utc.
    """
    if dt.tzinfo is None:
        # Interpret naïve dt as UTC to avoid circular import
        dt = dt.replace(tzinfo=timezone.utc)
    # Convert to UTC
    return dt.astimezone(timezone.utc)


# Database paths
LOCAL_DB_PATH = Path.home() / ".lifelog" / "lifelog.db"
SYNC_QUEUE_PATH = Path.home() / ".lifelog" / "sync_queue.db"
logger = logging.getLogger(__name__)


# lifelog/utils/db/db_helper.py


logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────────────
# Database file paths
# ───────────────────────────────────────────────────────────────────────────────

LOCAL_DB_PATH = Path.home() / ".lifelog" / "lifelog.db"
SYNC_QUEUE_PATH = Path.home() / ".lifelog" / "sync_queue.db"

# ───────────────────────────────────────────────────────────────────────────────
# Core Connection Context Manager
# ───────────────────────────────────────────────────────────────────────────────


@contextmanager
def get_connection():
    """
    Yields an sqlite3.Connection optimized for Raspberry Pi:
      • has PRAGMA foreign_keys=ON
      • Dynamically optimized PRAGMA settings based on Pi hardware
      • will COMMIT on normal exit,
      • ROLLBACK on exception,
      • and ALWAYS CLOSE.
    """
    from lifelog.utils.db import _resolve_db_path
    from lifelog.utils.pi_optimizer import pi_optimizer
    
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect with Pi-optimized timeout
    settings = pi_optimizer.get_optimized_settings()
    timeout = settings["performance"]["connection_timeout"]
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    
    # Apply Pi-optimized SQLite settings
    pi_optimizer.optimize_connection_settings(conn)

    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────────
# Deployment Mode Helpers
# ───────────────────────────────────────────────────────────────────────────────


def get_mode() -> Tuple[str, str]:
    """
    Returns (mode, server_url) from config:
      • mode in ['local','server','client']
      • server_url for sync endpoints
    """
    return get_deployment_mode_and_url()


def is_direct_db_mode() -> bool:
    """True if we can write directly (local or server mode)."""
    mode, _ = get_mode()
    return mode in ("local", "server")


def should_sync() -> bool:
    """True if we’re in client mode and should queue/push to host."""
    mode, _ = get_mode()
    return mode == "client"

# ───────────────────────────────────────────────────────────────────────────────
# Direct‐DB Access (bypasses sync queue)
# ───────────────────────────────────────────────────────────────────────────────


def direct_db_execute(query: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
    """
    Execute SQL on local DB immediately (only in local/server mode).
    Uses proper connection management for Raspberry Pi reliability.
    """
    if not is_direct_db_mode():
        raise RuntimeError("Direct DB access not allowed in client mode")
    
    try:
        # Use context manager for proper connection handling
        with sqlite3.connect(str(LOCAL_DB_PATH), timeout=30.0) as conn:
            # Configure SQLite for better Pi performance
            conn.execute("PRAGMA journal_mode=WAL")  # Better for concurrent access
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance between performance and safety
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor
    except sqlite3.OperationalError as e:
        logger.error(f"Database operation failed (may be locked or corrupted): {e}")
        raise
    except sqlite3.Error as e:
        logger.error(f"Database error in direct_db_execute: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in direct_db_execute: {e}")
        raise

# ───────────────────────────────────────────────────────────────────────────────
# Data Normalization
# ───────────────────────────────────────────────────────────────────────────────


def normalize_for_db(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert any Enum to .value, any datetime to UTC ISO string.
    """
    for k, v in list(d.items()):
        if isinstance(v, Enum):
            d[k] = v.value
        elif isinstance(v, datetime):
            d[k] = _to_utc(v).isoformat()
    return d

# ───────────────────────────────────────────────────────────────────────────────
# Sync Queue Helpers
# ───────────────────────────────────────────────────────────────────────────────


def get_sync_queue_connection() -> sqlite3.Connection:
    """Low‐level connection to the sync‐queue DB (no foreign keys)."""
    SYNC_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(SYNC_QUEUE_PATH))


def queue_sync_operation(table: str, operation: str, data: Dict[str, Any]) -> None:
    """
    In client mode, queue an operation (INSERT/UPDATE/DELETE) for later push.
    """
    if not should_sync():
        return

    with get_sync_queue_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
              id          INTEGER PRIMARY KEY,
              table_name  TEXT,
              operation   TEXT,
              data        TEXT,
              created_at  TEXT
            )
        """)
        conn.execute(
            "INSERT INTO sync_queue (table_name, operation, data, created_at) VALUES (?, ?, ?, ?)",
            (table, operation, json.dumps(data),
             datetime.now(timezone.utc).isoformat())
        )


def process_sync_queue() -> None:
    """
    Attempt to push queued operations to the host one‐by‐one, deleting on success.
    """
    if not should_sync():
        return

    mode, server_url = get_mode()
    api_key = load_config().get("api", {}).get("key", "")
    if not api_key:
        return

    conn = get_sync_queue_connection()
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sync_queue ORDER BY created_at ASC")
        for row in cursor.fetchall():
            try:
                resp = requests.post(
                    f"{server_url}/sync/{row['table_name']}",
                    json={"operation": row["operation"],
                          "data": json.loads(row["data"])},
                    headers={"X-API-Key": api_key},
                    timeout=10
                )
                if resp.status_code == 200:
                    conn.execute(
                        "DELETE FROM sync_queue WHERE id = ?", (row["id"],))
                    conn.commit()
                    logger.info("Synced %s id=%d",
                                row["table_name"], row["id"])
            except Exception:
                logger.exception("Error syncing %s id=%d",
                                 row["table_name"], row["id"])
    finally:
        conn.close()


def auto_sync() -> None:
    """
    High‐level sync: push queue, then pull fresh rows for all tracked tables.
    """
    if not should_sync():
        return

    from lifelog.utils.db.task_repository import _pull_changed_tasks_from_host
    from lifelog.utils.db.time_repository import _pull_changed_time_logs_from_host
    from lifelog.utils.db.track_repository import (_pull_changed_trackers_from_host,
                                                   _pull_changed_goals_from_host)

    for fn in (_pull_changed_tasks_from_host,
               _pull_changed_time_logs_from_host,
               _pull_changed_trackers_from_host,
               _pull_changed_goals_from_host):
        try:
            fn()
            logger.info("auto_sync: %s succeeded", fn.__name__)
        except Exception:
            logger.exception("auto_sync: %s failed", fn.__name__)

# ───────────────────────────────────────────────────────────────────────────────
# Server Fetch Helper
# ───────────────────────────────────────────────────────────────────────────────


def fetch_from_server(endpoint: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    In client mode, GET data from the host at /<endpoint>?… 
    Returns a list of JSON objects.
    """
    if not should_sync():
        return []

    _, server_url = get_mode()
    api_key = load_config().get("api", {}).get("key", "")
    if not api_key:
        return []

    try:
        resp = requests.get(f"{server_url}/{endpoint}", params=params,
                            headers={"X-API-Key": api_key}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("fetch_from_server error: %s", e)
        return []

# ───────────────────────────────────────────────────────────────────────────────
# Last‐Sync State Helpers
# ───────────────────────────────────────────────────────────────────────────────


def get_last_synced(table_name: str) -> Optional[str]:
    """
    Returns the ISO timestamp of last sync for `table_name`,
    reading from a `sync_state` table.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_synced_at FROM sync_state WHERE table_name = ?",
            (table_name,)
        ).fetchone()
    return row["last_synced_at"] if row else None


def set_last_synced(table_name: str, iso_ts: str) -> None:
    """
    Upsert the last sync timestamp for `table_name` in `sync_state`.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE sync_state SET last_synced_at = ? WHERE table_name = ?",
            (iso_ts, table_name)
        )
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO sync_state (table_name, last_synced_at) VALUES (?, ?)",
                (table_name, iso_ts)
            )

# ───────────────────────────────────────────────────────────────────────────────
# Safe Execute / Query with Retries
# ───────────────────────────────────────────────────────────────────────────────


def safe_execute(
    sql: str,
    params: Tuple[Any, ...] = (),
    retries: int = 5,
    backoff: float = 0.1
) -> sqlite3.Cursor:
    """
    Execute a write with retry on OperationalError (e.g. SQLITE_BUSY).
    Commits via get_connection, rolls back on exception.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with get_connection() as conn:
                cur = conn.execute(sql, params)
                return cur
        except sqlite3.OperationalError as e:
            last_exc = e
            logger.warning(
                "safe_execute attempt %d/%d failed: %s", attempt, retries, e)
            time.sleep(backoff * attempt)
        except sqlite3.DatabaseError as e:
            logger.exception("safe_execute unrecoverable DB error")
            raise
    logger.error("safe_execute failed after %d retries", retries)
    raise last_exc  # type: ignore


def safe_query(
    sql: str,
    params: Tuple[Any, ...] = (),
    retries: int = 5,
    backoff: float = 0.1
) -> List[sqlite3.Row]:
    """
    Execute a read with retry on OperationalError.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with get_connection() as conn:
                cur = conn.execute(sql, params)
                return cur.fetchall()
        except sqlite3.OperationalError as e:
            last_exc = e
            logger.warning("safe_query attempt %d/%d failed: %s",
                           attempt, retries, e)
            time.sleep(backoff * attempt)
        except sqlite3.DatabaseError as e:
            logger.exception("safe_query unrecoverable DB error")
            raise
    logger.error("safe_query failed after %d retries", retries)
    raise last_exc  # type: ignore
