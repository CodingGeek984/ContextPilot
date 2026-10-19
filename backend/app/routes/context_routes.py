from flask import Blueprint, jsonify

from controllers.context_controller import ContextController

context_bp = Blueprint('context', __name__)


@context_bp.post('/api/projects/<int:project_id>/context/recovery')
def generate_recovery_prompt(project_id: int):
    """Build a compact architecture/change dump for LLM context recovery."""
    body, status = ContextController.generate_recovery_prompt(project_id)
    return body, status
