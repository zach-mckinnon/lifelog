from datetime import datetime
import logging
from flask import request, jsonify, Blueprint
from lifelog.api.auth import require_device_token
from lifelog.utils.db import task_repository, time_repository, track_repository
from lifelog.utils.db.database_manager import update_record
from lifelog.utils.db.models import get_task_fields

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')
logger = logging.getLogger(__name__)


@sync_bp.route('/<table>', methods=['POST'])
@require_device_token
def handle_sync(table: str):
    """
    Handle sync operations from client. Expects JSON: {operation: 'create'|'update'|'delete', data: {...}}.
    Allowed tables: tasks, time_history, trackers, goals.
    """
    json_payload = request.get_json()
    if not isinstance(json_payload, dict):
        return jsonify({'error': 'Invalid JSON payload'}), 400

    operation = json_payload.get('operation')
    payload = json_payload.get('data')
    if operation not in {'create', 'update', 'delete'}:
        return jsonify({'error': 'Invalid operation'}), 400
    if not isinstance(payload, dict):
        return jsonify({'error': 'Invalid data payload'}), 400
    if table == 'tasks':
        if operation == 'create':
            # Validate and filter payload
            allowed_fields = set(get_task_fields())
            extra = set(payload.keys()) - allowed_fields
            if extra:
                return jsonify({'error': f'Unknown field(s) for create: {", ".join(sorted(extra))}'}), 400
            # Required: title
            title = payload.get('title')
            if not title or not isinstance(title, str) or not title.strip():
                return jsonify({'error': 'Field "title" is required for create'}), 400
            # Validate other fields similarly (importance, due, etc.)
            # Example: importance
            if 'importance' in payload:
                try:
                    imp = int(payload['importance'])
                    if imp < 0 or imp > 5:
                        raise ValueError
                    payload['importance'] = imp
                except Exception:
                    return jsonify({'error': 'Field "importance" must be integer between 0 and 5'}), 400
            if 'due' in payload:
                due_val = payload['due']
                if due_val is not None:
                    if not isinstance(due_val, str):
                        return jsonify({'error': 'Field "due" must be ISO-format string'}), 400
                    try:
                        datetime.fromisoformat(due_val)
                    except Exception:
                        return jsonify({'error': 'Field "due" must be valid ISO datetime string'}), 400
            try:
                task_repository.add_task(payload)
            except Exception as e:
                logging.getLogger(__name__).error(
                    f"Sync create task error: {e}", exc_info=True)
                return jsonify({'error': 'Failed to create task'}), 500

        elif operation == 'update':
            # Determine identifier
            if "uid" in payload:
                uid_val = payload.get("uid")
                # Check existence
                existing = task_repository.query_tasks(
                    uid=uid_val, show_completed=True)
                if not existing:
                    return jsonify({'error': 'Task not found for given uid'}), 404
                updates_raw = {k: v for k,
                               v in payload.items() if k not in ('id', 'uid')}
                if not updates_raw:
                    return jsonify({'error': 'No fields provided for update'}), 400
                # Filter to allowed fields
                allowed_fields = set(get_task_fields())
                extra = set(updates_raw.keys()) - allowed_fields
                if extra:
                    return jsonify({'error': f'Unknown field(s) for update: {", ".join(sorted(extra))}'}), 400
                # Validate each field as in update_task_api
                updates = {}
                from datetime import datetime
                for key, val in updates_raw.items():
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
                        f"Sync update task UID={uid_val} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to update task'}), 500
            elif "id" in payload:
                tid = payload.get("id")
                # Check existence
                existing = task_repository.get_task_by_id(tid)
                if not existing:
                    return jsonify({'error': 'Task not found for given id'}), 404
                updates_raw = {k: v for k,
                               v in payload.items() if k != 'id'}
                if not updates_raw:
                    return jsonify({'error': 'No fields provided for update'}), 400
                # Filter and validate same as above
                allowed_fields = set(get_task_fields())
                extra = set(updates_raw.keys()) - allowed_fields
                if extra:
                    return jsonify({'error': f'Unknown field(s) for update: {", ".join(sorted(extra))}'}), 400
                updates = {}
                from datetime import datetime
                for key, val in updates_raw.items():
                    # (same validation logic as for uid branch)
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
                    task_repository.update_task(tid, updates)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync update task id={tid} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to update task'}), 500
            else:
                return jsonify({"error": "No identifier provided for update"}), 400

        elif operation == 'delete':
            if "uid" in payload:
                uid_val = payload.get("uid")
                existing = task_repository.query_tasks(
                    uid=uid_val, show_completed=True)
                if not existing:
                    return jsonify({'error': 'Task not found for given uid'}), 404
                try:
                    task_repository.delete_task_by_uid(uid_val)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync delete task UID={uid_val} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to delete task'}), 500
            elif "id" in payload:
                tid = payload.get("id")
                existing = task_repository.get_task_by_id(tid)
                if not existing:
                    return jsonify({'error': 'Task not found for given id'}), 404
                try:
                    task_repository.delete_task(tid)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync delete task id={tid} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to delete task'}), 500
            else:
                return jsonify({"error": "No identifier provided for delete"}), 400

    elif table == 'time_history':
        if operation == 'create':
            # Insert on server using the same uid
            try:
                time_repository.add_time_entry(payload)
            except Exception as e:
                logging.getLogger(__name__).error(
                    f"Sync create time_history error: {e}", exc_info=True)
                return jsonify({'error': 'Failed to create time entry'}), 500

        elif operation == 'update':
            if "uid" in payload:
                uid_val = payload.get("uid")
                existing = time_repository.get_time_log_by_uid(uid_val)
                if not existing:
                    return jsonify({'error': 'Time entry not found for given uid'}), 404
                updates_raw = {k: v for k,
                               v in payload.items() if k not in ('id', 'uid')}
                if not updates_raw:
                    return jsonify({'error': 'No fields provided for update'}), 400
                # Filter and validate fields according to time_history schema...
                try:
                    time_repository.update_time_log_by_uid(
                        uid_val, updates_raw)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync update time_history UID={uid_val} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to update time entry'}), 500
            elif "id" in payload:
                tid = payload.get("id")
                existing = time_repository.get_time_log_by_id(tid)
                if not existing:
                    return jsonify({'error': 'Time entry not found for given id'}), 404
                updates_raw = {k: v for k, v in payload.items() if k != 'id'}
                if not updates_raw:
                    return jsonify({'error': 'No fields provided for update'}), 400
                # Use generic update_record or repository update; assume update_record works:
                from lifelog.utils.db.database_manager import get_connection
                conn = get_connection()
                # Optionally filter columns to actual columns in time_history
                try:
                    # For simplicity, call repository if available; else:
                    update_record("time_history", tid, updates_raw)
                    conn.commit()
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync update time_history id={tid} error: {e}", exc_info=True)
                    conn.rollback()
                    return jsonify({'error': 'Failed to update time entry'}), 500
                finally:
                    conn.close()
            else:
                return jsonify({"error": "No identifier provided for update"}), 400

        elif operation == 'delete':
            if "uid" in payload:
                uid_val = payload.get("uid")
                existing = time_repository.get_time_log_by_uid(uid_val)
                if not existing:
                    return jsonify({'error': 'Time entry not found for given uid'}), 404
                try:
                    time_repository.delete_time_log_by_uid(uid_val)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync delete time_history UID={uid_val} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to delete time entry'}), 500
            elif "id" in payload:
                tid = payload.get("id")
                existing = time_repository.get_time_log_by_id(tid)
                if not existing:
                    return jsonify({'error': 'Time entry not found for given id'}), 404
                try:
                    # Actual DELETE
                    from lifelog.utils.db.database_manager import get_connection
                    conn = get_connection()
                    conn.execute(
                        "DELETE FROM time_history WHERE id = ?", (tid,))
                    conn.commit()
                except Exception as e:
                    logging.getLogger(__name__).error(
                        f"Sync delete time_history id={tid} error: {e}", exc_info=True)
                    return jsonify({'error': 'Failed to delete time entry'}), 500
                finally:
                    conn.close()
            else:
                return jsonify({"error": "No identifier provided for delete"}), 400
    elif table == 'trackers':
        if operation == 'create':
            # Insert on server using payload with uid
            track_repository.add_tracker(payload)

        elif operation == 'update':
            if "uid" in payload:
                uid_val = payload.pop("uid")
                updates = {k: v for k, v in payload.items() if k != "id"}
                # Host must update by uid
                tracker = track_repository.get_tracker_by_uid(uid_val)
                if tracker:
                    track_repository.update_tracker(tracker.id, updates)
            elif "id" in payload:
                # Fallback (not recommended if uid exists)
                tid = payload.pop("id")
                updates = {k: v for k, v in payload.items()}
                track_repository.update_tracker(tid, updates)
            else:
                return jsonify({"error": "No identifier provided for update"}), 400

        elif operation == 'delete':
            if "uid" in payload:
                tracker = track_repository.get_tracker_by_uid(payload["uid"])
                if tracker:
                    track_repository.delete_tracker(tracker.id)
            elif "id" in payload:
                track_repository.delete_tracker(payload["id"])
            else:
                return jsonify({"error": "No identifier provided for delete"}), 400

    elif table == 'goals':
        if operation == 'create':
            # payload must include tracker_id and uid
            track_repository.add_goal(payload["tracker_id"], payload)

        if operation == 'update':
            if "uid" in payload:
                uid_val = payload.pop("uid")
                updates = {k: v for k, v in payload.items() if k != "id"}
                goal = track_repository.get_goal_by_uid(uid_val)
                if goal:
                    # Inject the existing kind so update_goal can update the right detail table
                    updates['kind'] = goal.kind
                    track_repository.update_goal(goal.id, updates)

            elif "id" in payload:
                gid = payload.pop("id")
                updates = {k: v for k, v in payload.items()}
                # Fetch the goal to get its kind
                goal = track_repository.get_goal_by_id(gid)
                if goal:
                    updates['kind'] = goal.kind
                    track_repository.update_goal(gid, updates)
            else:
                return jsonify({"error": "No identifier provided for update"}), 400

        elif operation == 'delete':
            if "uid" in payload:
                goal = track_repository.get_goal_by_uid(payload["uid"])
                if goal:
                    track_repository.delete_goal(goal.id)
            elif "id" in payload:
                track_repository.delete_goal(payload["id"])
            else:
                return jsonify({"error": "No identifier provided for delete"}), 400

    return jsonify({'status': 'success'})
