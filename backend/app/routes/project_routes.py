from flask import Blueprint, jsonify

from controllers.project_controller import ProjectController
from schemas.project_schema import ProjectCreate, ProjectRead, ProjectResponse
from schemas.validation import dump, parse_body

project_bp = Blueprint('projects', __name__)


@project_bp.post('/api/projects/scan')
def scan_project():
    data, error = parse_body(ProjectCreate)
    if error is not None:
        return error

    # scan_projects() reads name/path from the request body itself.
    body, status = ProjectController.scan_projects(None)
    payload = dump(ProjectResponse, body.get_json())
    return jsonify(payload), status


@project_bp.get('/api/projects')
def list_projects():
    body, status = ProjectController.get_projects()
    payload = dump(ProjectRead, body.get_json())
    return jsonify(payload), status


@project_bp.get('/api/projects/<int:project_id>')
def get_project(project_id: int):
    body, status = ProjectController.get_project(project_id)
    if status != 200:
        return body, status

    return jsonify(dump(ProjectRead, body.get_json())), status


@project_bp.delete('/api/projects/<int:project_id>')
def delete_project(project_id: int):
    body, status = ProjectController.delete_project(project_id)
    return body, status