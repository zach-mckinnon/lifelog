# api/task_api.py

from flask import request, jsonify, Blueprint
from lifelog.api.errors import debug_api
from lifelog.api.auth import require_api_key
from lifelog.utils.db import task_repository
from lifelog.config.config_manager import is_host_server, is_client_mode
from lifelog.utils.db.db_helper import should_sync

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


@tasks_bp.route('/', methods=['GET'])
@require_api_key
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
@require_api_key
@debug_api
def create_task():
    """
    Create a new task. Always allowed (host or client). In client mode,
    this will queue a sync; in host mode, it writes directly.
    Returns the newly created Task (with id and uid).
    """
    data = request.json or {}
    new_task = task_repository.add_task(data)
    if not new_task:
        return jsonify({'error': 'Failed to create task'}), 500

    return jsonify(new_task.__dict__), 201


@tasks_bp.route('/<int:task_id>', methods=['GET'])
@require_api_key
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
@require_api_key
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
@require_api_key
@debug_api
def update_task_api(task_id):
    # 1) fetch existing task by its numeric ID
    existing = task_repository.get_task_by_id(task_id)
    if not existing:
        return jsonify({'error': 'Task not found'}), 404

    # 2) apply the updates
    updates = request.json or {}
    task_repository.update_task(task_id, updates)

    # 3) re-fetch and return the fresh copy
    updated = task_repository.get_task_by_id(task_id)
    return jsonify(updated.__dict__), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['PUT'])
@require_api_key
@debug_api
def update_task_by_uid_api(uid_val):
    """
    Update a task by its global UID. Only allowed in host mode.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    data = request.json or {}
    success = task_repository.update_task_by_uid(uid_val, data)
    # repository.update_task_by_uid does not return value, so verify by fetching
    tasks = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if not tasks:
        return jsonify({'error': 'Task not found'}), 404

    task = tasks[0]
    return jsonify(task.__dict__), 200


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@require_api_key
@debug_api
def delete_task_api(task_id):
    """
    Delete a task by numeric ID. In client mode, this queues a delete; in host mode, deletes directly.
    """
    # 1) Verify it exists first
    existing = task_repository.get_task_by_id(task_id)
    if not existing:
        return jsonify({'error': 'Task not found'}), 404

    # 2) Perform the deletion
    task_repository.delete_task(task_id)

    # 3) Return success
    return jsonify({'status': 'success'}), 200


@tasks_bp.route('/uid/<string:uid_val>', methods=['DELETE'])
@require_api_key
@debug_api
def delete_task_by_uid_api(uid_val):
    """
    Delete a task by global UID. Only allowed in host mode.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    success = task_repository.delete_task_by_uid(uid_val)
    # Verify deletion
    tasks = task_repository.query_tasks(uid=uid_val, show_completed=True)
    if not tasks:
        return jsonify({'error': 'Task not found'}), 404

    task = tasks[0]
    return jsonify(task.__dict__), 200


@tasks_bp.route('/<int:task_id>/done', methods=['POST'])
@require_api_key
@debug_api
def mark_task_done(task_id):
    """
    Mark a task as done by numeric ID. This is a convenience endpoint.
    """
    # In client mode, this update is queued; in host mode, updates directly.
    task_repository.update_task(task_id, {'status': 'done'})
    updated = task_repository.get_task_by_id(task_id)
    if not updated:
        return jsonify({'error': 'Failed to mark done'}), 400
    return jsonify({'status': 'success', 'task': updated.__dict__}), 200
