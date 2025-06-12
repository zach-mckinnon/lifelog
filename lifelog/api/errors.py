import functools
import logging
from flask import jsonify, request
from datetime import datetime

logger = logging.getLogger(__name__)

# ——— Generic error handler decorator ———


def debug_api(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ApiError as e:
            # our custom exception
            return jsonify({'error': e.message}), e.status_code
        except Exception:
            logger.exception("Unhandled exception in API endpoint")
            return jsonify({'error': 'Internal server error'}), 500
    return wrapped

# ——— Custom exception for expected errors ———


class ApiError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# ——— Helpers ———


def error(message, code=400):
    """Raise an ApiError so @debug_api will catch it."""
    raise ApiError(message, code)


def parse_json():
    """Parse `request.get_json()`, or error 400."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        error('Invalid JSON payload', 400)
    return data


def require_fields(data, *fields):
    """Ensure those keys exist and are non‐empty in `data`."""
    for f in fields:
        if f not in data or data[f] is None or (isinstance(data[f], str) and not data[f].strip()):
            error(f'Missing or invalid "{f}" field', 400)


def validate_iso(name, val):
    if not isinstance(val, str):
        error(f'Field "{name}" must be ISO-format string', 400)
    try:
        datetime.fromisoformat(val)
    except Exception as e:
        error(f'Invalid "{name}" timestamp: {e}', 400)
    return val


def identify(payload, repo_by_uid, repo_by_id):
    """
    Returns (obj, id_field, id_value) or raises 400/404 ApiError.
    """
    if 'uid' in payload:
        uid = payload['uid']
        obj = repo_by_uid(uid)
        if not obj:
            error('Record not found for given uid', 404)
        return obj, 'uid', uid

    if 'id' in payload:
        try:
            iid = int(payload['id'])
        except Exception:
            error('Invalid id in payload', 400)
        obj = repo_by_id(iid)
        if not obj:
            error('Record not found for given id', 404)
        return obj, 'id', iid

    error('No identifier provided', 400)
