# lifelog.utils/db/environment_repository.py
from typing import Optional
from lifelog.utils.db import get_connection
import json

from lifelog.utils.db.models import EnvironmentData
from lifelog.utils.shared_utils import now_utc


def save_environment_data(section, data):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO environment_data (timestamp, {section})
            VALUES (?, ?)
        """, (now_utc(), json.dumps(data)))


def get_latest_environment_data(source: str) -> Optional[EnvironmentData]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT data FROM environment_data 
            WHERE source = ?
            ORDER BY timestamp DESC LIMIT 1
        """, (source,))
        row = cur.fetchone()

    return EnvironmentData(**json.loads(row[0])) if row else None
