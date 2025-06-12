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
    # Allowed fields from dataclass (excluding 'id')
    allowed_fields = set(get_task_fields())
    extra_keys = set(data) - allowed_fields
    if extra_keys:
        return None, f'Unknown field(s): {", ".join(sorted(extra_keys))}'

    cleaned: dict = {}
    # Define allowed values
    allowed_status = {status.value for status in TaskStatus}
    allowed_recur_units = {"days", "weeks", "months"}

    for key, raw_val in data.items():
        # Skip keys with value None if partial update
        if raw_val is None:
            continue

        # Field-specific validation/conversion
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
            cleaned[key] = raw_val  # or normalized string

        elif key in ('project', 'category', 'tags', 'notes'):
            if not isinstance(raw_val, str):
                return None, f'Field "{key}" must be a string'
            cleaned[key] = raw_val.strip() or None

        elif key == 'uid':
            if not isinstance(raw_val, str) or not raw_val.strip():
                return None, 'Field "uid" must be non-empty string'
            cleaned[key] = raw_val.strip()

        else:
            # Should not happen since filtered allowed_fields
            return None, f'Unhandled field "{key}"'

    # If not partial and some required fields missing
    if not partial:
        if 'title' not in cleaned:
            return None, 'Field "title" is required'
        # If created missing, set now
        if 'created' not in cleaned:
            cleaned['created'] = datetime.utcnow()

    # Attempt to build Task to catch errors
    try:
        task_obj = Task(**cleaned)
    except Exception as e:
        return None, f'Error constructing Task: {e}'
    # Return Python-native dict for repository
    return task_obj.asdict(), None


def _get_task_or_404(task_id: int) -> Task:
    """
    Fetch task by numeric ID or raise ApiError(404).
    """
    task = task_repository.get_task_by_id(task_id)
    if not task:
        error('Task not found', 404)
    return task


def _get_task_by_uid_or_404(uid_val: str) -> Task:
    tasks = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if not tasks:
        error('Task not found', 404)
    return tasks[0]


@tasks_bp.route('/', methods=['GET'])
@require_device_token
@debug_api
def list_tasks():
    """
    List tasks, optionally filtered by uid, status, category, project, etc.
    Inline validation: raises ApiError on bad filters.
    """
    filters: dict = {}

    # uid filter
    uid = request.args.get('uid')
    if uid:
        filters['uid'] = uid

    # status filter
    status = request.args.get('status')
    if status:
        allowed_status = {s.value for s in TaskStatus}
        if status not in allowed_status:
            error(
                f'Invalid status filter: must be one of {", ".join(sorted(allowed_status))}', 400)
        filters['status'] = status

    # category/project
    category = request.args.get('category')
    if category:
        filters['category'] = category
    project = request.args.get('project')
    if project:
        filters['project'] = project

    # importance
    imp = request.args.get('importance', type=int)
    if imp is not None:
        if imp < 0 or imp > 5:
            error('Invalid importance filter: must be between 0 and 5', 400)
        filters['importance'] = imp

    # due_contains
    due_contains = request.args.get('due_contains')
    if due_contains:
        filters['due_contains'] = due_contains

    # show_completed
    show_completed = request.args.get(
        'show_completed', 'false').lower() == 'true'
    filters['show_completed'] = show_completed

    # sort
    sort = request.args.get('sort', 'priority')
    filters['sort'] = sort

    tasks = task_repository.query_tasks(**filters)
    return jsonify([t.to_dict() for t in tasks]), 200


@tasks_bp.route('/', methods=['POST'])
@require_device_token
@debug_api
def create_task():
    """
    Create a new task. Uses centralized validation & conversion.
    """
    data = parse_json()              # raises ApiError if invalid JSON
    # Ensure required fields
    require_fields(data, 'title')
    # Validate & clean
    cleaned, err = _filter_and_validate_task_data(data, partial=False)
    if err:
        error(err, 400)
    try:
        new_task = task_repository.add_task(cleaned)
    except Exception as e:
        logger.exception("Error in create_task")
        error('Failed to create task', 500)

    if not new_task:
        error('Failed to create task', 500)

    return jsonify(new_task.to_dict()), 201


@tasks_bp.route('/<int:task_id>', methods=['GET'])
@require_device_token
@debug_api
def get_task(task_id):
    """
    Fetch single task by numeric ID.
    """
    task = _get_task_or_404(task_id)
    return jsonify(task.to_dict()), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_task_by_uid(uid_val):
    """
    Fetch a single task by its global UID.
    """
    task = _get_task_by_uid_or_404(uid_val)
    return jsonify(task.to_dict()), 200


@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@require_device_token
@debug_api
def update_task_api(task_id):
    """
    Update a task by numeric ID. Uses centralized validation.
    """
    _get_task_or_404(task_id)  # raises if not found

    data = parse_json()
    cleaned, err = _filter_and_validate_task_data(data, partial=True)
    if err:
        error(err, 400)
    if not cleaned:
        error('No valid fields provided for update', 400)

    try:
        task_repository.update_task(task_id, cleaned)
    except Exception:
        logger.exception(f"Error updating task {task_id}")
        error('Failed to update task', 500)

    # Return fresh copy
    updated = task_repository.get_task_by_id(task_id)
    if not updated:
        error('Task not found after update', 500)
    return jsonify(updated.to_dict()), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_task_by_uid_api(uid_val):
    """
    Update a task by its global UID. Only in host mode.
    """
    if not is_host_server():
        error('Endpoint only available on host', 403)

    _get_task_by_uid_or_404(uid_val)

    data = parse_json()
    cleaned, err = _filter_and_validate_task_data(data, partial=True)
    if err:
        error(err, 400)
    if not cleaned:
        error('No valid fields provided for update', 400)

    try:
        task_repository.update_task_by_uid(uid_val, cleaned)
    except Exception:
        logger.exception(f"Error updating task UID={uid_val}")
        error('Failed to update task', 500)

    # Fetch fresh copy
    updated = _get_task_by_uid_or_404(uid_val)
    return jsonify(updated.to_dict()), 200


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_task_api(task_id):
    """
    Delete a task by numeric ID.
    """
    _get_task_or_404(task_id)

    try:
        task_repository.delete_task(task_id)
    except Exception:
        logger.exception(f"Error deleting task {task_id}")
        error('Failed to delete task', 500)
    return jsonify({'status': 'success'}), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_task_by_uid_api(uid_val):
    """
    Delete a task by global UID. Only in host mode.
    """
    if not is_host_server():
        error('Endpoint only available on host', 403)

    _get_task_by_uid_or_404(uid_val)

    try:
        task_repository.delete_task_by_uid(uid_val)
    except Exception:
        logger.exception(f"Error deleting task UID={uid_val}")
        error('Failed to delete task', 500)

    # Verify deletion
    remaining = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if remaining:
        error('Failed to delete task', 500)
    return jsonify({'status': 'success'}), 200


@tasks_bp.route('/<int:task_id>/done', methods=['POST'])
@require_device_token
@debug_api
def mark_task_done(task_id):
    """
    Mark a task as done by numeric ID. Convenience endpoint.
    """
    _get_task_or_404(task_id)

    try:
        task_repository.update_task(task_id, {'status': 'done'})
    except Exception:
        logger.exception(f"Error marking task {task_id} done")
        error('Failed to mark done', 500)

    updated = task_repository.get_task_by_id(task_id)
    if not updated:
        error('Task not found after marking done', 500)
    return jsonify({'status': 'success', 'task': updated.to_dict()}), 200
