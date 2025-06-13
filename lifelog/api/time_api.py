# lifelog/api/time_api.py

from datetime import datetime
import logging
from flask import request, jsonify, Blueprint

from lifelog.api.errors import debug_api, parse_json, error, validate_iso
from lifelog.api.auth import require_device_token
from lifelog.utils.db import time_repository, task_repository
from lifelog.config.config_manager import is_host_server

time_bp = Blueprint('time', __name__, url_prefix='/time')
logger = logging.getLogger(__name__)


def _require_host_mode():
    if not is_host_server():
        error('Endpoint only available on host', 403)


def _get_entry_or_404(uid: str):
    entry = time_repository.get_time_log_by_uid(uid)
    if not entry:
        error('TimeLog not found', 404)
    return entry


@time_bp.route('/entries', methods=['GET'])
@require_device_token
@debug_api
def list_time_entries():
    since = request.args.get('since')
    if since:
        validate_iso('since', since)

    try:
        entries = time_repository.get_all_time_logs(since=since)
        return jsonify([e.to_dict() for e in entries]), 200
    except Exception:
        logger.exception("Failed to fetch time entries")
        error('Failed to fetch entries', 500)


@time_bp.route('/entries', methods=['POST'])
@require_device_token
@debug_api
def create_time_entry():
    data = parse_json()

    # title is required
    title = data.get('title')
    if not isinstance(title, str) or not title.strip():
        error('Missing or invalid "title"', 400)

    # build repo payload
    repo_data = {'title': title.strip()}

    # optional start
    start = data.get('start')
    if start is not None:
        validate_iso('start', start)
        repo_data['start'] = start

    # optional end => historical entry
    end = data.get('end')
    if end is not None:
        validate_iso('end', end)
        repo_data['end'] = end

    # optional string fields
    for fld in ('category', 'project', 'tags', 'notes'):
        if fld in data:
            val = data[fld]
            if val is not None and not isinstance(val, str):
                error(f'Field "{fld}" must be a string', 400)
            repo_data[fld] = val

    # optional link to task by its UID
    task_uid = data.get('task_uid')
    if task_uid is not None:
        if not isinstance(task_uid, str) or not task_uid.strip():
            error('Field "task_uid" must be a non-empty string', 400)
        task = task_repository.get_task_by_uid(task_uid.strip())
        if not task:
            error('Parent task not found', 404)
        repo_data['task_id'] = task.id

    try:
        # start_time_entry handles creating active entries;
        # if 'end' is provided, it treats it as a historical entry
        new_entry = time_repository.start_time_entry(repo_data)
        return jsonify(new_entry.to_dict()), 201
    except Exception as e:
        logger.exception("Failed to create time entry")
        error('Failed to create entry', 500)


@time_bp.route('/entries/current', methods=['PUT'])
@require_device_token
@debug_api
def stop_time_entry():
    data = parse_json()

    end = data.get('end')
    if not isinstance(end, str):
        error('Missing or invalid "end" timestamp', 400)
    validate_iso('end', end)

    tags = data.get('tags')
    if 'tags' in data and tags is not None and not isinstance(tags, str):
        error('Field "tags" must be a string', 400)

    notes = data.get('notes')
    if 'notes' in data and notes is not None and not isinstance(notes, str):
        error('Field "notes" must be a string', 400)

    try:
        stopped = time_repository.stop_active_time_entry(
            end, tags=tags, notes=notes)
        if not stopped:
            error('No active time entry to stop', 400)
        return jsonify(stopped.to_dict()), 200
    except RuntimeError as e:
        error(str(e), 400)
    except Exception:
        logger.exception("Failed to stop active time entry")
        error('Failed to stop entry', 500)


@time_bp.route('/entries/uid/<string:uid>', methods=['GET'])
@require_device_token
@debug_api
def get_time_entry_by_uid(uid):
    entry = _get_entry_or_404(uid)
    return jsonify(entry.to_dict()), 200


@time_bp.route('/entries/uid/<string:uid>', methods=['PUT'])
@require_device_token
@debug_api
def update_time_entry_by_uid(uid):
    _require_host_mode()
    _get_entry_or_404(uid)

    data = parse_json()
    # strip any accidental numeric id
    data.pop('id', None)
    data.pop('uid', None)

    # validate ISO fields
    for fld in ('start', 'end'):
        if fld in data and data[fld] is not None:
            validate_iso(fld, data[fld])

    # optional link to task by UID
    if 'task_uid' in data:
        tu = data.pop('task_uid')
        if tu is not None:
            if not isinstance(tu, str) or not tu.strip():
                error('Field "task_uid" must be non-empty string', 400)
            task = task_repository.get_task_by_uid(tu.strip())
            if not task:
                error('Parent task not found', 404)
            data['task_id'] = task.id

    # no numeric id allowed:
    if 'task_id' in data:
        error('Direct "task_id" not supported; use "task_uid"', 400)

    try:
        time_repository.update_time_log_by_uid(uid, data)
        updated = _get_entry_or_404(uid)
        return jsonify(updated.to_dict()), 200
    except Exception:
        logger.exception(f"Failed to update TimeLog uid={uid}")
        error('Failed to update entry', 500)


@time_bp.route('/entries/uid/<string:uid>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_time_entry_by_uid(uid):
    _require_host_mode()
    _get_entry_or_404(uid)

    try:
        time_repository.delete_time_log_by_uid(uid)
        # verify deletion
        if time_repository.get_time_log_by_uid(uid):
            error('Delete failed', 500)
        return jsonify({'status': 'success'}), 200
    except Exception:
        logger.exception(f"Failed to delete TimeLog uid={uid}")
        error('Failed to delete entry', 500)
