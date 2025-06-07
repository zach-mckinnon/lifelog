# app.py
from flask import Flask
from lifelog.api.task_api import tasks_bp
from lifelog.api.time_api import time_bp
from lifelog.api.track_api import trackers_bp
from lifelog.api.errors import register_error_handlers
from lifelog.api.sync_api import sync_bp

from lifelog.config.config_manager import is_host_server
from lifelog.utils.db.database_manager import initialize_schema

app = Flask(__name__)
initialize_schema()
# Always register CRUD endpoints (tasks, time, trackers)
app.register_blueprint(tasks_bp)
app.register_blueprint(time_bp)
app.register_blueprint(trackers_bp)
app.register_blueprint(sync_bp)

# Register error handlers (works for all modes)
register_error_handlers(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
