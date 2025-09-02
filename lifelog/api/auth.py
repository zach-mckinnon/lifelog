import secrets
import string
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from lifelog.utils.db import get_connection

auth_bp = Blueprint('auth', __name__)

PAIRING_EXPIRY_MINUTES = 5


def require_device_token(f):
    from functools import wraps
    from flask import request, jsonify
    from lifelog.utils.db import get_connection

    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Device-Token')
        if not token:
            return jsonify({'error': 'Missing device token'}), 401
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT id FROM api_devices WHERE device_token = ?", (token,))
            if not cur.fetchone():
                return jsonify({'error': 'Invalid or unregistered device'}), 401
        return f(*args, **kwargs)
    return decorated_function


def generate_code(length=8):  # use 8 chars for security
    import secrets
    import string
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@auth_bp.route('/api/pair/start', methods=['POST'])
def start_pairing():
    from datetime import datetime, timedelta
    data = request.get_json() or {}
    device_name = data.get('device_name', 'Unknown Device')
    code = generate_code()
    expires_at = (datetime.now() +
                  timedelta(minutes=PAIRING_EXPIRY_MINUTES)).isoformat()
    # Remove expired codes before inserting new
    with get_connection() as conn:
        conn.execute("DELETE FROM api_pairing_codes WHERE expires_at < ?",
                     (datetime.now().isoformat(),))
        # Loop until a unique code is found (rare collision)
        while True:
            cur = conn.execute(
                "SELECT 1 FROM api_pairing_codes WHERE code = ?", (code,))
            if not cur.fetchone():
                break
            code = generate_code()
        conn.execute("INSERT INTO api_pairing_codes (code, expires_at, device_name) VALUES (?, ?, ?)",
                     (code, expires_at, device_name))
        conn.commit()
    return jsonify({'pairing_code': code, 'expires_in': PAIRING_EXPIRY_MINUTES * 60})


@auth_bp.route('/api/pair/complete', methods=['POST'])
def complete_pairing():
    from datetime import datetime
    data = request.get_json() or {}
    code = data.get('pairing_code')
    device_name = data.get('device_name', 'Unknown Device')
    with get_connection() as conn:
        # Clean up expired codes
        conn.execute("DELETE FROM api_pairing_codes WHERE expires_at < ?",
                     (datetime.now().isoformat(),))
        cur = conn.execute(
            "SELECT 1 FROM api_devices WHERE device_name = ?", (device_name,))
        if cur.fetchone():
            return jsonify({'error': 'Device name already registered'}), 400
        cur = conn.execute(
            "SELECT expires_at FROM api_pairing_codes WHERE code = ?", (code,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Invalid code'}), 400
        expires_at = datetime.fromisoformat(row[0])
        if expires_at < datetime.now():
            conn.execute(
                "DELETE FROM api_pairing_codes WHERE code = ?", (code,))
            conn.commit()
            return jsonify({'error': 'Code expired'}), 400
        # Generate device token, add to devices table
        import secrets
        token = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO api_devices (device_name, device_token) VALUES (?, ?)", (device_name, token))
        conn.execute("DELETE FROM api_pairing_codes WHERE code = ?", (code,))
        conn.commit()
    return jsonify({'device_token': token})
