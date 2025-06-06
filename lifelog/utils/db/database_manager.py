from lifelog.config.config_manager import BASE_DIR
import sqlite3
from pathlib import Path

DB_PATH = BASE_DIR / "lifelog.db"


class DBConnection:
    def __enter__(self):
        self.conn = get_connection()
        return self.conn.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.commit()
        self.conn.close()


def get_connection():
    # 1) ensure ~/.lifelog exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 2) open (or create) the DB file
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # 3) turn on FOREIGN KEY support so ON DELETE CASCADE works
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def is_initialized() -> bool:
    """Check if database exists and has tables"""
    if not DB_PATH.exists():
        return False

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            return len(tables) > 0
    except sqlite3.Error:
        return False


def initialize_schema():
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
            created DATETIME
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
            amount REAL NOT NULL,
            unit TEXT,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_count (
            goal_id INTEGER PRIMARY KEY,
            amount INTEGER NOT NULL,
            unit TEXT,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_bool (
            goal_id INTEGER PRIMARY KEY,
            -- No special fields, treated as True once any value is logged per period
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_streak (
            goal_id INTEGER PRIMARY KEY,
            target_streak INTEGER NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_duration (
            goal_id INTEGER PRIMARY KEY,
            amount REAL NOT NULL,
            unit TEXT DEFAULT 'minutes',
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_milestone (
            goal_id INTEGER PRIMARY KEY,
            target REAL NOT NULL,
            unit TEXT,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_reduction (
            goal_id INTEGER PRIMARY KEY,
            amount REAL NOT NULL,
            unit TEXT,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_range (
            goal_id INTEGER PRIMARY KEY,
            min_amount REAL NOT NULL,
            max_amount REAL NOT NULL,
            unit TEXT,
            mode TEXT CHECK (mode IN ('goal', 'tracker')) DEFAULT 'goal',
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_percentage (
            goal_id INTEGER PRIMARY KEY,
            target_percentage REAL NOT NULL,
            current_percentage REAL DEFAULT 0,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS goal_replacement (
            goal_id INTEGER PRIMARY KEY,
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
            tracker_id INTEGER,
            timestamp DATETIME,
            value FLOAT,
            FOREIGN KEY(tracker_id) REFERENCES trackers(id)
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
        
        """)
        cursor.executescript("""
            CREATE INDEX IF NOT EXISTS idx_tracker_entries_tracker_id ON tracker_entries(tracker_id);
            CREATE INDEX IF NOT EXISTS idx_time_history_task_id ON time_history(task_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);
            CREATE INDEX IF NOT EXISTS idx_goals_tracker_id ON goals(tracker_id);
            """)

        conn.commit()
    except sqlite3.Error as e:
        print(f"Schema initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()


def add_record(table, data, fields):
    conn = get_connection()
    cursor = conn.cursor()
    cols = ', '.join(fields)
    placeholders = ', '.join(['?'] * len(fields))
    values = [data.get(f) for f in fields]
    cursor.execute(f"""
        INSERT INTO {table} ({cols}) VALUES ({placeholders})
    """, values)
    conn.commit()
    conn.close()


def update_record(table, record_id, updates):
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
