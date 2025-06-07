# lifelog/api/time_api.py

from datetime import datetime
from flask import request, jsonify, Blueprint
from lifelog.api.errors import debug_api
from lifelog.api.auth import require_api_key
from lifelog.utils.db import time_repository
from lifelog.config.config_manager import is_host_server

time_bp = Blueprint('time', __name__, url_prefix='/time')


@time_bp.route('/entries', methods=['GET'])
@require_api_key
@debug_api
def list_time_entries():
    """
    GET /time/entries?since=<ISO>
    Returns all local time logs, optionally filtering by 'since'. In CLIENT mode,
    this will first pull new/updated logs from the host, upsert locally, then return.
    """
    since = request.args.get('since')  # ISO formatted date/time
    try:
        entries = time_repository.get_all_time_logs(since=since)
        return jsonify([entry.__dict__ for entry in entries]), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch entries: {e}'}), 500


@time_bp.route('/entries', methods=['POST'])
@require_api_key
@debug_api
def create_time_entry():
    """
    POST /time/entries
    Body: JSON payload of a new TimeLog, e.g.
      {
        "title": "Focused work",
        "start": "2025-06-05T14:00:00",
        "category": "work",
        "project": "api",
        "tags": "deep",
        "notes": "Starting sprint planning"
      }
    In CLIENT mode:
      • Assigns a new uid, inserts locally, queues sync to host.
    In HOST mode:
      • Inserts directly into SQLite (with a generated uid if missing).
    Returns the created TimeLog (with both numeric `id` and `uid`).
    """
    data = request.json or {}
    try:
        new_log = time_repository.start_time_entry(data)
        return jsonify(new_log.__dict__), 201
    except Exception as e:
        return jsonify({'error': f'Failed to start entry: {e}'}), 400


@time_bp.route('/entries/current', methods=['PUT'])
@require_api_key
@debug_api
def stop_time_entry():
    """
    PUT /time/entries/current
    Body: { "end": "<ISO-string>", "tags": "...", "notes": "..." }
    Stops the one active (end IS NULL) entry by updating end/duration (+ optional fields).
    In CLIENT mode:
      • Updates local row, queues a sync “update” by uid (full payload).
    In HOST mode:
      • Updates directly in SQLite.
    Returns the updated TimeLog.
    """
    data = request.json or {}
    if "end" not in data:
        return jsonify({'error': 'Missing "end" timestamp'}), 400

    try:
        end_dt = datetime.fromisoformat(data["end"])
    except Exception as e:
        return jsonify({'error': f'Invalid end timestamp: {e}'}), 400

    tags = data.get("tags")
    notes = data.get("notes")

    try:
        updated = time_repository.stop_active_time_entry(
            end_dt, tags=tags, notes=notes)
        return jsonify(updated.__dict__), 200
    except Exception as e:
        return jsonify({'error': f'Failed to stop entry: {e}'}), 400


@time_bp.route('/entries/uid/<string:uid_val>', methods=['GET'])
@require_api_key
@debug_api
def get_time_entry_by_uid(uid_val):
    """
    GET /time/entries/uid/<uid>
    Fetch a single TimeLog by global UID.
    In CLIENT mode:
      • Push pending local changes, then pull exactly that one record from host by uid.
      • Upsert locally, then return it.
    In HOST/DIRECT mode:
      • Return from SQLite WHERE uid = ?.
    """
    try:
        entry = time_repository.get_time_log_by_uid(uid_val)
        if not entry:
            return jsonify({'error': 'TimeLog not found'}), 404
        return jsonify(entry.__dict__), 200
    except Exception as e:
        return jsonify({'error': f'Failed to fetch entry: {e}'}), 500


@time_bp.route('/entries/<string:uid_val>', methods=['PUT'])
@require_api_key
@debug_api
def update_time_entry_by_uid(uid_val):
    """
    PUT /time/entries/<uid>
    Body: JSON payload of fields to update (partial), e.g. { "notes": "..." }.
    Only allowed on HOST (server) mode. Clients always use /entries/current or queue via sync.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    data = request.json or {}
    # Remove any attempt to override “id”
    data.pop("id", None)

    try:
        time_repository.update_time_log_by_uid(uid_val, data)
        updated = time_repository.get_time_log_by_uid(uid_val)
        if not updated:
            return jsonify({'error': 'TimeLog not found'}), 404
        return jsonify(updated.__dict__), 200
    except Exception as e:
        return jsonify({'error': f'Failed to update entry: {e}'}), 400


@time_bp.route('/entries/<string:uid_val>', methods=['DELETE'])
@require_api_key
@debug_api
def delete_time_entry_by_uid(uid_val):
    """
    DELETE /time/entries/<uid>
    Only allowed on HOST mode. Deletes the TimeLog row WHERE uid = ?.
    """
    if not is_host_server():
        return jsonify({'error': 'Endpoint only available on host'}), 403

    try:
        time_repository.delete_time_log_by_uid(uid_val)
        # Verify deletion
        if time_repository.get_time_log_by_uid(uid_val):
            return jsonify({'error': 'Delete failed'}), 400
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'error': f'Failed to delete entry: {e}'}), 400
