from flask import jsonify, request

from models.project import Project
from services import recovery_service


class ContextController:
    """Context Recovery Engine HTTP surface."""

    @staticmethod
    def generate_recovery_prompt(project_id: int):
        project = Project.query.get(project_id)
        if not project:
            return jsonify({'error': 'Project not found'}), 404

        options = request.get_json(silent=True) or {}

        try:
            result = recovery_service.generate_recovery_prompt(project, options)
        except ValueError as error:
            return jsonify({'error': str(error)}), 400

        return jsonify(result), 200
