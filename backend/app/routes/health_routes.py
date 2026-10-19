from flask import Blueprint, jsonify

from controllers.health_controller import HealthController

health_bp = Blueprint('health', __name__)


@health_bp.get('/api/health')
def health():
    return HealthController.check_health()


@health_bp.get('/api/health/live')
def live():
    return jsonify({'status': 'ok'}), 200