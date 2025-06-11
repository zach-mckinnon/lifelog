# api/task_api.py

import logging
from flask import request, jsonify, Blueprint
from lifelog.api.errors import debug_api
from lifelog.api.auth import require_device_token
from lifelog.utils.db import task_repository
from lifelog.config.config_manager import is_host_server, is_client_mode
from lifelog.utils.db.db_helper import should_sync
from lifelog.utils.db.models import get_task_fields

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')

logger = logging.getLogger(__name__)


@tasks_bp.route('/', methods=['GET'])
@require_device_token
@debug_api
def list_tasks():
    """
    List tasks, optionally filtered by uid, status, category, project, etc.
    In client mode, query_tasks will first push/pull to keep local cache up-to-date.
    """
    # Gather query parameters
    uid = request.args.get('uid')
    status = request.args.get('status')
    category = request.args.get('category')
    project = request.args.get('project')
    importance = request.args.get('importance', type=int)
    due_contains = request.args.get('due_contains')
    show_completed = request.args.get(
        'show_completed', 'false').lower() == 'true'
    sort = request.args.get('sort', 'priority')

    # Build filter kwargs; skip None
    filters = {
        'uid': uid,
        'status': status,
        'category': category,
        'project': project,
        'importance': importance,
        'due_contains': due_contains,
        'show_completed': show_completed,
        'sort': sort
    }
    # Remove keys with None values so repository can handle defaults
    filters = {k: v for k, v in filters.items() if v is not None}

    tasks = task_repository.query_tasks(**filters)
    return jsonify([t.__dict__ for t in tasks]), 200


@tasks_bp.route('/', methods=['POST'])
@require_device_token
@debug_api
def create_task():
    """
    Create a new task. In client mode, this will queue a sync; in host mode, writes directly.
    Validates payload keys and required fields.
    Returns 201 with created Task, or 400 on invalid input, 500 on server error.
    """
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid JSON payload'}), 400

    # Filter to allowed fields
    allowed_fields = set(get_task_fields())
    extra_keys = set(data.keys()) - allowed_fields
    if extra_keys:
        return jsonify({'error': f'Unknown field(s): {", ".join(sorted(extra_keys))}'}), 400

    # Required: title
    title = data.get('title')
    if not title or not isinstance(title, str) or not title.strip():
        return jsonify({'error': 'Field "title" is required and must be non-empty string'}), 400

    # Additional validation can be applied here (e.g., importance range, due format)
    # Example: validate importance if provided
    if 'importance' in data:
        try:
            imp = int(data['importance'])
            if imp < 0 or imp > 5:
                raise ValueError
            data['importance'] = imp
        except Exception:
            return jsonify({'error': 'Field "importance" must be integer between 0 and 5'}), 400
    if 'due' in data:
        # We assume repository or model conversion will parse ISO; here we can do a simple check
        due_val = data['due']
        if due_val is not None:
            if not isinstance(due_val, str):
                return jsonify({'error': 'Field "due" must be ISO-format string'}), 400
            # Optionally: try datetime.fromisoformat to validate format
            from datetime import datetime
            try:
                datetime.fromisoformat(due_val)
            except Exception:
                return jsonify({'error': 'Field "due" must be valid ISO datetime string'}), 400

    # All other fields are optional; repository.add_task will handle defaults
    try:
        new_task = task_repository.add_task(data)
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error in create_task: {e}", exc_info=True)
        return jsonify({'error': 'Failed to create task'}), 500

    if not new_task:
        return jsonify({'error': 'Failed to create task'}), 500

    return jsonify(new_task.__dict__), 201


@tasks_bp.route('/<int:task_id>', methods=['GET'])
@require_device_token
@debug_api
def get_task(task_id):
    """
    Fetch a single task by numeric ID. In client mode, this will push local changes
    then pull the latest version of this task from the host before returning.
    """
    task = task_repository.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task.__dict__), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_task_by_uid(uid_val):
    """
    Fetch a single task by its global UID. Only allowed if:
      - host mode (direct DB), or
      - client mode (will push/pull to keep local cache in sync).
    """
    # In client mode, repository.get_task_by_uid will push pending changes then pull
    # this single task from host. In host mode, it reads directly.
    tasks = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if not tasks:
        return jsonify({'error': 'Task not found'}), 404

    task = tasks[0]
    return jsonify(task.__dict__), 200


@tasks_bp.route('/<int:task_id>', methods=['PUT'])
@require_device_token
@debug_api
def update_task_api(task_id):
    """
    Update a task by numeric ID. Validates payload keys and formats.
    """
    existing = task_repository.get_task_by_id(task_id)
    if not existing:
        return jsonify({'error': 'Task not found'}), 404

    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid JSON payload'}), 400

    # Filter to allowed fields
    allowed_fields = set(get_task_fields())
    extra_keys = set(data.keys()) - allowed_fields
    if extra_keys:
        return jsonify({'error': f'Unknown field(s): {", ".join(sorted(extra_keys))}'}), 400

    # Remove any keys with None (no-op) or skip if value unchanged?
    updates = {}
    from datetime import datetime
    for key, val in data.items():
        # Skip None values (do not override to None)
        if val is None:
            continue
        # Validate per-field
        if key == 'title':
            if not isinstance(val, str) or not val.strip():
                return jsonify({'error': 'Field "title" must be non-empty string'}), 400
            updates[key] = val
        elif key == 'importance':
            try:
                imp = int(val)
                if imp < 0 or imp > 5:
                    raise ValueError
                updates[key] = imp
            except Exception:
                return jsonify({'error': 'Field "importance" must be integer between 0 and 5'}), 400
        elif key == 'due':
            if not isinstance(val, str):
                return jsonify({'error': 'Field "due" must be ISO-format string'}), 400
            try:
                datetime.fromisoformat(val)
            except Exception:
                return jsonify({'error': 'Field "due" must be valid ISO datetime string'}), 400
            updates[key] = val
        elif key == 'status':
            if not isinstance(val, str) or val not in ('backlog', 'active', 'done'):
                return jsonify({'error': 'Field "status" must be one of backlog/active/done'}), 400
            updates[key] = val
        elif key in ('start', 'end', 'recur_base', 'created'):
            if not isinstance(val, str):
                return jsonify({'error': f'Field "{key}" must be ISO-format string'}), 400
            try:
                datetime.fromisoformat(val)
            except Exception:
                return jsonify({'error': f'Field "{key}" must be valid ISO datetime string'}), 400
            updates[key] = val
        elif key == 'priority':
            try:
                pr = float(val)
                updates[key] = pr
            except Exception:
                return jsonify({'error': 'Field "priority" must be a float number'}), 400
        else:
            # category, project, tags, notes, recur_interval, recur_unit, recur_days_of_week
            # Basic type checks
            if key in ('category', 'project', 'tags', 'notes', 'recur_unit', 'recur_days_of_week'):
                if not isinstance(val, str):
                    return jsonify({'error': f'Field "{key}" must be a string'}), 400
                updates[key] = val
            elif key == 'recur_interval':
                try:
                    updates[key] = int(val)
                except Exception:
                    return jsonify({'error': 'Field "recur_interval" must be integer'}), 400
            else:
                # Should not reach here, since we filtered keys already
                continue

    if not updates:
        return jsonify({'error': 'No valid fields provided for update'}), 400

    try:
        task_repository.update_task(task_id, updates)
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error updating task {task_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to update task'}), 500

    updated = task_repository.get_task_by_id(task_id)
    if not updated:
        return jsonify({'error': 'Task disappeared after update'}), 500
    return jsonify(updated.__dict__), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_task_by_uid_api(uid_val):
    """
    Update a task by its global UID. Only allowed in host mode.
    Validates payload keys and formats.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    existing_tasks = task_repository.query_tasks(
        uid=uid_val, show_completed=True)
    if not existing_tasks:
        return jsonify({'error': 'Task not found'}), 404
    existing = existing_tasks[0]

    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid JSON payload'}), 400

    # Filter to allowed fields
    allowed_fields = set(get_task_fields())
    extra_keys = set(data.keys()) - allowed_fields
    if extra_keys:
        return jsonify({'error': f'Unknown field(s): {", ".join(sorted(extra_keys))}'}), 400

    # Validate fields identically to update_task_api
    updates = {}
    from datetime import datetime
    for key, val in data.items():
        if val is None:
            continue
        if key == 'title':
            if not isinstance(val, str) or not val.strip():
                return jsonify({'error': 'Field "title" must be non-empty string'}), 400
            updates[key] = val
        elif key == 'importance':
            try:
                imp = int(val)
                if imp < 0 or imp > 5:
                    raise ValueError
                updates[key] = imp
            except Exception:
                return jsonify({'error': 'Field "importance" must be integer between 0 and 5'}), 400
        elif key == 'due':
            if not isinstance(val, str):
                return jsonify({'error': 'Field "due" must be ISO-format string'}), 400
            try:
                datetime.fromisoformat(val)
            except Exception:
                return jsonify({'error': 'Field "due" must be valid ISO datetime string'}), 400
            updates[key] = val
        elif key == 'status':
            if not isinstance(val, str) or val not in ('backlog', 'active', 'done'):
                return jsonify({'error': 'Field "status" must be one of backlog/active/done'}), 400
            updates[key] = val
        elif key in ('start', 'end', 'recur_base', 'created'):
            if not isinstance(val, str):
                return jsonify({'error': f'Field "{key}" must be ISO-format string'}), 400
            try:
                datetime.fromisoformat(val)
            except Exception:
                return jsonify({'error': f'Field "{key}" must be valid ISO datetime string'}), 400
            updates[key] = val
        elif key == 'priority':
            try:
                pr = float(val)
                updates[key] = pr
            except Exception:
                return jsonify({'error': 'Field "priority" must be a float number'}), 400
        else:
            # category, project, tags, notes, recur_interval, recur_unit, recur_days_of_week
            if key in ('category', 'project', 'tags', 'notes', 'recur_unit', 'recur_days_of_week'):
                if not isinstance(val, str):
                    return jsonify({'error': f'Field "{key}" must be a string'}), 400
                updates[key] = val
            elif key == 'recur_interval':
                try:
                    updates[key] = int(val)
                except Exception:
                    return jsonify({'error': 'Field "recur_interval" must be integer'}), 400

    if not updates:
        return jsonify({'error': 'No valid fields provided for update'}), 400

    try:
        task_repository.update_task_by_uid(uid_val, updates)
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error updating task UID={uid_val}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to update task'}), 500

    # Fetch fresh copy
    tasks = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if not tasks:
        # Could not find after update
        return jsonify({'error': 'Task not found after update'}), 500
    task = tasks[0]
    return jsonify(task.__dict__), 200


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_task_api(task_id):
    """
    Delete a task by numeric ID. In client mode, this queues a delete; in host mode, deletes directly.
    """
    existing = task_repository.get_task_by_id(task_id)
    if not existing:
        return jsonify({'error': 'Task not found'}), 404
    try:
        task_repository.delete_task(task_id)
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error deleting task {task_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to delete task'}), 500
    return jsonify({'status': 'success'}), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_task_by_uid_api(uid_val):
    """
    Delete a task by global UID. Only allowed in host mode.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    # Verify existence first
    tasks = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if not tasks:
        return jsonify({'error': 'Task not found'}), 404

    try:
        task_repository.delete_task_by_uid(uid_val)
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error deleting task UID={uid_val}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to delete task'}), 500

    # Verify deletion
    remaining = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if remaining:
        return jsonify({'error': 'Failed to delete task'}), 500

    return jsonify({'status': 'success'}), 200


@tasks_bp.route('/<int:task_id>/done', methods=['POST'])
@require_device_token
@debug_api
def mark_task_done(task_id):
    """
    Mark a task as done by numeric ID. Convenience endpoint.
    """
    existing = task_repository.get_task_by_id(task_id)
    if not existing:
        return jsonify({'error': 'Task not found'}), 404
    try:
        task_repository.update_task(task_id, {'status': 'done'})
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error marking task {task_id} done: {e}", exc_info=True)
        return jsonify({'error': 'Failed to mark done'}), 500
    updated = task_repository.get_task_by_id(task_id)
    if not updated:
        return jsonify({'error': 'Failed to fetch updated task'}), 500
    return jsonify({'status': 'success', 'task': updated.__dict__}), 200
