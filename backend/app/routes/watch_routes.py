import queue
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

from models.project import Project
from services.watcher_service import KEEPALIVE_SECONDS, sse_format, watcher_service

watch_bp = Blueprint('watch', __name__)


@watch_bp.get('/api/projects/<int:project_id>/watch')
def stream_project_watcher(project_id: int):
    """Server-Sent Events stream: `file_changed` events for one project.

    Connecting starts the filesystem observer, disconnecting (the last client)
    stops it, so monitoring costs nothing while the UI is closed.
    """
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    if not watcher_service.available:
        return jsonify({
            'error': 'File watcher unavailable',
            'details': 'Install the "watchdog" package on the backend to enable live monitoring.',
        }), 501

    watching = watcher_service.start(project_id, project.path)
    subscriber = watcher_service.subscribe(project_id)
    status = watcher_service.status(project_id)

    def generate():
        try:
            yield 'retry: 3000\n\n'
            yield sse_format({
                'type': 'watcher_status',
                'project_id': project_id,
                'watching': bool(watching and status.get('watching')),
                'path': status.get('path') or project.path,
                'available': True,
            }, event='watcher_status')

            while True:
                try:
                    event = subscriber.get(timeout=KEEPALIVE_SECONDS)
                    yield sse_format(event, event='file_changed')
                except queue.Empty:
                    yield ': keepalive\n\n'
        except GeneratorExit:
            # Client went away (tab closed, monitoring toggled off).
            return
        finally:
            watcher_service.unsubscribe(project_id, subscriber)
            watcher_service.stop_if_unused(project_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@watch_bp.get('/api/projects/<int:project_id>/watch/status')
def watcher_status(project_id: int):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    state = watcher_service.status(project_id)
    # The observer only runs while a stream is attached — still report the
    # project folder so the UI can show what would be watched.
    if not state.get('path'):
        state['path'] = project.path
    return jsonify(state), 200


@watch_bp.get('/api/projects/<int:project_id>/watch/changes')
def watcher_changes(project_id: int):
    """Recent file changes (used to rebuild the feed after a reconnect)."""
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    window_minutes = request.args.get('window_minutes', default=30, type=int) or 30
    window_minutes = max(1, min(window_minutes, 10080))
    since_ts = time.time() - window_minutes * 60
    changes = watcher_service.recent_changes(project_id, since_ts=since_ts, limit=200)

    return jsonify({
        'project_id': project_id,
        'window_minutes': window_minutes,
        'count': len(changes),
        'changes': changes,
    }), 200


@watch_bp.post('/api/projects/<int:project_id>/watch/start')
def watcher_start(project_id: int):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    started = watcher_service.start(project_id, project.path)
    if not started:
        return jsonify({
            'error': 'Cannot watch project folder',
            'details': 'The folder is missing or the watchdog package is not installed.',
        }), 503

    return jsonify({'status': 'watching', **watcher_service.status(project_id)}), 200


@watch_bp.post('/api/projects/<int:project_id>/watch/stop')
def watcher_stop(project_id: int):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    # Keep live streams running, only halt the observer when nobody listens.
    stopped = watcher_service.stop_if_unused(project_id)
    state = 'stopped' if stopped else 'streaming'
    return jsonify({'status': state, **watcher_service.status(project_id)}), 200
