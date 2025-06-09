# lifelog/api/track_api.py

from flask import request, jsonify, Blueprint
from lifelog.api.auth import require_device_token
from lifelog.api.errors import debug_api
from lifelog.utils.db import track_repository
from lifelog.config.config_manager import is_host_server

trackers_bp = Blueprint('trackers', __name__, url_prefix='/trackers')


# ───────────────────────────────────────────────────────────────────────────────
# TRACKER ENDPOINTS
# ───────────────────────────────────────────────────────────────────────────────

@trackers_bp.route('/', methods=['GET'])
@require_device_token
@debug_api
def list_trackers():
    """
    GET /trackers?uid=<uid>&title_contains=…&category=…
    Returns a list of trackers (local‐merged). In client mode, pushes & pulls first.
    """
    uid = request.args.get('uid')
    title_contains = request.args.get('title_contains')
    category = request.args.get('category')

    # Pass these filters into repository
    trackers = track_repository.get_all_trackers(
        title_contains=title_contains,
        category=category
    )

    if uid:
        # If someone asked specifically by uid, filter the returned list
        trackers = [t for t in trackers if t.uid == uid]

    return jsonify([t.__dict__ for t in trackers]), 200


@trackers_bp.route('/', methods=['POST'])
@require_device_token
@debug_api
def create_tracker():
    """
    POST /trackers
    Body: JSON with at least { "title":"…", "type":"int"|"float"|"bool"|"str", ... }
    In CLIENT mode: inserts locally, queues “create” to /sync/trackers, returns created tracker.
    In HOST mode: inserts directly, returns created tracker.
    """
    data = request.json or {}
    try:
        new_tracker = track_repository.add_tracker(data)
        return jsonify(new_tracker.__dict__), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to create tracker: {e}'}), 400


@trackers_bp.route('/<int:tracker_id>', methods=['GET'])
@require_device_token
@debug_api
def get_tracker(tracker_id: int):
    """
    GET /trackers/<tracker_id>
    Returns one tracker by numeric ID. In client mode, pushes & pulls first.
    """
    tracker = track_repository.get_tracker_by_id(tracker_id)
    if not tracker:
        return jsonify({'error': 'Tracker not found'}), 404
    return jsonify(tracker.__dict__), 200


@trackers_bp.route('/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_tracker_by_uid(uid_val: str):
    """
    GET /trackers/uid/<uid>
    Returns one tracker by global UID. Push/pull first if client; direct if host.
    """
    tracker = track_repository.get_tracker_by_uid(uid_val)
    if not tracker:
        return jsonify({'error': 'Tracker not found'}), 404
    return jsonify(tracker.__dict__), 200


@trackers_bp.route('/<int:tracker_id>', methods=['PUT'])
@require_device_token
@debug_api
def update_tracker_api(tracker_id: int):
    """
    PUT /trackers/<tracker_id>
    Body: JSON of fields to update (partial).
    In CLIENT mode: updates locally, queues “update” by uid, returns updated tracker.
    In HOST mode: updates directly, returns updated tracker.
    """
    data = request.json or {}
    try:
        updated = track_repository.update_tracker(tracker_id, data)
        if not updated:
            return jsonify({'error': 'Tracker not found or update failed'}), 400
        return jsonify(updated.__dict__), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to update tracker: {e}'}), 400


@trackers_bp.route('/uid/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_tracker_by_uid_api(uid_val: str):
    """
    PUT /trackers/uid/<uid>
    Body: JSON of fields to update (partial). Host‐only.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    data = request.json or {}
    try:
        # Fetch the local row’s numeric ID first
        tracker = track_repository.get_tracker_by_uid(uid_val)
        if not tracker:
            return jsonify({'error': 'Tracker not found'}), 404

        updated = track_repository.update_tracker(tracker.id, data)
        return jsonify(updated.__dict__), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to update tracker: {e}'}), 400


@trackers_bp.route('/<int:tracker_id>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_tracker_api(tracker_id: int):
    """
    DELETE /trackers/<tracker_id>
    In CLIENT mode: deletes locally, queues “delete” by uid, returns success.
    In HOST mode: deletes directly, returns success.
    """
    try:
        success = track_repository.delete_tracker(tracker_id)
        if not success:
            return jsonify({'error': 'Delete failed'}), 400
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to delete tracker: {e}'}), 400


@trackers_bp.route('/uid/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_tracker_by_uid_api(uid_val: str):
    """
    DELETE /trackers/uid/<uid>
    Host‐only: delete by global UID.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    try:
        tracker = track_repository.get_tracker_by_uid(uid_val)
        if not tracker:
            return jsonify({'error': 'Tracker not found'}), 404

        success = track_repository.delete_tracker(tracker.id)
        if not success:
            return jsonify({'error': 'Delete failed'}), 400
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to delete tracker: {e}'}), 400


# ───────────────────────────────────────────────────────────────────────────────
# TRACKER‐ENTRY ENDPOINTS (purely local; no sync)
# ───────────────────────────────────────────────────────────────────────────────

@trackers_bp.route('/<int:tracker_id>/entries', methods=['GET'])
@require_device_token
@debug_api
def list_tracker_entries(tracker_id: int):
    """
    GET /trackers/<tracker_id>/entries
    Lists all entries for that tracker (local-only).
    """
    entries = track_repository.get_entries_for_tracker(tracker_id)
    return jsonify([e.__dict__ for e in entries]), 200


@trackers_bp.route('/<int:tracker_id>/entries', methods=['POST'])
@require_device_token
@debug_api
def add_tracker_entry_api(tracker_id: int):
    """
    POST /trackers/<tracker_id>/entries
    Body: { "timestamp": "<ISO>", "value": <float> }
    Local‐only insert; no host sync.
    """
    data = request.json or {}
    ts = data.get("timestamp")
    val = data.get("value")

    if ts is None or val is None:
        return jsonify({'error': 'Missing timestamp or value'}), 400

    try:
        entry = track_repository.add_tracker_entry(tracker_id, ts, float(val))
        return jsonify(entry.__dict__), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to add entry: {e}'}), 400


# ───────────────────────────────────────────────────────────────────────────────
# GOAL ENDPOINTS
# ───────────────────────────────────────────────────────────────────────────────

@trackers_bp.route('/<int:tracker_id>/goals', methods=['GET'])
@require_device_token
@debug_api
def list_goals_for_tracker(tracker_id: int):
    """
    GET /trackers/<tracker_id>/goals
    Return all goals for that tracker. In CLIENT mode, push → pull first.
    """
    goals = track_repository.get_goals_for_tracker(tracker_id)
    return jsonify([g.__dict__ for g in goals]), 200


@trackers_bp.route('/<int:tracker_id>/goals', methods=['POST'])
@require_device_token
@debug_api
def create_goal_for_tracker(tracker_id: int):
    data = request.json or {}
    try:
        new_goal = track_repository.add_goal(tracker_id, data)
        return jsonify(new_goal.__dict__), 201

    except ValueError as ve:
        # If validation fails, send 400 + explanatory message
        return jsonify({'error': str(ve)}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to create goal: {e}'}), 500


@trackers_bp.route('/goals/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_goal_by_uid_api(uid_val: str):
    """
    GET /trackers/goals/uid/<uid>
    Fetch one goal by global UID. In CLIENT mode: push → pull → upsert → return.
    In HOST mode: direct local SELECT.
    """
    goal = track_repository.get_goal_by_uid(uid_val)
    if not goal:
        return jsonify({'error': 'Goal not found'}), 404
    return jsonify(goal.__dict__), 200


@trackers_bp.route('/goals/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_goal_by_uid_api(uid_val: str):
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    data = request.json or {}

    # 1) Fetch the existing goal
    goal = track_repository.get_goal_by_uid(uid_val)
    if not goal:
        return jsonify({'error': 'Goal not found'}), 404

    # 2) Inject the kind so that update_goal can route to the correct detail table
    data['kind'] = goal.kind

    try:
        # 3) Now update_goal has everything it needs
        updated = track_repository.update_goal(goal.id, data)
        return jsonify(updated.__dict__), 200

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400

    except Exception as e:
        return jsonify({'error': f'Failed to update goal: {e}'}), 500


@trackers_bp.route('/goals/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_goal_by_uid_api(uid_val: str):
    """
    DELETE /trackers/goals/<uid>
    Host-only endpoint. Deletes goal WHERE uid = ?.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    try:
        goal = track_repository.get_goal_by_uid(uid_val)
        if not goal:
            return jsonify({'error': 'Goal not found'}), 404

        success = track_repository.delete_goal(goal.id)
        if not success:
            return jsonify({'error': 'Delete failed'}), 400
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to delete goal: {e}'}), 400
