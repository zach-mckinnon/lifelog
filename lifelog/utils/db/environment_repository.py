# lifelog.utils/db/environment_repository.py
from typing import Optional
from lifelog.utils.db.db_helper import get_connection
from datetime import datetime
import json

from lifelog.utils.db.models import EnvironmentData


def save_environment_data(section, data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO environment_data (timestamp, {section})
        VALUES (?, ?)
    """, (datetime.now().isoformat(), json.dumps(data)))
    conn.commit()
    conn.close()


def get_latest_environment_data(source: str) -> Optional[EnvironmentData]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT data FROM environment_data 
        WHERE source = ?
        ORDER BY timestamp DESC LIMIT 1
    """, (source,))
    row = cur.fetchone()
    conn.close()
    return EnvironmentData(**json.loads(row[0])) if row else None
