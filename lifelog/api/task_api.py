# api/task_api.py

import logging
from flask import request, jsonify, Blueprint
from lifelog.api.errors import debug_api, parse_json, error, require_fields, validate_iso
from lifelog.api.auth import require_device_token
from lifelog.utils.db import task_repository
from lifelog.config.config_manager import is_host_server
from lifelog.utils.db.models import Task, TaskStatus, get_task_fields

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')
logger = logging.getLogger(__name__)


def _filter_and_validate_task_data(data: dict, partial: bool = False) -> tuple[dict, str]:
    """
    Validate and convert input dict against Task dataclass.
    Returns (cleaned_dict, None) on success, or (None, error_message) on failure.
    Note: callers should call error(msg, 400) if error_message is non-None.
    """
    from datetime import datetime
    allowed_fields = set(get_task_fields())
    extra_keys = set(data) - allowed_fields
    if extra_keys:
        return None, f'Unknown field(s): {", ".join(sorted(extra_keys))}'

    cleaned: dict = {}
    allowed_status = {status.value for status in TaskStatus}
    allowed_recur_units = {"days", "weeks", "months"}

    for key, raw_val in data.items():
        if raw_val is None:
            continue
        if key == 'title':
            if not isinstance(raw_val, str) or not raw_val.strip():
                return None, 'Field "title" must be non-empty string'
            cleaned[key] = raw_val.strip()

        elif key == 'status':
            if not isinstance(raw_val, str) or raw_val not in allowed_status:
                return None, f'Field "status" must be one of {", ".join(sorted(allowed_status))}'
            cleaned[key] = TaskStatus(raw_val)

        elif key in ('due', 'start', 'end', 'created', 'recur_base'):
            if not isinstance(raw_val, str):
                return None, f'Field "{key}" must be ISO-format string'
            try:
                dt = datetime.fromisoformat(raw_val)
            except Exception:
                return None, f'Field "{key}" must be valid ISO datetime string'
            cleaned[key] = dt

        elif key == 'importance':
            try:
                imp = int(raw_val)
            except Exception:
                return None, 'Field "importance" must be integer'
            if imp < 0 or imp > 5:
                return None, 'Field "importance" must be between 0 and 5'
            cleaned[key] = imp

        elif key == 'priority':
            try:
                pr = float(raw_val)
            except Exception:
                return None, 'Field "priority" must be a number'
            if pr < 0:
                return None, 'Field "priority" must be non-negative'
            cleaned[key] = pr

        elif key == 'recur_interval':
            try:
                interval = int(raw_val)
            except Exception:
                return None, 'Field "recur_interval" must be integer'
            if interval < 1:
                return None, 'Field "recur_interval" must be >= 1'
            cleaned[key] = interval

        elif key == 'recur_unit':
            if not isinstance(raw_val, str) or raw_val not in allowed_recur_units:
                return None, f'Field "recur_unit" must be one of {", ".join(sorted(allowed_recur_units))}'
            cleaned[key] = raw_val

        elif key == 'recur_days_of_week':
            if not isinstance(raw_val, str):
                return None, 'Field "recur_days_of_week" must be string of comma-separated integers 0-6'
            parts = [p.strip() for p in raw_val.split(',') if p.strip()]
            for p in parts:
                if not p.isdigit() or not (0 <= int(p) <= 6):
                    return None, 'Field "recur_days_of_week" entries must be integers 0–6'
            cleaned[key] = raw_val

        elif key in ('project', 'category', 'tags', 'notes'):
            if not isinstance(raw_val, str):
                return None, f'Field "{key}" must be a string'
            cleaned[key] = raw_val.strip() or None

        elif key == 'uid':
            if not isinstance(raw_val, str) or not raw_val.strip():
                return None, 'Field "uid" must be non-empty string'
            cleaned[key] = raw_val.strip()

        else:
            return None, f'Unhandled field "{key}"'

    if not partial:
        if 'title' not in cleaned:
            return None, 'Field "title" is required'
        if 'created' not in cleaned:
            cleaned['created'] = datetime.now()

    try:
        task_obj = Task(**cleaned)
    except Exception as e:
        return None, f'Error constructing Task: {e}'
    return task_obj.asdict(), None


def _get_task_by_uid_or_404(uid: str):
    tasks = task_repository.query_tasks(uid=uid, show_completed=True)
    if not tasks:
        error('Task not found', 404)
    return tasks[0]


@tasks_bp.route('/', methods=['POST'])
@require_device_token
@debug_api
def create_task():
    data = parse_json()
    require_fields(data, 'title')
    cleaned, err = _filter_and_validate_task_data(data, partial=False)
    if err:
        error(err, 400)

    new_task = task_repository.add_task(cleaned)
    return jsonify(new_task.to_dict()), 201


@tasks_bp.route('/uid/<string:uid>', methods=['GET'])
@require_device_token
@debug_api
def get_task_by_uid(uid):
    t = _get_task_by_uid_or_404(uid)
    return jsonify(t.to_dict()), 200


@tasks_bp.route('/uid/<string:uid>', methods=['PUT'])
@require_device_token
@debug_api
def update_task_by_uid_api(uid):
    if not is_host_server():
        error('Endpoint only available on host', 403)
    _get_task_by_uid_or_404(uid)

    data = parse_json()
    cleaned, err = _filter_and_validate_task_data(data, partial=True)
    if err:
        error(err, 400)
    if not cleaned:
        error('No valid fields', 400)

    task_repository.update_task_by_uid(uid, cleaned)
    updated = _get_task_by_uid_or_404(uid)
    return jsonify(updated.to_dict()), 200


@tasks_bp.route('/uid/<string:uid>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_task_by_uid_api(uid):
    if not is_host_server():
        error('Endpoint only available on host', 403)
    _get_task_by_uid_or_404(uid)

    task_repository.delete_task_by_uid(uid)
    return jsonify({'status': 'success'}), 200


@tasks_bp.route('/<int:task_id>', methods=['GET', 'PUT', 'DELETE'])
@require_device_token
@debug_api
def task_id_fallback(task_id):
    t = task_repository.get_task_by_id(task_id)
    if not t:
        error('Task not found', 404)
    return jsonify(t.to_dict()), 200
