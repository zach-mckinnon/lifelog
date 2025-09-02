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


def _require_host_mode():
    if not is_host_server():
        error('Endpoint only available on host', 403)


def _get_tracker_or_404(uid: str):
    t = track_repository.get_tracker_by_uid(uid)
    if not t:
        error('Tracker not found', 404)
    return t


@trackers_bp.route('/', methods=['GET'])
@require_device_token
@debug_api
def list_trackers():
    filters = {}
    title_contains = request.args.get('title_contains')
    if title_contains:
        filters['title_contains'] = title_contains
    category = request.args.get('category')
    if category:
        filters['category'] = category

    trackers = track_repository.get_all_trackers(**filters)

    uid = request.args.get('uid')
    if uid:
        trackers = [t for t in trackers if t.uid == uid]

    return jsonify([t.to_dict() for t in trackers]), 200


@trackers_bp.route('/', methods=['POST'])
@require_device_token
@debug_api
def create_tracker():
    data = parse_json()
    title = data.get('title')
    if not isinstance(title, str) or not title.strip():
        error('Missing or invalid "title"', 400)
    ttype = data.get('type')
    if not isinstance(ttype, str) or not ttype.strip():
        error('Missing or invalid "type"', 400)

    try:
        new = track_repository.add_tracker(data)
        return jsonify(new.to_dict()), 201
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        # TODO: Add more specific exception handling for better debugging
        logger.exception("Failed to create tracker")
        error('Failed to create tracker', 500)


@trackers_bp.route('/uid/<string:uid>', methods=['GET'])
@require_device_token
@debug_api
def get_tracker_by_uid(uid):
    t = _get_tracker_or_404(uid)
    return jsonify(t.to_dict()), 200


@trackers_bp.route('/uid/<string:uid>', methods=['PUT'])
@require_device_token
@debug_api
def update_tracker_by_uid(uid):
    _require_host_mode()
    t = _get_tracker_or_404(uid)

    data = parse_json()
    if 'title' in data:
        if not isinstance(data['title'], str) or not data['title'].strip():
            error('Field "title" must be non-empty string', 400)
    if 'type' in data:
        if not isinstance(data['type'], str) or not data['type'].strip():
            error('Field "type" must be non-empty string', 400)
    for fld in ('category', 'tags', 'notes'):
        if fld in data and data[fld] is not None and not isinstance(data[fld], str):
            error(f'Field "{fld}" must be a string', 400)

    try:
        updated = track_repository.update_tracker(t.id, data)
        return jsonify(updated.to_dict()), 200
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to update tracker")
        error('Failed to update tracker', 500)


@trackers_bp.route('/uid/<string:uid>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_tracker_by_uid(uid):
    _require_host_mode()
    t = _get_tracker_or_404(uid)
    try:
        ok = track_repository.delete_tracker(t.id)
        if not ok:
            error('Delete failed', 400)
        return jsonify({'status': 'success'}), 200
    except Exception:
        logger.exception("Failed to delete tracker")
        error('Failed to delete tracker', 500)


@trackers_bp.route('/uid/<string:tracker_uid>/entries', methods=['GET'])
@require_device_token
@debug_api
def list_tracker_entries(tracker_uid):
    t = _get_tracker_or_404(tracker_uid)
    entries = track_repository.get_entries_for_tracker(t.id)
    return jsonify([e.to_dict() for e in entries]), 200


@trackers_bp.route('/uid/<string:tracker_uid>/entries', methods=['POST'])
@require_device_token
@debug_api
def add_tracker_entry_api(tracker_uid):
    t = _get_tracker_or_404(tracker_uid)

    data = parse_json()
    ts = data.get('timestamp')
    val = data.get('value')
    if ts is None or val is None:
        error('Missing "timestamp" or "value"', 400)
    validate_iso('timestamp', ts)
    try:
        val_f = float(val)
    except Exception:
        error(f'Invalid "value": {val}', 400)

    try:
        entry = track_repository.add_tracker_entry(t.id, ts, val_f)
        return jsonify(entry.to_dict()), 201
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to add tracker entry")
        error('Failed to add entry', 500)


@trackers_bp.route('/uid/<string:tracker_uid>/goals', methods=['GET'])
@require_device_token
@debug_api
def list_goals_for_tracker(tracker_uid):
    t = _get_tracker_or_404(tracker_uid)
    goals = track_repository.get_goals_for_tracker(t.id)
    return jsonify([g.to_dict() for g in goals]), 200


@trackers_bp.route('/uid/<string:tracker_uid>/goals', methods=['POST'])
@require_device_token
@debug_api
def create_goal_for_tracker(tracker_uid):
    t = _get_tracker_or_404(tracker_uid)
    data = parse_json()
    try:
        new = track_repository.add_goal(t.id, data)
        return jsonify(new.to_dict()), 201
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to create goal")
        error('Failed to create goal', 500)


@trackers_bp.route('/goals/uid/<string:uid>', methods=['GET'])
@require_device_token
@debug_api
def get_goal_by_uid(uid):
    g = track_repository.get_goal_by_uid(uid)
    if not g:
        error('Goal not found', 404)
    return jsonify(g.to_dict()), 200


@trackers_bp.route('/goals/uid/<string:uid>', methods=['PUT'])
@require_device_token
@debug_api
def update_goal_by_uid(uid):
    _require_host_mode()
    g = track_repository.get_goal_by_uid(uid)
    if not g:
        error('Goal not found', 404)

    data = parse_json()
    data.setdefault('kind', g.kind)
    try:
        updated = track_repository.update_goal(g.id, data)
        return jsonify(updated.to_dict()), 200
    except ValueError as ve:
        error(str(ve), 400)
    except Exception:
        logger.exception("Failed to update goal")
        error('Failed to update goal', 500)


@trackers_bp.route('/goals/uid/<string:uid>', methods=['DELETE'])
@require_device_token
@debug_api
def delete_goal_by_uid(uid):
    _require_host_mode()
    g = track_repository.get_goal_by_uid(uid)
    if not g:
        error('Goal not found', 404)
    try:
        ok = track_repository.delete_goal(g.id)
        if not ok:
            error('Delete failed', 400)
        return jsonify({'status': 'success'}), 200
    except Exception:
        logger.exception("Failed to delete goal")
        error('Failed to delete goal', 500)
