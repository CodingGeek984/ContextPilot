from flask import Blueprint, jsonify, request

from controllers.git_controller import GitController
from schemas.git_schema import GitDiffRead
from schemas.validation import dump

git_bp = Blueprint('git', __name__)

DEFAULT_WINDOW_MINUTES = 30
MAX_WINDOW_MINUTES = 24 * 60


def _parse_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _parse_bool(value):
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


@git_bp.get('/api/projects/<int:project_id>/diff')
def project_diff(project_id: int):
    """Live git status / diff-stat / recent commits for a project folder."""
    window_minutes = _parse_int(
        request.args.get('window_minutes'),
        DEFAULT_WINDOW_MINUTES,
        1,
        MAX_WINDOW_MINUTES,
    )
    include_diff = _parse_bool(request.args.get('include_diff'))

    body, status = GitController.get_diff(
        project_id,
        window_minutes=window_minutes,
        include_diff=include_diff,
    )
    if status != 200:
        return body, status

    return jsonify(dump(GitDiffRead, body.get_json())), status
