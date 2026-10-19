"""Real-time file system watcher for registered projects.

Design goals:
  * zero-copy fan-out — SSE subscribers get events through thread-safe queues
    and never touch the Flask/SQLAlchemy context from background threads;
  * resilience — a project watcher dies silently if the folder disappears, the
    stream simply stays alive and reports `watching: false`;
  * a bounded per-project history ring used by the Context Recovery Engine
    ("Recent Diff & Violations" scope).
"""

import json
import os
import queue
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object

# Directories that never contain architecture-relevant source changes.
IGNORED_DIRS = {
    '.git', '.hg', '.svn', '.jj',
    'node_modules', '__pycache__', '.venv', 'venv', 'env',
    '.next', '.nuxt', '.turbo', '.output',
    'dist', 'build', 'out', 'coverage',
    '.cache', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.idea', '.vscode', '.DS_Store',
    'target', 'vendor', '.terraform',
}

IGNORED_SUFFIXES = ('.pyc', '.pyo', '.pyd', '.swp', '.swo', '.tmp', '.log', '.lock')
IGNORED_NAMES = {'.DS_Store', 'Thumbs.db'}

# Minimum interval between two events for the same file (agent saves burst).
PER_FILE_THROTTLE_SECONDS = 0.25
HISTORY_LIMIT = 600
MAX_SUBSCRIBER_QUEUE = 256
KEEPALIVE_SECONDS = 15


def _iso(ts):
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec='seconds')


def _relative(root, path):
    try:
        return os.path.relpath(path, root).replace(os.sep, '/')
    except ValueError:
        return path.replace(os.sep, '/')


# Meaningful filesystem actions — open/close access events are pure noise.
ACTION_MAP = {
    'created': 'created',
    'modified': 'modified',
    'deleted': 'deleted',
    'moved': 'moved',
}


class _ProjectEventHandler(FileSystemEventHandler):
    """Filters raw watchdog events and forwards them to the shared service."""

    def __init__(self, service, project_id, root):
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.root = root

    def on_any_event(self, event):
        try:
            action = ACTION_MAP.get(event.event_type)
            if action is None:
                return

            src = getattr(event, 'src_path', None)
            dest = getattr(event, 'dest_path', None)
            if not src and not dest:
                return

            self.service.record(
                project_id=self.project_id,
                root=self.root,
                action=action,
                path=src or dest,
                dest_path=dest if action == 'moved' else None,
                is_directory=bool(event.is_directory),
            )
        except Exception:
            # Never let a watcher bug kill the observer thread.
            return


class WatcherService:
    """Process-wide singleton managing project observers and SSE subscribers."""

    def __init__(self):
        self._lock = threading.RLock()
        self._observers = {}
        self._subscribers = defaultdict(set)
        self._history = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
        self._paths = {}
        self._throttle = {}
        self._throttle_counter = 0

    # ------------------------------------------------------------------
    # Availability / introspection
    # ------------------------------------------------------------------
    @property
    def available(self):
        return WATCHDOG_AVAILABLE

    def status(self, project_id):
        with self._lock:
            observer = self._observers.get(project_id)
            watching = bool(observer and observer.is_alive())
            return {
                'project_id': project_id,
                'available': WATCHDOG_AVAILABLE,
                'watching': watching,
                'subscribers': len(self._subscribers.get(project_id, ())),
                'path': self._paths.get(project_id),
                'recent_events': len(self._history.get(project_id, ())),
            }

    # ------------------------------------------------------------------
    # Observer lifecycle
    # ------------------------------------------------------------------
    def start(self, project_id, path):
        """Start (or keep) the recursive watcher for a project folder."""
        if not WATCHDOG_AVAILABLE or not path:
            return False

        normalized = os.path.abspath(path)
        if not os.path.isdir(normalized):
            return False

        with self._lock:
            observer = self._observers.get(project_id)
            if observer and observer.is_alive():
                if self._paths.get(project_id) == normalized:
                    return True
                self._stop_locked(project_id)

            handler = _ProjectEventHandler(self, project_id, normalized)
            observer = Observer()
            observer.schedule(handler, normalized, recursive=True)
            observer.daemon = True
            observer.start()

            self._observers[project_id] = observer
            self._paths[project_id] = normalized
            return True

    def stop(self, project_id):
        with self._lock:
            self._stop_locked(project_id)

    def _stop_locked(self, project_id):
        observer = self._observers.pop(project_id, None)
        self._paths.pop(project_id, None)
        if observer:
            try:
                observer.stop()
                observer.join(timeout=2)
            except Exception:
                pass

    def stop_if_unused(self, project_id):
        """Stop the observer once the last live stream disconnected."""
        with self._lock:
            if self._subscribers.get(project_id):
                return False
            self._stop_locked(project_id)
            return True

    # ------------------------------------------------------------------
    # SSE subscribers
    # ------------------------------------------------------------------
    def subscribe(self, project_id):
        subscriber = queue.Queue(maxsize=MAX_SUBSCRIBER_QUEUE)
        with self._lock:
            self._subscribers[project_id].add(subscriber)
        return subscriber

    def unsubscribe(self, project_id, subscriber):
        with self._lock:
            subscribers = self._subscribers.get(project_id)
            if subscribers is not None:
                subscribers.discard(subscriber)
                if not subscribers:
                    self._subscribers.pop(project_id, None)

    # ------------------------------------------------------------------
    # Event intake
    # ------------------------------------------------------------------
    def record(self, project_id, root, action, path, dest_path=None, is_directory=False):
        if not path:
            return
        if is_directory and action == 'modified':
            # Directory "modified" events are implied by their file events.
            return
        relative_path = _relative(root, path)
        if relative_path in ('.', '', './'):
            return
        if _is_noise(relative_path, is_directory):
            return

        now = time.time()
        key = (project_id, path)
        with self._lock:
            last = self._throttle.get(key)
            if last is not None and (now - last) < PER_FILE_THROTTLE_SECONDS:
                return
            self._throttle[key] = now

            event = {
                'type': 'file_changed',
                'project_id': project_id,
                'action': action,
                'path': path,
                'relative_path': relative_path,
                'dest_path': dest_path,
                'dest_relative_path': _relative(root, dest_path) if dest_path else None,
                'is_directory': bool(is_directory),
                'ts': now,
                'iso': _iso(now),
            }

            self._history[project_id].append(event)
            for subscriber in tuple(self._subscribers.get(project_id, ())):
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    # Slow consumer: drop the oldest event and keep streaming.
                    try:
                        subscriber.get_nowait()
                        subscriber.put_nowait(event)
                    except queue.Empty:
                        pass

        self._prune_throttle(now)

    def _prune_throttle(self, now):
        """Cheap periodic cleanup so the throttle map cannot grow unbounded."""
        self._throttle_counter += 1
        if self._throttle_counter % 128 != 0:
            return
        with self._lock:
            self._throttle = {
                key: ts for key, ts in self._throttle.items() if now - ts <= 30
            }

    # ------------------------------------------------------------------
    # History for the Context Recovery Engine
    # ------------------------------------------------------------------
    def recent_changes(self, project_id, since_ts=None, limit=None):
        with self._lock:
            events = list(self._history.get(project_id, ()))
        if since_ts is not None:
            events = [event for event in events if event['ts'] >= since_ts]
        if limit is not None:
            events = events[-limit:]
        return events

    def clear_history(self, project_id):
        with self._lock:
            self._history.pop(project_id, None)


def _split_parts(path):
    normalized = path.replace(os.sep, '/')
    return [part for part in normalized.split('/') if part]


def _is_noise(relative_path, is_directory=False):
    """Skip dependency folders, editor droppings and binaries — project-relative."""
    parts = _split_parts(relative_path)
    if not parts:
        return True
    if set(parts) & IGNORED_DIRS:
        return True
    if is_directory:
        return False

    name = parts[-1]
    if name in IGNORED_NAMES:
        return True
    if name.endswith(IGNORED_SUFFIXES):
        return True
    # Dotfiles are rarely architecture relevant (env samples are the exception).
    return name.startswith('.') and name not in {'.env', '.env.local'}


# Singleton shared by routes/controllers.
watcher_service = WatcherService()


def sse_format(payload, event=None):
    """Serialise a dict as a Server-Sent Events frame."""
    data = json.dumps(payload, ensure_ascii=False, default=str)
    frame = ''
    if event:
        frame += f'event: {event}\n'
    frame += f'data: {data}\n\n'
    return frame
