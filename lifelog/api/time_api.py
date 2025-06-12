# lifelog/api/time_api.py

from datetime import datetime
import logging
from flask import request, jsonify, Blueprint
from lifelog.api.errors import debug_api, parse_json, error, validate_iso
from lifelog.api.auth import require_device_token
from lifelog.utils.db import time_repository
from lifelog.config.config_manager import is_host_server

time_bp = Blueprint('time', __name__, url_prefix='/time')
logger = logging.getLogger(__name__)


def _get_time_entry_or_404(uid_val: str):
    """
    Fetch a TimeLog by UID or raise ApiError(404).
    """
    entry = time_repository.get_time_log_by_uid(uid_val)
    if not entry:
        error('TimeLog not found', 404)
    return entry


def _require_host_mode():
    """
    Raise ApiError(403) if not host server.
    """
    if not is_host_server():
        error('Endpoint only available on host', 403)


@time_bp.route('/entries', methods=['GET'])
@require_device_token
@debug_api
def list_time_entries():
    """
    GET /time/entries?since=<ISO>
    """
    since = request.args.get('since')
    if since:
        # validate ISO or raise ApiError
        validate_iso('since', since)
    try:
        entries = time_repository.get_all_time_logs(since=since)
        result = [entry.to_dict() for entry in entries]
        return jsonify(result), 200
    except Exception:
        logger.exception("Failed to fetch time entries")
        error('Failed to fetch entries', 500)


@time_bp.route('/entries', methods=['POST'])
@require_device_token
@debug_api
def create_time_entry():
    """
    POST /time/entries
    Start a new time entry.
    """
    data = parse_json()  # raises ApiError if invalid JSON

    # Required: title
    title = data.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        error('Missing or invalid "title" field', 400)
    repo_data = {"title": title.strip()}

    # Optional: start
    if "start" in data and data["start"] is not None:
        start_val = data["start"]
        # validate ISO or raise
        validate_iso("start", start_val)
        repo_data["start"] = start_val

    # Optional string fields
    for fld in ("category", "project", "tags", "notes"):
        if fld in data:
            val = data.get(fld)
            if val is not None and not isinstance(val, str):
                error(f'Field "{fld}" must be a string', 400)
            repo_data[fld] = val

    # Optional: task_id
    if "task_id" in data and data.get("task_id") is not None:
        try:
            task_id_val = int(data["task_id"])
        except Exception:
            error(f'Invalid "task_id": {data["task_id"]}', 400)
        repo_data["task_id"] = task_id_val

    try:
        new_log = time_repository.start_time_entry(repo_data)
        if not new_log:
            error('Failed to start entry', 500)
        return jsonify(new_log.to_dict()), 201
    except Exception:
        logger.exception("Failed to start time entry")
        error('Failed to start entry', 500)


@time_bp.route('/entries/current', methods=['PUT'])
@require_device_token
@debug_api
def stop_time_entry():
    """
    Stop the current active time entry.
    """
    data = parse_json()

    end_str = data.get("end")
    if not end_str:
        error('Missing "end" timestamp', 400)
    # validate ISO or raise
    validate_iso("end", end_str)

    # Optional tags/notes
    tags = data.get("tags")
    if "tags" in data and tags is not None and not isinstance(tags, str):
        error('Field "tags" must be a string', 400)
    notes = data.get("notes")
    if "notes" in data and notes is not None and not isinstance(notes, str):
        error('Field "notes" must be a string', 400)

    try:
        updated = time_repository.stop_active_time_entry(
            end_str, tags=tags, notes=notes)
        if not updated:
            error('No active time entry to stop', 400)
        return jsonify(updated.to_dict()), 200
    except RuntimeError as e:
        # e.g. no active entry
        error(str(e), 400)
    except Exception:
        logger.exception("Failed to stop active time entry")
        error('Failed to stop entry', 500)


@time_bp.route('/entries/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_time_entry_by_uid(uid_val):
    """
    Fetch a single TimeLog by global UID.
    """
    entry = _get_time_entry_or_404(uid_val)
    return jsonify(entry.to_dict()), 200


@time_bp.route('/entries/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_time_entry_by_uid(uid_val):
    """
    Update fields of a TimeLog by UID. Host-only.
    """
    _require_host_mode()
    _get_time_entry_or_404(uid_val)  # ensure exists

    data = parse_json()
    # Prevent overriding id/uid
    data.pop("id", None)
    data.pop("uid", None)

    # Validate ISO fields if present
    for fld in ("start", "end"):
        if fld in data and data[fld] is not None:
            validate_iso(fld, data[fld])

    # Validate numeric task_id
    if "task_id" in data and data.get("task_id") is not None:
        try:
            task_id_val = int(data["task_id"])
        except Exception:
            error(f'Invalid "task_id": {data["task_id"]}', 400)
        data["task_id"] = task_id_val

    # Validate string fields
    for fld in ("title", "category", "project", "tags", "notes"):
        if fld in data and data[fld] is not None and not isinstance(data[fld], str):
            error(f'Field "{fld}" must be a string', 400)

    try:
        time_repository.update_time_log_by_uid(uid_val, data)
    except Exception:
        logger.exception(f"Failed to update TimeLog uid={uid_val}")
        error('Failed to update entry', 500)

    # Fetch updated
    updated = _get_time_entry_or_404(uid_val)
    return jsonify(updated.to_dict()), 200


@time_bp.route('/entries/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_time_entry_by_uid(uid_val):
    """
    Delete a TimeLog by UID. Host-only.
    """
    _require_host_mode()
    _get_time_entry_or_404(uid_val)

    try:
        time_repository.delete_time_log_by_uid(uid_val)
    except Exception:
        logger.exception(f"Failed to delete TimeLog uid={uid_val}")
        error('Failed to delete entry', 500)

    # Verify deletion
    still = time_repository.get_time_log_by_uid(uid_val)
    if still:
        error('Delete failed', 500)
    return jsonify({'status': 'success'}), 200
