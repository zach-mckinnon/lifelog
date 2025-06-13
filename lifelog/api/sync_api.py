from flask import request, jsonify, Blueprint
from datetime import datetime
import logging

from lifelog.api.task_api import _filter_and_validate_task_data
from lifelog.api.auth import require_device_token
from lifelog.utils.db import task_repository, time_repository, track_repository

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')
logger = logging.getLogger(__name__)


def error_response(message: str, code: int = 400):
    return jsonify({'error': message}), code


def parse_sync_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response('Invalid JSON payload')
    operation = data.get('operation')
    if operation not in {'create', 'update', 'delete'}:
        return None, error_response('Invalid operation')
    payload = data.get('data')
    if not isinstance(payload, dict):
        return None, error_response('Invalid data payload')
    return {'operation': operation, 'payload': payload}, None


def require_uid(payload):
    uid = payload.get('uid')
    if not uid:
        return None, error_response('Missing "uid" in payload')
    return uid, None


@sync_bp.route('/<table>', methods=['POST'])
@require_device_token
def handle_sync(table: str):
    req, err = parse_sync_request()
    if err:
        return err
    op = req['operation']
    data = req['payload']

    if table == 'tasks':
        return _sync_tasks(op, data)
    elif table == 'time_history':
        return _sync_time(op, data)
    elif table == 'trackers':
        return _sync_trackers(op, data)
    elif table == 'goals':
        return _sync_goals(op, data)
    else:
        return error_response('Invalid table for sync')


def _sync_tasks(operation: str, payload: dict):
    if operation == 'create':
        validated, err = _filter_and_validate_task_data(payload, partial=False)
        if err:
            return err
        try:
            task_repository.add_task(validated)
        except Exception:
            logger.exception("Sync create task error")
            return error_response('Failed to create task', 500)
        return jsonify(status='success')

    # UPDATE or DELETE must include uid
    uid, err = require_uid(payload)
    if err:
        return err

    if operation == 'update':
        updates_raw = {k: v for k, v in payload.items() if k not in ('uid',)}
        if not updates_raw:
            return error_response('No fields provided for update')
        validated, err = _filter_and_validate_task_data(
            updates_raw, partial=True)
        if err:
            return err
        try:
            task_repository.update_task_by_uid(uid, validated)
        except Exception:
            logger.exception("Sync update task error")
            return error_response('Failed to update task', 500)
        return jsonify(status='success')

    if operation == 'delete':
        try:
            task_repository.delete_task_by_uid(uid)
        except Exception:
            logger.exception("Sync delete task error")
            return error_response('Failed to delete task', 500)
        return jsonify(status='success')

    return error_response('Unsupported operation')


def _sync_time(operation: str, payload: dict):
    if operation == 'create':
        if payload.get('start') is None:
            return error_response('Missing "start" for create')
        # assume repository will validate further
        try:
            time_repository.add_time_entry(payload)
        except ValueError as ve:
            return error_response(str(ve))
        except Exception:
            logger.exception("Sync create time entry error")
            return error_response('Failed to create time entry', 500)
        return jsonify(status='success')

    # UPDATE or DELETE require uid
    uid, err = require_uid(payload)
    if err:
        return err

    if operation == 'update':
        updates = {k: v for k, v in payload.items() if k != 'uid'}
        if not updates:
            return error_response('No fields provided for update')
        try:
            time_repository.update_time_log_by_uid(uid, updates)
        except Exception:
            logger.exception("Sync update time entry error")
            return error_response('Failed to update time entry', 500)
        return jsonify(status='success')

    if operation == 'delete':
        try:
            time_repository.delete_time_log_by_uid(uid)
        except Exception:
            logger.exception("Sync delete time entry error")
            return error_response('Failed to delete time entry', 500)
        return jsonify(status='success')

    return error_response('Unsupported operation')


def _sync_trackers(operation: str, payload: dict):
    if operation == 'create':
        try:
            track_repository.add_tracker(payload)
        except Exception:
            logger.exception("Sync create tracker error")
            return error_response('Failed to create tracker', 500)
        return jsonify(status='success')

    uid, err = require_uid(payload)
    if err:
        return err

    if operation == 'update':
        updates = {k: v for k, v in payload.items() if k != 'uid'}
        if not updates:
            return error_response('No fields provided for update')
        try:
            track_repository.update_tracker_by_uid(uid, updates)
        except Exception:
            logger.exception("Sync update tracker error")
            return error_response('Failed to update tracker', 500)
        return jsonify(status='success')

    if operation == 'delete':
        try:
            track_repository.delete_tracker_by_uid(uid)
        except Exception:
            logger.exception("Sync delete tracker error")
            return error_response('Failed to delete tracker', 500)
        return jsonify(status='success')

    return error_response('Unsupported operation')


def _sync_goals(operation: str, payload: dict):
    if operation == 'create':
        tracker_uid = payload.get('tracker_uid')
        if not tracker_uid:
            return error_response('Missing "tracker_uid" for goal create')
        try:
            # look up numeric tracker_id first
            tracker = track_repository.get_tracker_by_uid(tracker_uid)
            if not tracker:
                return error_response('Parent tracker not found', 404)
            track_repository.add_goal(tracker.id, payload)
        except Exception:
            logger.exception("Sync create goal error")
            return error_response('Failed to create goal', 500)
        return jsonify(status='success')

    uid, err = require_uid(payload)
    if err:
        return err

    if operation == 'update':
        updates = {k: v for k, v in payload.items() if k != 'uid'}
        if not updates:
            return error_response('No fields provided for update')
        try:
            track_repository.update_goal_by_uid(uid, updates)
        except Exception:
            logger.exception("Sync update goal error")
            return error_response('Failed to update goal', 500)
        return jsonify(status='success')

    if operation == 'delete':
        try:
            track_repository.delete_goal_by_uid(uid)
        except Exception:
            logger.exception("Sync delete goal error")
            return error_response('Failed to delete goal', 500)
        return jsonify(status='success')

    return error_response('Unsupported operation')
