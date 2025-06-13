import os
import uuid
from lifelog.config.config_manager import BASE_DIR
import sqlite3
from pathlib import Path


# _ENV_DB = os.getenv("LIFELOG_DB_PATH", "").strip()
# if _ENV_DB:
#     DB_PATH = Path(_ENV_DB).expanduser().resolve()
# else:
#     DB_PATH = BASE_DIR / "lifelog.db"


class DBConnection:
    def __enter__(self):
        from lifelog.utils.db.db_helper import get_connection
        self.conn = get_connection()
        return self.conn.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.commit()
        self.conn.close()


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
        from lifelog.utils.db.db_helper import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            conn.close()
        return len(tables) > 0
    except sqlite3.Error:
        return False


def initialize_schema():
    from lifelog.utils.db.db_helper import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.executescript("""          
        CREATE TABLE IF NOT EXISTS trackers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE,
            title TEXT,
            type TEXT,
            category TEXT,
            created DATETIME,
            notes TEXT, 
            tags TEXT
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
            tags TEXT
            
        );
        
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE,
            tracker_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL, -- redundant but useful for quick joins or debugging
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
            -- No special fields, treated as True once any value is logged per period
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
            mode TEXT CHECK (mode IN ('goal', 'tracker')) DEFAULT 'goal',
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
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );

        
        CREATE TABLE IF NOT EXISTS tracker_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT UNIQUE,
        tracker_id INTEGER,
        timestamp DATETIME,
        value FLOAT,
        FOREIGN KEY(tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
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
            FOREIGN KEY(task_id) REFERENCES tasks(id)
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
            last_synced_at TEXT  -- ISO‐8601 timestamp of last successful pull
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

        
        """)
        cursor.executescript("""
            CREATE INDEX IF NOT EXISTS idx_tracker_entries_tracker_id ON tracker_entries(tracker_id);
            CREATE INDEX IF NOT EXISTS idx_time_history_task_id ON time_history(task_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);
            CREATE INDEX IF NOT EXISTS idx_goals_tracker_id ON goals(tracker_id);
            """)
        cursor.executescript("SELECT COUNT(*) FROM feedback_sayings")
        conn.commit()
    except sqlite3.Error as e:
        print(f"Schema initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()


def add_record(table, data, fields):
    from lifelog.utils.db.db_helper import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    if "uid" in fields and not data.get("uid"):
        data["uid"] = str(uuid.uuid4())

    cols = ', '.join(fields)
    placeholders = ', '.join(['?'] * len(fields))
    values = [data.get(f) for f in fields]

    cursor.execute(f"""
        INSERT INTO {table} ({cols}) VALUES ({placeholders})
    """, values)
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_record(table, record_id, updates):
    from lifelog.utils.db.db_helper import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    fields = []
    values = []
    for key, value in updates.items():
        fields.append(f"{key} = ?")
        values.append(value)
    values.append(record_id)
    cursor.execute(
        f"UPDATE {table} SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_all_api_devices():
    from lifelog.utils.db.db_helper import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT device_name, device_token, paired_at
        FROM api_devices
        ORDER BY paired_at DESC
    """)
    devices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return devices
