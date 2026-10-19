"""Best-effort Git integration for a registered project folder.

Every helper degrades gracefully: if `git` is missing, the folder is not a
repository, or a command fails, callers simply receive an empty/`None` result
instead of an exception. Shared by the Context Recovery Engine and the
`/projects/<id>/diff` endpoint so both describe the tree identically.
"""

import os
import shutil
import subprocess

GIT_TIMEOUT_SECONDS = 6
MAX_GIT_LINES = 200
DEFAULT_WINDOW_MINUTES = 30


def is_available():
    return shutil.which('git') is not None


def run_git(args, cwd, timeout=GIT_TIMEOUT_SECONDS):
    """Run `git -C cwd <args>`, returning stdout as text or `None` on failure."""
    if not cwd or not os.path.isdir(cwd) or not is_available():
        return None
    try:
        proc = subprocess.run(
            ['git', '-C', cwd, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def is_repository(path):
    output = run_git(['rev-parse', '--is-inside-work-tree'], path)
    return bool(output and output.strip() == 'true')


def current_branch(path):
    output = run_git(['rev-parse', '--abbrev-ref', 'HEAD'], path)
    return output.strip() if output and output.strip() else None


def status_entries(path, limit=MAX_GIT_LINES):
    """`git status --porcelain` rows, capped at `limit`."""
    output = run_git(['status', '--porcelain'], path)
    if not output:
        return []
    rows = [row for row in output.splitlines() if row.strip()]
    return rows[:limit]


def changed_files(path, limit=MAX_GIT_LINES):
    """Project-relative paths reported by `git status --porcelain`."""
    files = []
    for row in status_entries(path, limit=limit):
        entry = row[3:] if len(row) > 3 else row.strip()
        if ' -> ' in entry:
            entry = entry.split(' -> ', 1)[1]
        files.append(entry.strip().strip('"'))
    return files


def diff_stat(path, paths=None, limit=MAX_GIT_LINES):
    """`git diff --stat HEAD [-- paths]` rows."""
    args = ['diff', '--stat', 'HEAD']
    if paths:
        args.extend(['--', *paths])
    output = run_git(args, path)
    if not output:
        return []
    return [row for row in output.splitlines() if row.strip()][:limit]


def recent_commits(path, window_minutes=DEFAULT_WINDOW_MINUTES, limit=20):
    """Commits newer than `window_minutes` as `{hash, subject}` dicts."""
    since = f'--since={max(1, int(window_minutes))} minutes ago'
    output = run_git(['log', since, f'--max-count={limit}', '--pretty=%h%x09%s'], path)
    if not output:
        return []
    commits = []
    for row in output.splitlines():
        if not row.strip():
            continue
        commit_hash, _, subject = row.partition('\t')
        commits.append({'hash': commit_hash.strip(), 'subject': subject.strip()})
    return commits


def unified_diff(path, paths=None, max_lines=MAX_GIT_LINES):
    """`git diff HEAD [-- paths]` split into lines, capped."""
    args = ['diff', 'HEAD', '--no-color']
    if paths:
        args.extend(['--', *paths])
    output = run_git(args, path, timeout=GIT_TIMEOUT_SECONDS * 2)
    if not output:
        return []
    lines = output.splitlines()
    return lines[:max_lines]


def snapshot(path, window_minutes=DEFAULT_WINDOW_MINUTES, include_diff=False, paths=None):
    """Structured git state for one project folder."""
    available = is_available()
    repository = available and is_repository(path)
    result = {
        'available': available,
        'is_repository': repository,
        'branch': None,
        'window_minutes': max(1, int(window_minutes or DEFAULT_WINDOW_MINUTES)),
        'status': [],
        'changed_files': [],
        'diff_stat': [],
        'commits': [],
    }
    if not repository:
        return result

    result['branch'] = current_branch(path)
    result['status'] = status_entries(path)
    result['changed_files'] = changed_files(path)
    result['diff_stat'] = diff_stat(path, paths=paths)
    result['commits'] = recent_commits(path, window_minutes=result['window_minutes'])
    if include_diff:
        result['diff'] = unified_diff(path, paths=paths)
    return result
