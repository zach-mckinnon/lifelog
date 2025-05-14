import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".lifelog" / "lifelog.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_schema():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        recur_base DATETIME
    );
    
    CREATE TABLE IF NOT EXISTS task_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        start DATETIME,
        end DATETIME,
        duration_minutes FLOAT,
        tags TEXT,
        notes TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

    CREATE TABLE IF NOT EXISTS trackers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        type TEXT,
        category TEXT,
        created DATETIME
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
    title TEXT NOT NULL,               
    start DATETIME NOT NULL,
    end DATETIME,                     
    duration_minutes FLOAT,           
    task_id INTEGER,                   
    category TEXT,
    project TEXT,
    tags TEXT,
    notes TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

    CREATE TABLE IF NOT EXISTS environment_data (
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
    """)

    conn.commit()
    conn.close()
