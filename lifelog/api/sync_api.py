from flask import request, jsonify
from datetime import datetime
import logging
from flask import request, jsonify, Blueprint
from lifelog.api.task_api import _filter_and_validate_task_data
from lifelog.api.auth import require_device_token
from lifelog.utils.db import task_repository, time_repository, track_repository

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')
logger = logging.getLogger(__name__)


# Helper to return JSON error response

def error_response(message: str, code: int = 400):
    return jsonify({'error': message}), code

# Parse JSON body once


def parse_sync_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response('Invalid JSON payload', 400)
    operation = data.get('operation')
    if operation not in {'create', 'update', 'delete'}:
        return None, error_response('Invalid operation', 400)
    payload = data.get('data')
    if not isinstance(payload, dict):
        return None, error_response('Invalid data payload', 400)
    return {'operation': operation, 'payload': payload}, None

# Identify existing record by uid or id for any repository:
# Returns (identifier_type, identifier_value, existing_obj) or error response.


def identify_record(repo_get_by_uid, repo_get_by_id, payload: dict):
    """
    repo_get_by_uid: function(uid)->object or None
    repo_get_by_id: function(id)->object or None
    payload: dict containing possible 'uid' or 'id'
    Returns (obj, identifier_field, identifier_value) or (None, response)
    """
    if 'uid' in payload:
        uid_val = payload.get('uid')
        obj = repo_get_by_uid(uid_val)
        if not obj:
            return None, error_response('Record not found for given uid', 404)
        return obj, 'uid', uid_val
    elif 'id' in payload:
        try:
            rid = payload.get('id')
            # optionally ensure integer
            rid_int = int(rid)
        except Exception:
            return None, error_response('Invalid id in payload', 400)
        obj = repo_get_by_id(rid_int)
        if not obj:
            return None, error_response('Record not found for given id', 404)
        return obj, 'id', rid_int
    else:
        return None, error_response('No identifier provided', 400)

# Validate ISO datetime string


def validate_iso(field_name: str, value):
    if not isinstance(value, str):
        return None, error_response(f'Field "{field_name}" must be ISO-format string', 400)
    try:
        datetime.fromisoformat(value)
    except Exception as e:
        return None, error_response(f'Invalid "{field_name}" timestamp: {e}', 400)
    return value, None

# Validate integer field in payload


def parse_int_field(field_name: str, payload: dict, min_val=None, max_val=None):
    if field_name not in payload:
        return None, None
    v = payload.get(field_name)
    if v is None:
        return None, None
    try:
        iv = int(v)
    except Exception:
        return None, error_response(f'Field "{field_name}" must be integer', 400)
    if min_val is not None and iv < min_val:
        return None, error_response(f'Field "{field_name}" must be >= {min_val}', 400)
    if max_val is not None and iv > max_val:
        return None, error_response(f'Field "{field_name}" must be <= {max_val}', 400)
    return iv, None

# Validate float field


def parse_float_field(field_name: str, payload: dict, min_val=None):
    if field_name not in payload:
        return None, None
    v = payload.get(field_name)
    if v is None:
        return None, None
    try:
        fv = float(v)
    except Exception:
        return None, error_response(f'Field "{field_name}" must be number', 400)
    if min_val is not None and fv < min_val:
        return None, error_response(f'Field "{field_name}" must be >= {min_val}', 400)
    return fv, None


@sync_bp.route('/<table>', methods=['POST'])
@require_device_token
def handle_sync(table: str):
    req, error = parse_sync_request()
    if error:
        return error
    operation = req['operation']
    payload = req['payload']

    # Dispatch by table name
    if table == 'tasks':
        return handle_sync_tasks(operation, payload)
    elif table == 'time_history':
        return handle_sync_time(operation, payload)
    elif table == 'trackers':
        return handle_sync_trackers(operation, payload)
    elif table == 'goals':
        return handle_sync_goals(operation, payload)
    else:
        return error_response('Invalid table for sync', 400)


def handle_sync_tasks(operation: str, payload: dict):
    """
    Handle sync for 'tasks' table.
    operation in {'create','update','delete'}.
    payload: dict containing fields, including identifier for update/delete.
    """
    # For create, use partial=False to require fields
    if operation == 'create':
        # Reuse Task validation logic
        validated, error = _filter_and_validate_task_data(
            payload, partial=False)
        if error:
            return error  # returns (Response, code)
        try:
            task_repository.add_task(validated)
        except Exception:
            logger.exception("Sync create task error")
            return error_response('Failed to create task', 500)
        return jsonify({'status': 'success'}), 200

    # For update/delete, first identify existing record
    # Use identify_record helper: repo_get_by_uid, repo_get_by_id
    def repo_get_by_uid(uid):
        tasks = task_repository.query_tasks(uid=uid, show_completed=True)
        return tasks[0] if tasks else None

    def repo_get_by_id(tid):
        return task_repository.get_task_by_id(tid)

    identified, err = identify_record(repo_get_by_uid, repo_get_by_id, payload)
    if err:
        return err  # (Response, code)
    existing_obj, id_field, id_value = identified

    if operation == 'update':
        # Prepare updates: drop identifier fields
        updates_raw = {k: v for k,
                       v in payload.items() if k not in ('id', 'uid')}
        if not updates_raw:
            return error_response('No fields provided for update', 400)
        # Validate with partial=True
        validated_updates, error = _filter_and_validate_task_data(
            updates_raw, partial=True)
        if error:
            return error  # e.g. (Response,400)
        if not validated_updates:
            return error_response('No valid fields provided for update', 400)
        try:
            # Use repository update by uid or id
            if id_field == 'uid':
                task_repository.update_task_by_uid(id_value, validated_updates)
            else:
                task_repository.update_task(id_value, validated_updates)
        except Exception:
            logger.exception("Sync update task error")
            return error_response('Failed to update task', 500)
        return jsonify({'status': 'success'}), 200

    elif operation == 'delete':
        try:
            if id_field == 'uid':
                task_repository.delete_task_by_uid(id_value)
            else:
                task_repository.delete_task(id_value)
        except Exception:
            logger.exception("Sync delete task error")
            return error_response('Failed to delete task', 500)
        return jsonify({'status': 'success'}), 200

    else:
        # Shouldn’t reach: operation validated earlier
        return error_response('Unsupported operation', 400)


def handle_sync_time(operation: str, payload: dict):
    if operation == 'create':
        # For historical entries: ensure required fields exist, e.g. 'start'
        # Let's assume payload may include start, end, category, etc.
        # Ideally repository layer has validation; here minimally check 'start'
        start_val = payload.get('start')
        if start_val is None:
            return error_response('Missing "start" for create', 400)
        # Validate ISO
        start_iso, err = validate_iso('start', start_val)
        if err:
            return err
        # If 'end' provided, validate ISO
        end_val = payload.get('end')
        if end_val is not None:
            end_iso, err2 = validate_iso('end', end_val)
            if err2:
                return err2
        try:
            # Decide which repository method: add_time_entry for historical if end provided,
            # or start_time_entry if only start? For sync, assume historical:
            new_entry = time_repository.add_time_entry(payload)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync create time entry error")
            return error_response('Failed to create time entry', 500)
        return jsonify({'status': 'success'}), 200

    # For update/delete: identify record
    def repo_get_by_uid(uid): return time_repository.get_time_log_by_uid(uid)

    def repo_get_by_id(tid):
        # You need a get_time_log_by_id; if not existing, implement a small helper:
        return time_repository.get_time_log_by_uid(time_repository.get_time_log_by_id(tid).uid) \
            if hasattr(time_repository, 'get_time_log_by_id') else None
        # If repository lacks get_by_id, you can query SQLite directly or extend repo.
    identified, err = identify_record(
        repo_get_by_uid, time_repository.get_time_log_by_id, payload)
    if err:
        return err
    existing_obj, id_field, id_value = identified

    if operation == 'update':
        updates_raw = {k: v for k,
                       v in payload.items() if k not in ('id', 'uid')}
        if not updates_raw:
            return error_response('No fields provided for update', 400)
        # Validate date fields in updates_raw
        for date_field in ('start', 'end'):
            if date_field in updates_raw and updates_raw[date_field] is not None:
                val = updates_raw[date_field]
                iso_val, err2 = validate_iso(date_field, val)
                if err2:
                    return err2
                updates_raw[date_field] = iso_val
        # Possibly validate numeric fields: duration_minutes, distracted_minutes
        # If repository.update_time_log_by_uid handles validation, skip here; else:
        if 'duration_minutes' in updates_raw:
            try:
                updates_raw['duration_minutes'] = float(
                    updates_raw['duration_minutes'])
            except Exception:
                return error_response('Field "duration_minutes" must be numeric', 400)
        if 'distracted_minutes' in updates_raw:
            try:
                updates_raw['distracted_minutes'] = float(
                    updates_raw['distracted_minutes'])
            except Exception:
                return error_response('Field "distracted_minutes" must be numeric', 400)
        try:
            if id_field == 'uid':
                time_repository.update_time_log_by_uid(id_value, updates_raw)
            else:
                # If repository supports update_time_entry by id:
                time_repository.update_time_entry(id_value, **updates_raw)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync update time entry error")
            return error_response('Failed to update time entry', 500)
        return jsonify({'status': 'success'}), 200

    elif operation == 'delete':
        try:
            if id_field == 'uid':
                time_repository.delete_time_log_by_uid(id_value)
            else:
                # If repository supports delete_time_entry:
                time_repository.delete_time_entry(id_value)
        except Exception:
            logger.exception("Sync delete time entry error")
            return error_response('Failed to delete time entry', 500)
        return jsonify({'status': 'success'}), 200

    else:
        return error_response('Unsupported operation', 400)


def handle_sync_time(operation: str, payload: dict):
    # CREATE: historical entry
    if operation == 'create':
        # Minimal validation: require 'start'
        start_val = payload.get('start')
        if start_val is None:
            return error_response('Missing "start" for create', 400)
        start_iso, err = validate_iso('start', start_val)
        if err:
            return err
        end_val = payload.get('end')
        if end_val is not None:
            end_iso, err2 = validate_iso('end', end_val)
            if err2:
                return err2
        try:
            time_repository.add_time_entry(payload)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync create time entry error")
            return error_response('Failed to create time entry', 500)
        return jsonify({'status': 'success'}), 200

    # Identify existing time entry
    def repo_get_by_uid(uid):
        return time_repository.get_time_log_by_uid(uid)

    def repo_get_by_id(tid):
        # Assuming time_repository.get_time_log_by_id exists
        return time_repository.get_time_log_by_id(tid)
    identified, err = identify_record(repo_get_by_uid, repo_get_by_id, payload)
    if err:
        return err
    existing_obj, id_field, id_value = identified

    if operation == 'update':
        updates_raw = {k: v for k,
                       v in payload.items() if k not in ('id', 'uid')}
        if not updates_raw:
            return error_response('No fields provided for update', 400)
        # Validate date fields
        for df in ('start', 'end'):
            if df in updates_raw and updates_raw[df] is not None:
                iso_val, err2 = validate_iso(df, updates_raw[df])
                if err2:
                    return err2
                updates_raw[df] = iso_val
        # Validate numeric fields if needed
        if 'duration_minutes' in updates_raw:
            try:
                updates_raw['duration_minutes'] = float(
                    updates_raw['duration_minutes'])
            except Exception:
                return error_response('Field "duration_minutes" must be numeric', 400)
        if 'distracted_minutes' in updates_raw:
            try:
                updates_raw['distracted_minutes'] = float(
                    updates_raw['distracted_minutes'])
            except Exception:
                return error_response('Field "distracted_minutes" must be numeric', 400)
        try:
            if id_field == 'uid':
                time_repository.update_time_log_by_uid(id_value, updates_raw)
            else:
                time_repository.update_time_entry(id_value, **updates_raw)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync update time entry error")
            return error_response('Failed to update time entry', 500)
        return jsonify({'status': 'success'}), 200

    elif operation == 'delete':
        try:
            if id_field == 'uid':
                time_repository.delete_time_log_by_uid(id_value)
            else:
                time_repository.delete_time_entry(id_value)
        except Exception:
            logger.exception("Sync delete time entry error")
            return error_response('Failed to delete time entry', 500)
        return jsonify({'status': 'success'}), 200

    else:
        return error_response('Unsupported operation', 400)


def handle_sync_trackers(operation: str, payload: dict):
    # CREATE
    if operation == 'create':
        try:
            new_tracker = track_repository.add_tracker(payload)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync create tracker error")
            return error_response('Failed to create tracker', 500)
        return jsonify({'status': 'success'}), 200

    # Identify existing
    def repo_get_by_uid(uid):
        return track_repository.get_tracker_by_uid(uid)

    def repo_get_by_id(tid):
        return track_repository.get_tracker_by_id(tid)
    identified, err = identify_record(repo_get_by_uid, repo_get_by_id, payload)
    if err:
        return err
    existing_obj, id_field, id_value = identified

    if operation == 'update':
        updates_raw = {k: v for k,
                       v in payload.items() if k not in ('id', 'uid')}
        if not updates_raw:
            return error_response('No fields provided for update', 400)
        try:
            updated = track_repository.update_tracker(
                existing_obj.id, updates_raw)
            if not updated:
                return error_response('Tracker not found or update failed', 400)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync update tracker error")
            return error_response('Failed to update tracker', 500)
        return jsonify({'status': 'success'}), 200

    elif operation == 'delete':
        try:
            track_repository.delete_tracker(existing_obj.id)
        except Exception:
            logger.exception("Sync delete tracker error")
            return error_response('Failed to delete tracker', 500)
        return jsonify({'status': 'success'}), 200

    else:
        return error_response('Unsupported operation', 400)


def handle_sync_goals(operation: str, payload: dict):
    # CREATE: payload must include tracker_id
    if operation == 'create':
        # Ensure tracker_id in payload
        tid = payload.get('tracker_id')
        if tid is None:
            return error_response('Missing tracker_id for goal create', 400)
        try:
            new_goal = track_repository.add_goal(int(tid), payload)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync create goal error")
            return error_response('Failed to create goal', 500)
        return jsonify({'status': 'success'}), 200

    # Identify existing goal
    def repo_get_by_uid(uid):
        return track_repository.get_goal_by_uid(uid)

    def repo_get_by_id(gid):
        return track_repository.get_goal_by_id(gid)
    identified, err = identify_record(repo_get_by_uid, repo_get_by_id, payload)
    if err:
        return err
    existing_obj, id_field, id_value = identified

    if operation == 'update':
        updates_raw = {k: v for k,
                       v in payload.items() if k not in ('id', 'uid')}
        if not updates_raw:
            return error_response('No fields provided for update', 400)
        # Inject kind from existing if not provided
        updates_raw.setdefault('kind', existing_obj.kind)
        try:
            updated = track_repository.update_goal(
                existing_obj.id, updates_raw)
            if not updated:
                return error_response('Goal not found or update failed', 400)
        except ValueError as ve:
            return error_response(str(ve), 400)
        except Exception:
            logger.exception("Sync update goal error")
            return error_response('Failed to update goal', 500)
        return jsonify({'status': 'success'}), 200

    elif operation == 'delete':
        try:
            track_repository.delete_goal(existing_obj.id)
        except Exception:
            logger.exception("Sync delete goal error")
            return error_response('Failed to delete goal', 500)
        return jsonify({'status': 'success'}), 200

    else:
        return error_response('Unsupported operation', 400)
