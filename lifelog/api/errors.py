import functools
import logging
from flask import jsonify, request
from datetime import datetime

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def debug_api(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ApiError as e:
            return jsonify({'error': e.message}), e.status_code
        except Exception:
            logger.exception("Unhandled exception in API endpoint")
            return jsonify({'error': 'Internal server error'}), 500
    return wrapped


def error(message, code=400):
    raise ApiError(message, code)


def parse_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        error('Invalid JSON payload', 400)
    return data


def require_fields(data, *fields):
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


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify({'error': err.message}), err.status_code

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify({'error': 'Not Found', 'path': request.path}), 404

    @app.errorhandler(500)
    def handle_500(err):
        logger.exception("Server Error")
        return jsonify({'error': 'Internal server error'}), 500
