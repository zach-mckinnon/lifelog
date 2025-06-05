# api/time_api.py
from flask import request, jsonify, Blueprint
from lifelog.utils.db import time_repository
from lifelog.api.auth import require_api_key

time_bp = Blueprint('time', __name__, url_prefix='/time')


@time_bp.route('/entries', methods=['GET'])
@require_api_key
def get_time_entries():
    since = request.args.get('since')  # ISO format date
    entries = time_repository.get_all_time_logs(since=since)
    return jsonify([entry.__dict__ for entry in entries])


@time_bp.route('/entries', methods=['POST'])
@require_api_key
def start_time_entry():
    data = request.json
    time_log = time_repository.start_time_entry(data)
    return jsonify(time_log.__dict__), 201


@time_bp.route('/entries/current', methods=['PUT'])
@require_api_key
def stop_time_entry():
    # Implementation to stop current timer
    return jsonify({'status': 'success'})
