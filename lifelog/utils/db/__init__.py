# lifelog/utils/db/__init__.py

"""
Database connection, schema initialization, and repository APIs.
"""

# ─── Core connection & sync helpers ─────────────────────────────────────────────
from lifelog.utils.db.db_helper import (
    get_connection,
    get_mode,
    is_direct_db_mode,
    should_sync,
    direct_db_execute,
    normalize_for_db,
    get_sync_queue_connection,
    queue_sync_operation,
    process_sync_queue,
    auto_sync,
    fetch_from_server,
    get_last_synced,
    set_last_synced,
    safe_execute,
    safe_query,
)

# ─── Schema management ───────────────────────────────────────────────────────────
from lifelog.utils.db.database_manager import (
    DBConnection,
    is_initialized,
    initialize_schema,
    add_record,
    update_record
)

# ─── Data models ────────────────────────────────────────────────────────────────
from lifelog.utils.db import models

# ─── Repository sub-modules ─────────────────────────────────────────────────────
from lifelog.utils.db import (
    environment_repository,
    gamify_repository,
    report_repository,
    task_repository,
    time_repository,
    track_repository,
)

# ─── Public API ─────────────────────────────────────────────────────────────────
__all__ = [
    # connection & sync
    "get_connection",
    "get_mode",
    "is_direct_db_mode",
    "should_sync",
    "direct_db_execute",
    "normalize_for_db",
    "get_sync_queue_connection",
    "queue_sync_operation",
    "process_sync_queue",
    "auto_sync",
    "fetch_from_server",
    "get_last_synced",
    "set_last_synced",
    "safe_execute",
    "safe_query",
    "add_record",
    "update_record",
    # schema
    "DBConnection",
    "is_initialized",
    "initialize_schema",
    # models & repositories
    "models",
    "environment_repository",
    "gamify_repository",
    "report_repository",
    "task_repository",
    "time_repository",
    "track_repository",
]
