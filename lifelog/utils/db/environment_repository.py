# lifelog.utils/db/environment_repository.py
from lifelog.utils.db.database_manager import get_connection
from datetime import datetime
import json


def save_environment_data(section, data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO environment_data (timestamp, {section})
        VALUES (?, ?)
    """, (datetime.now().isoformat(), json.dumps(data)))
    conn.commit()
    conn.close()


def get_latest_environment_data(source: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT data FROM environment_data 
        WHERE source = ?
        ORDER BY timestamp DESC LIMIT 1
    """, (source,))
    row = cur.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None
