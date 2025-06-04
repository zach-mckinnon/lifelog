# app.py
from flask import Flask
from api.task_api import tasks_bp
from api.time_api import time_bp
from api.track_api import trackers_bp
from api.errors import register_error_handlers

app = Flask(__name__)

# Register blueprints
app.register_blueprint(tasks_bp)
app.register_blueprint(time_bp)
app.register_blueprint(trackers_bp)

# Register error handlers
register_error_handlers(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
