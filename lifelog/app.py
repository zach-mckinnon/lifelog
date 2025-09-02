import os
import logging
from flask import Flask, jsonify
from lifelog.api.task_api import tasks_bp
from lifelog.api.auth import auth_bp
from lifelog.api.time_api import time_bp
from lifelog.api.track_api import trackers_bp
from lifelog.api.sync_api import sync_bp
from lifelog.api.errors import register_error_handlers
from lifelog.config.config_manager import get_deployment_mode
from lifelog.utils.db import initialize_schema

# Flask optimizations for Raspberry Pi deployment
app = Flask(__name__)

# Production configuration for Pi
app.config.update(
    # Security
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', os.urandom(24)),
    
    # Performance optimizations for Pi
    SEND_FILE_MAX_AGE_DEFAULT=31536000,  # 1 year cache for static files
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max request size
    
    # Timeouts and limits for Pi hardware
    PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
    APPLICATION_ROOT='/',
    
    # Disable unnecessary features for API server
    EXPLAIN_TEMPLATE_LOADING=False,
    PRESERVE_CONTEXT_ON_EXCEPTION=False,
)

# Configure logging for Pi
if not app.debug:
    logging.basicConfig(level=logging.WARNING)  # Reduce log verbosity
    app.logger.setLevel(logging.WARNING)

initialize_schema()

app.register_blueprint(auth_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(time_bp)
app.register_blueprint(trackers_bp)
app.register_blueprint(sync_bp)

# Register error handlers
register_error_handlers(app)

# Add request optimization middleware for Pi
@app.before_request
def optimize_request():
    """Pi-specific request optimizations"""
    from flask import request
    # Reject oversized requests early to save Pi resources
    if request.content_length and request.content_length > app.config['MAX_CONTENT_LENGTH']:
        from flask import abort
        abort(413)  # Request Entity Too Large

@app.after_request
def optimize_response(response):
    """Pi-specific response optimizations"""
    # Add efficient caching headers for Pi
    if not response.cache_control.max_age:
        response.cache_control.max_age = 300  # 5 minute default cache
    
    # Compress response for slower Pi network
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.route('/api/health')
def health_check():
    return jsonify({
        "status": "ok",
        "version": "1.0",
        "mode": get_deployment_mode()
    }), 200


@app.route("/api/status")
def api_status():
    return "OK", 200


if __name__ == '__main__':
    # Production-optimized server settings for Raspberry Pi
    is_debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('FLASK_PORT', 5000))
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    
    # Pi-optimized server settings
    app.run(
        host=host,
        port=port, 
        debug=is_debug,
        threaded=True,  # Enable threading for Pi's limited cores
        use_reloader=False,  # Disable reloader to save memory
        passthrough_errors=not is_debug,  # Better error handling in production
    )
