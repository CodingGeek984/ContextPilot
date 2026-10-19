from flask import jsonify

from models.project import Project
from services import git_service


class GitController:
    """Read-only view over the project's git working tree (best effort)."""

    @staticmethod
    def get_diff(project_id: int, window_minutes: int = 30, include_diff: bool = False, paths=None):
        project = Project.query.get(project_id)
        if not project:
            return jsonify({'error': 'Project not found'}), 404

        snapshot = git_service.snapshot(
            project.path,
            window_minutes=window_minutes,
            include_diff=include_diff,
            paths=paths,
        )

        payload = {
            'status': 'success',
            'project_id': project_id,
            'available': snapshot['available'],
            'is_repository': snapshot['is_repository'],
            'branch': snapshot['branch'],
            'window_minutes': snapshot['window_minutes'],
            'status_entries': snapshot['status'],
            'changed_files': snapshot['changed_files'],
            'diff_stat': snapshot['diff_stat'],
            'commits': snapshot['commits'],
            'diff': snapshot.get('diff', []),
            'truncated': len(snapshot['status']) >= git_service.MAX_GIT_LINES,
        }
        return jsonify(payload), 200
