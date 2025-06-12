# lifelog/api/track_api.py

from datetime import datetime
import logging
from flask import request, jsonify, Blueprint
from lifelog.api.auth import require_device_token
from lifelog.api.errors import debug_api, parse_json, error, validate_iso
from lifelog.utils.db import track_repository
from lifelog.config.config_manager import is_host_server

trackers_bp = Blueprint('trackers', __name__, url_prefix='/trackers')
logger = logging.getLogger(__name__)


def _get_tracker_or_404_by_id(tracker_id: int):
    """
    Fetch tracker by numeric ID or raise ApiError(404).
    """
    tracker = track_repository.get_tracker_by_id(tracker_id)
    if not tracker:
        error('Tracker not found', 404)
    return tracker


def _get_tracker_or_404_by_uid(uid_val: str):
    """
    Fetch tracker by global UID or raise ApiError(404).
    """
    tracker = track_repository.get_tracker_by_uid(uid_val)
    if not tracker:
        error('Tracker not found', 404)
    return tracker


def _require_host_mode():
    """
    Raise ApiError(403) if not host mode.
    """
    if not is_host_server():
        error('Endpoint only available on host', 403)


def _parse_list_filters(args):
    """
    Parse query params for list_trackers or raise ApiError.
    Supported filters: title_contains, category.
    """
    filters: dict = {}
    title_contains = args.get('title_contains')
    if title_contains:
        if not isinstance(title_contains, str):
            error('Invalid title_contains filter', 400)
        filters['title_contains'] = title_contains
    category = args.get('category')
    if category:
        if not isinstance(category, str):
            error('Invalid category filter', 400)
        filters['category'] = category
    # Note: uid handled separately in endpoint
    return filters


@trackers_bp.route('/', methods=['GET'])
@require_device_token
@debug_api
def list_trackers():
    """
    GET /trackers?uid=<uid>&title_contains=…&category=…
    """
    filters = _parse_list_filters(request.args)
    trackers = track_repository.get_all_trackers(
        title_contains=filters.get('title_contains'),
        category=filters.get('category')
    )
    # If uid filter provided, apply here
    uid = request.args.get('uid')
    if uid:
        if not isinstance(uid, str):
            error('Invalid uid filter', 400)
        trackers = [t for t in trackers if t.uid == uid]
    # Return JSON list
    return jsonify([t.to_dict() for t in trackers]), 200


@trackers_bp.route('/', methods=['POST'])
@require_device_token
@debug_api
def create_tracker():
    """
    POST /trackers
    Body: JSON with at least { "title":"…", "type":"int"|"float"|"bool"|"str", ... }
    """
    data = parse_json()  # raises ApiError if invalid JSON
    # Minimal required: title
    title = data.get('title')
    if not title or not isinstance(title, str) or not title.strip():
        error('Missing or invalid "title" field', 400)
    # 'type' is also required by repository; validate presence
    ttype = data.get('type')
    if not ttype or not isinstance(ttype, str) or not ttype.strip():
        error('Missing or invalid "type" field', 400)
    # Optionally other fields (category, tags, notes) can be strings if provided
    # Let repository handle defaults and further validation

    try:
        new_tracker = track_repository.add_tracker(data)
    except ValueError as ve:
        # validation failure in repository, e.g. missing required fields
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to create tracker")
        error('Failed to create tracker', 500)

    return jsonify(new_tracker.to_dict()), 201


@trackers_bp.route('/<int:tracker_id>', methods=['GET'])
@require_device_token
@debug_api
def get_tracker(tracker_id: int):
    """
    GET /trackers/<tracker_id>
    """
    tracker = _get_tracker_or_404_by_id(tracker_id)
    return jsonify(tracker.to_dict()), 200


@trackers_bp.route('/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_tracker_by_uid(uid_val: str):
    """
    GET /trackers/uid/<uid>
    """
    tracker = _get_tracker_or_404_by_uid(uid_val)
    return jsonify(tracker.to_dict()), 200


@trackers_bp.route('/<int:tracker_id>', methods=['PUT'])
@require_device_token
@debug_api
def update_tracker_api(tracker_id: int):
    """
    PUT /trackers/<tracker_id>
    Body: JSON partial fields.
    """
    _get_tracker_or_404_by_id(tracker_id)
    data = parse_json()
    # If data contains 'title', validate non-empty string
    if 'title' in data:
        title = data['title']
        if title is None or not isinstance(title, str) or not title.strip():
            error('Field "title" must be non-empty string', 400)
    # If data contains other fields, optionally validate types:
    if 'type' in data:
        ttype = data['type']
        if ttype is None or not isinstance(ttype, str) or not ttype.strip():
            error('Field "type" must be non-empty string', 400)
    # category/tags/notes if present must be strings or None
    for fld in ('category', 'tags', 'notes'):
        if fld in data:
            val = data[fld]
            if val is not None and not isinstance(val, str):
                error(f'Field "{fld}" must be a string', 400)
    try:
        updated = track_repository.update_tracker(tracker_id, data)
        if not updated:
            error('Tracker not found or update failed', 400)
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to update tracker")
        error('Failed to update tracker', 500)

    return jsonify(updated.to_dict()), 200


@trackers_bp.route('/uid/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_tracker_by_uid_api(uid_val: str):
    """
    PUT /trackers/uid/<uid>  Host-only.
    """
    _require_host_mode()
    tracker = _get_tracker_or_404_by_uid(uid_val)
    data = parse_json()
    # Similar validation as above
    if 'title' in data:
        title = data['title']
        if title is None or not isinstance(title, str) or not title.strip():
            error('Field "title" must be non-empty string', 400)
    if 'type' in data:
        ttype = data['type']
        if ttype is None or not isinstance(ttype, str) or not ttype.strip():
            error('Field "type" must be non-empty string', 400)
    for fld in ('category', 'tags', 'notes'):
        if fld in data:
            val = data[fld]
            if val is not None and not isinstance(val, str):
                error(f'Field "{fld}" must be a string', 400)
    try:
        updated = track_repository.update_tracker(tracker.id, data)
        if not updated:
            error('Tracker not found or update failed', 400)
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to update tracker by UID")
        error('Failed to update tracker', 500)

    return jsonify(updated.to_dict()), 200


@trackers_bp.route('/<int:tracker_id>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_tracker_api(tracker_id: int):
    """
    DELETE /trackers/<tracker_id>
    """
    _get_tracker_or_404_by_id(tracker_id)
    try:
        success = track_repository.delete_tracker(tracker_id)
        if not success:
            error('Delete failed', 400)
    except Exception:
        logger.exception("Failed to delete tracker")
        error('Failed to delete tracker', 500)
    return jsonify({'status': 'success'}), 200


@trackers_bp.route('/uid/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_tracker_by_uid_api(uid_val: str):
    """
    DELETE /trackers/uid/<uid>  Host-only.
    """
    _require_host_mode()
    tracker = _get_tracker_or_404_by_uid(uid_val)
    try:
        success = track_repository.delete_tracker(tracker.id)
        if not success:
            error('Delete failed', 400)
    except Exception:
        logger.exception("Failed to delete tracker by UID")
        error('Failed to delete tracker', 500)
    return jsonify({'status': 'success'}), 200


# ───────────────────────────────────────────────────────────────────────────────
# TRACKER‐ENTRY ENDPOINTS (purely local; no sync)
# ───────────────────────────────────────────────────────────────────────────────

@trackers_bp.route('/<int:tracker_id>/entries', methods=['GET'])
@require_device_token
@debug_api
def list_tracker_entries(tracker_id: int):
    """
    GET /trackers/<tracker_id>/entries
    """
    # Optionally ensure tracker exists, else return empty
    _get_tracker_or_404_by_id(tracker_id)
    entries = track_repository.get_entries_for_tracker(tracker_id)
    return jsonify([e.to_dict() for e in entries]), 200


@trackers_bp.route('/<int:tracker_id>/entries', methods=['POST'])
@require_device_token
@debug_api
def add_tracker_entry_api(tracker_id: int):
    """
    POST /trackers/<tracker_id>/entries
    Body: { "timestamp": "<ISO>", "value": <float> }
    """
    _get_tracker_or_404_by_id(tracker_id)
    data = parse_json()
    ts = data.get("timestamp")
    val = data.get("value")
    if ts is None or val is None:
        error('Missing timestamp or value', 400)
    # Validate timestamp
    validate_iso("timestamp", ts)
    # Validate value as float
    try:
        val_f = float(val)
    except Exception:
        error(f'Invalid "value": {val}', 400)
    try:
        entry = track_repository.add_tracker_entry(tracker_id, ts, val_f)
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to add tracker entry")
        error('Failed to add entry', 500)
    return jsonify(entry.to_dict()), 201


# ───────────────────────────────────────────────────────────────────────────────
# GOAL ENDPOINTS
# ───────────────────────────────────────────────────────────────────────────────

@trackers_bp.route('/<int:tracker_id>/goals', methods=['GET'])
@require_device_token
@debug_api
def list_goals_for_tracker(tracker_id: int):
    """
    GET /trackers/<tracker_id>/goals
    """
    _get_tracker_or_404_by_id(tracker_id)
    goals = track_repository.get_goals_for_tracker(tracker_id)
    return jsonify([g.to_dict() for g in goals]), 200


@trackers_bp.route('/<int:tracker_id>/goals', methods=['POST'])
@require_device_token
@debug_api
def create_goal_for_tracker(tracker_id: int):
    """
    POST /trackers/<tracker_id>/goals
    """
    _get_tracker_or_404_by_id(tracker_id)
    data = parse_json()
    # Repository will validate required fields (title, kind, etc.) and raise ValueError
    try:
        new_goal = track_repository.add_goal(tracker_id, data)
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to create goal")
        error('Failed to create goal', 500)
    return jsonify(new_goal.to_dict()), 201


@trackers_bp.route('/goals/uid/<string:uid_val>', methods=['GET'])
@require_device_token
@debug_api
def get_goal_by_uid_api(uid_val: str):
    """
    GET /trackers/goals/uid/<uid>
    """
    goal = track_repository.get_goal_by_uid(uid_val)
    if not goal:
        error('Goal not found', 404)
    return jsonify(goal.to_dict()), 200


@trackers_bp.route('/goals/<string:uid_val>', methods=['PUT'])
@require_device_token
@debug_api
def update_goal_by_uid_api(uid_val: str):
    """
    PUT /trackers/goals/<uid>  Host-only.
    """
    _require_host_mode()
    goal = track_repository.get_goal_by_uid(uid_val)
    if not goal:
        error('Goal not found', 404)
    data = parse_json()
    # Inject existing kind so repository routes detail correctly
    data['kind'] = goal.kind
    try:
        updated = track_repository.update_goal(goal.id, data)
        if not updated:
            error('Goal not found or update failed', 400)
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to update goal")
        error('Failed to update goal', 500)
    return jsonify(updated.to_dict()), 200


@trackers_bp.route('/goals/<string:uid_val>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_goal_by_uid_api(uid_val: str):
    """
    DELETE /trackers/goals/<uid>  Host-only.
    """
    _require_host_mode()
    goal = track_repository.get_goal_by_uid(uid_val)
    if not goal:
        error('Goal not found', 404)
    try:
        success = track_repository.delete_goal(goal.id)
        if not success:
            error('Delete failed', 400)
    except Exception:
        logger.exception("Failed to delete goal")
        error('Failed to delete goal', 500)
    return jsonify({'status': 'success'}), 200
