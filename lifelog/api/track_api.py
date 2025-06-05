# api/track_api.py
from flask import request, jsonify, Blueprint
from lifelog.utils.db import track_repository
from lifelog.api.auth import require_api_key

trackers_bp = Blueprint('trackers', __name__, url_prefix='/trackers')


@trackers_bp.route('/', methods=['GET'])
@require_api_key
def list_trackers():
    trackers = track_repository.get_all_trackers()
    return jsonify([tracker.__dict__ for tracker in trackers])


@trackers_bp.route('/<int:tracker_id>/entries', methods=['POST'])
@require_api_key
def log_tracker_value(tracker_id):
    data = request.json
    value = data.get('value')
    # Implementation to log tracker value
    return jsonify({'status': 'success'}), 201
