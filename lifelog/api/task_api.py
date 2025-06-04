# api/task_api.py
from flask import request, jsonify, Blueprint
from lifelog.utils.db import task_repository
from api.auth import require_api_key

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


@tasks_bp.route('/', methods=['GET'])
@require_api_key
def list_tasks():
    status = request.args.get('status')
    tasks = task_repository.query_tasks(status=status)
    return jsonify([task.__dict__ for task in tasks])


@tasks_bp.route('/', methods=['POST'])
@require_api_key
def create_task():
    data = request.json
    task = task_repository.add_task(data)
    return jsonify(task.__dict__), 201


@tasks_bp.route('/<int:task_id>', methods=['GET'])
@require_api_key
def get_task(task_id):
    task = task_repository.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task.__dict__)


@tasks_bp.route('/<int:task_id>/done', methods=['POST'])
@require_api_key
def mark_task_done(task_id):
    # Implementation would call task_repository.update_task
    return jsonify({'status': 'success', 'message': f'Task {task_id} marked done'})
