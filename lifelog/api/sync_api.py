from flask import request, jsonify, Blueprint
from lifelog.api.auth import require_api_key
from lifelog.utils.db import task_repository, time_repository, track_repository
from lifelog.utils.db.database_manager import update_record

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')


@sync_bp.route('/<table>', methods=['POST'])
@require_api_key
def handle_sync(table: str):
    data = request.json
    operation = data.get('operation')
    payload = data.get('data')

    if table == 'tasks':
        if operation == 'create':
            # Insert on server using the same uid
            task_repository.add_task(payload)

        elif operation == 'update':
            # If payload includes uid, update by uid; else fallback to numeric id
            if "uid" in payload:
                uid_val = payload.pop("uid")
                updates = {k: v for k, v in payload.items() if k != "id"}
                task_repository.update_task_by_uid(uid_val, updates)
            elif "id" in payload:
                tid = payload.pop("id")
                updates = {k: v for k, v in payload.items()}
                task_repository.update_task(tid, updates)
            else:
                return jsonify({"error": "No identifier provided for update"}), 400

        elif operation == 'delete':
            if "uid" in payload:
                task_repository.delete_task_by_uid(payload["uid"])
            elif "id" in payload:
                task_repository.delete_task(payload["id"])
            else:
                return jsonify({"error": "No identifier provided for delete"}), 400

    elif table == 'time_history':
        if operation == 'create':
            # Insert on server using the same uid
            time_repository.add_time_entry(payload)

        elif operation == 'update':
            # If payload includes uid, update by uid
            if "uid" in payload:
                uid_val = payload.pop("uid")
                updates = {k: v for k, v in payload.items() if k != "id"}
                time_repository.update_time_log_by_uid(uid_val, updates)
            elif "id" in payload:
                # fallback by numeric id (not recommended)—host can do UPDATE ... WHERE id = ?
                record_id = payload.pop("id")
                updates = {k: v for k, v in payload.items()}
                update_record("time_history", record_id, updates)
            else:
                return jsonify({"error": "No identifier provided for update"}), 400

        elif operation == 'delete':
            if "uid" in payload:
                time_repository.delete_time_log_by_uid(payload["uid"])
            elif "id" in payload:
                # fallback: delete by numeric id
                update_record("time_history", payload["id"], {"deleted": 1})
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
