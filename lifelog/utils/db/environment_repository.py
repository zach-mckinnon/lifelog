# lifelog/utils/db/environment_repository.py

from typing import Optional, Dict, Any
from lifelog.utils.db import get_connection
import json
from lifelog.utils.core_utils import now_utc

# Only these four sections exist in the schema
VALID_SECTIONS = {"weather", "air_quality", "moon", "satellite"}


def save_environment_data(section: str, data: Any) -> None:
    """
    Save a blob of environment data into the specified column.
    `section` must be one of VALID_SECTIONS; `data` will be JSON-dumped.
    """
    if section not in VALID_SECTIONS:
        raise ValueError(
            f"Invalid section '{section}'. Must be one of: {', '.join(VALID_SECTIONS)}"
        )
    with get_connection() as conn:
        cur = conn.cursor()
        # Insert into the named column; other columns stay NULL
        cur.execute(
            f"INSERT INTO environment_data (timestamp, {section}) VALUES (?, ?)",
            (now_utc(), json.dumps(data))
        )


def get_latest_environment_data(section: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the most-recent JSON blob from the given column.
    Returns the parsed dict, or None if no rows exist.
    """
    if section not in VALID_SECTIONS:
        raise ValueError(
            f"Invalid section '{section}'. Must be one of: {', '.join(VALID_SECTIONS)}"
        )
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {section}
              FROM environment_data
             WHERE {section} IS NOT NULL
             ORDER BY timestamp DESC
             LIMIT 1
            """
        )
        row = cur.fetchone()

    if not row:
        return None

    # row[0] is the JSON string in the named column
    return json.loads(row[0])
