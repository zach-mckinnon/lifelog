# api/auth.py
from functools import wraps
from flask import request, jsonify
import lifelog.config.config_manager as cf


def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = cf.load_config()
        api_config = config.get('api', {})

        # Get API key from header
        api_key = request.headers.get('X-API-Key')

        if not api_key or api_key != api_config.get('key'):
            return jsonify({'error': 'Invalid API key'}), 401

        return f(*args, **kwargs)
    return decorated_function
