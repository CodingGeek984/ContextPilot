import logging
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    # The project uses flat imports inside controllers/models/schemas
    # (e.g. "from database.db import db"), so "app/" must be importable.
    sys.path.insert(0, APP_DIR)

from flask import Flask, jsonify, request  # noqa: E402
from flask_cors import CORS  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402

from config import get_config  # noqa: E402
from database.db import db  # noqa: E402
from routes.context_routes import context_bp  # noqa: E402
from routes.git_routes import git_bp  # noqa: E402
from routes.graph_routes import graph_bp  # noqa: E402
from routes.health_routes import health_bp  # noqa: E402
from routes.mcp_routes import mcp_bp  # noqa: E402
from routes.project_routes import project_bp  # noqa: E402
from routes.rules_routes import rules_bp  # noqa: E402
from routes.watch_routes import watch_bp  # noqa: E402

BLUEPRINTS = (
    health_bp, project_bp, graph_bp, rules_bp, mcp_bp, watch_bp, context_bp, git_bp,
)

MODEL_MODULES = (
    'models.project',
    'models.node',
    'models.edge',
    'models.project_rule',
    'models.mcp_session',
)


def register_models():
    """Import every model module so db.create_all() sees the full metadata."""
    import importlib

    for module in MODEL_MODULES:
        importlib.import_module(module)


def register_error_handlers(app: Flask):
    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(error):
        db.session.rollback()
        app.logger.exception('Database error: %s', error)
        return jsonify({'error': 'Database error', 'details': str(error)}), 500

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if not request.path.startswith('/api'):
            return error
        return jsonify({
            'error': error.name,
            'message': error.description,
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        db.session.rollback()
        app.logger.exception('Unhandled error: %s', error)
        return jsonify({
            'error': 'Internal server error',
            'details': str(error),
        }), 500


def register_cli(app: Flask):
    @app.cli.command('init-db')
    def init_db():
        """Create all tables."""
        register_models()
        db.create_all()
        print('Database initialised.')

    @app.cli.command('drop-db')
    def drop_db():
        """Drop all tables (destructive)."""
        register_models()
        db.drop_all()
        print('Database dropped.')


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    logging.basicConfig(level=logging.INFO)

    CORS(app, resources={r'/api/*': {'origins': app.config.get('CORS_ORIGINS', '*')}})

    db.init_app(app)
    register_models()

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    register_error_handlers(app)
    register_cli(app)

    with app.app_context():
        db.create_all()

    app.logger.info('ContextPilot backend ready')
    return app