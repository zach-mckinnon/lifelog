import os
import uuid
from lifelog.config.config_manager import BASE_DIR
import sqlite3
from pathlib import Path

from lifelog.utils.db import get_connection


# _ENV_DB = os.getenv("LIFELOG_DB_PATH", "").strip()
# if _ENV_DB:
#     DB_PATH = Path(_ENV_DB).expanduser().resolve()
# else:
#     DB_PATH = BASE_DIR / "lifelog.db"

class DBConnection:
    def __enter__(self):
        self._cm = get_connection()
        self.conn = self._cm.__enter__()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._cm.__exit__(exc_type, exc_val, exc_tb)


def _resolve_db_path():
    # Always read the latest env var at call time
    env_db = os.getenv("LIFELOG_DB_PATH", "").strip()
    if env_db:
        return Path(env_db).expanduser().resolve()
    return BASE_DIR / "lifelog.db"


def is_initialized() -> bool:
    """Check if database exists and has tables"""
    db_path = _resolve_db_path()
    if not db_path.exists():
        return False

    try:
        # Open a connection
        from lifelog.utils.db import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            conn.close()
        return len(tables) > 0
    except sqlite3.Error:
        return False


def initialize_schema():
    """
    Create all tables, indexes and do a simple test query.
    Uses get_connection() as a context‐manager, which:
      • commits on normal exit,
      • rolls back on exception,
      • and always closes.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # ───────────────────────────────────────────────────────────────────────────
            # Core tables
            # ───────────────────────────────────────────────────────────────────────────
            cursor.executescript("""
            CREATE TABLE IF NOT EXISTS trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                title TEXT,
                type TEXT,
                category TEXT,
                created DATETIME,
                notes TEXT,
                tags TEXT,
                updated_at TEXT,
                deleted INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                title TEXT,
                project TEXT,
                category TEXT,
                importance INTEGER,
                created DATETIME,
                due DATETIME,
                status TEXT,
                start DATETIME,
                end DATETIME,
                priority FLOAT,
                recur_interval INTEGER,
                recur_unit TEXT,
                recur_days_of_week TEXT,
                recur_base DATETIME,
                notes TEXT,
                tags TEXT,
                updated_at TEXT,
                deleted INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                tracker_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                period TEXT DEFAULT 'day',
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_sum (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                amount REAL NOT NULL,
                unit TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_count (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                amount INTEGER NOT NULL,
                unit TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_bool (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_streak (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                target_streak INTEGER NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_duration (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                amount REAL NOT NULL,
                unit TEXT DEFAULT 'minutes',
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_milestone (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                target REAL NOT NULL,
                unit TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_reduction (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                amount REAL NOT NULL,
                unit TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_range (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                min_amount REAL NOT NULL,
                max_amount REAL NOT NULL,
                unit TEXT,
                mode TEXT CHECK (mode IN ('goal','tracker')) DEFAULT 'goal',
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_percentage (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                target_percentage REAL NOT NULL,
                current_percentage REAL DEFAULT 0,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_replacement (
                goal_id INTEGER PRIMARY KEY,
                uid TEXT UNIQUE,
                old_behavior TEXT NOT NULL,
                new_behavior TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                task_id INTEGER,
                start DATETIME,
                end DATETIME,
                duration_minutes FLOAT,
                tags TEXT,
                notes TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );

            CREATE TABLE IF NOT EXISTS tracker_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                tracker_id INTEGER,
                timestamp DATETIME,
                value FLOAT,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS time_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE,
                title TEXT NOT NULL,
                start DATETIME NOT NULL,
                end DATETIME,
                duration_minutes FLOAT,
                task_id INTEGER,
                category TEXT,
                project TEXT,
                tags TEXT,
                notes TEXT,
                distracted_minutes FLOAT DEFAULT 0,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                updated_at TEXT,
                deleted INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS environment_data (
                uid TEXT UNIQUE,
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                weather TEXT,
                air_quality TEXT,
                moon TEXT,
                satellite TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_quote (
                date DATE PRIMARY KEY,
                quote TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback_sayings (
                context TEXT PRIMARY KEY,
                sayings JSON NOT NULL
            );

            CREATE TABLE IF NOT EXISTS first_command_flags (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                uid TEXT UNIQUE,
                last_executed DATE
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                table_name TEXT PRIMARY KEY,
                last_synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS api_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT,
                device_token TEXT UNIQUE NOT NULL,
                paired_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS api_pairing_codes (
                code TEXT PRIMARY KEY,
                expires_at DATETIME,
                device_name TEXT
            );
            
            CREATE TABLE IF NOT EXISTS user_profiles (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                uid            TEXT    UNIQUE,
                xp             INTEGER NOT NULL DEFAULT 0,
                level          INTEGER NOT NULL DEFAULT 1,
                gold           INTEGER NOT NULL DEFAULT 0,
                created_at     DATETIME,
                last_level_up  DATETIME
            );

            CREATE TABLE IF NOT EXISTS badges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uid         TEXT    UNIQUE,
                name        TEXT    NOT NULL,
                description TEXT,
                icon        TEXT     -- e.g. emoji or path
            );

            CREATE TABLE IF NOT EXISTS profile_badges (
                profile_id  INTEGER,
                badge_id    INTEGER,
                awarded_at  DATETIME,
                PRIMARY KEY (profile_id, badge_id),
                FOREIGN KEY (profile_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (badge_id)   REFERENCES badges(id)        ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS skills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uid         TEXT    UNIQUE,
                name        TEXT    NOT NULL,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS profile_skills (
                profile_id  INTEGER,
                skill_id    INTEGER,
                level       INTEGER NOT NULL DEFAULT 1,
                xp          INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (profile_id, skill_id),
                FOREIGN KEY (profile_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (skill_id)   REFERENCES skills(id)        ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shop_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uid         TEXT    UNIQUE,
                name        TEXT    NOT NULL,
                description TEXT,
                cost_gold   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS inventory (
                profile_id  INTEGER,
                item_id     INTEGER,
                quantity    INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (profile_id, item_id),
                FOREIGN KEY (profile_id) REFERENCES user_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (item_id)    REFERENCES shop_items(id)     ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS notifications (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id    INTEGER NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
                message       TEXT      NOT NULL,
                created_at    TEXT      NOT NULL,            -- ISO timestamp
                read          INTEGER   NOT NULL DEFAULT 0   -- 0 = unread, 1 = read
                );
            """)

            # ───────────────────────────────────────────────────────────────────────
            # Indexes
            # ───────────────────────────────────────────────────────────────────────
            cursor.executescript("""
            CREATE INDEX IF NOT EXISTS idx_tracker_entries_tracker_id ON tracker_entries(tracker_id);
            CREATE INDEX IF NOT EXISTS idx_time_history_task_id ON time_history(task_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);
            CREATE INDEX IF NOT EXISTS idx_goals_tracker_id ON goals(tracker_id);
            """)

            # simple test query
            cursor.execute("SELECT COUNT(*) FROM feedback_sayings")
            # all done; on exiting the with-block, commit & close happen automatically

    except sqlite3.Error as e:
        # any error inside 'with' has already been rolled back
        print(f"Schema initialization error: {e}")


def add_record(table, data, fields):
    with get_connection() as conn:
        cursor = conn.cursor()
        if "uid" in fields and not data.get("uid"):
            data["uid"] = str(uuid.uuid4())
        cols = ', '.join(fields)
        ph = ', '.join('?' for _ in fields)
        vals = [data[f] for f in fields]
        cursor.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", vals)
        new_id = cursor.lastrowid
        # no conn.commit() or conn.close() here—handled by the contextmanager
    return new_id


def update_record(table, record_id, updates):
    """
    Update a single row in `table` by its numeric primary key `id`.
    `updates` is a dict mapping column names to new values.
    """
    # 1) Build the SET clause and values list
    fields = [f"{col} = ?" for col in updates.keys()]
    values = list(updates.values())
    values.append(record_id)

    sql = f"UPDATE {table} SET {', '.join(fields)} WHERE id = ?"

    # 2) Execute inside the connection context (auto-commit & close)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, values)


def get_all_api_devices():
    with get_connection() as conn:
        cursor = conn.cursor()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT device_name, device_token, paired_at
        FROM api_devices
        ORDER BY paired_at DESC
    """)
    devices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return devices
