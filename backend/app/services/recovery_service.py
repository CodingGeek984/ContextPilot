"""Context Recovery Engine.

Builds a *compact, structured* Markdown dump of a project's architecture and
current change state so a LLM that lost the thread can be re-synced in one
message. Three scopes are supported:

  full     — high-level map of every layer, module and dependency;
  focused  — one module plus its 1–2 hop neighbourhood;
  recent   — what changed in the last N minutes + git state + rules/violations.
"""

import os
import time
from collections import defaultdict
from datetime import datetime

from models.edge import Edge
from models.node import Node
from models.project_rule import ProjectRule
from services import git_service
from services.watcher_service import watcher_service

SCOPES = ('full', 'focused', 'recent')

MAX_PROMPT_CHARS = 60_000
MAX_MODULE_LINES = 500
MAX_EDGE_LINES = 500
MAX_RECENT_EVENTS = 120
MAX_GIT_LINES = 120
MAX_RULE_LINES = 60

SCOPE_MISSION = {
    'full': (
        'Rebuild your complete mental model of this repository from the snapshot '
        'below before answering. The snapshot is ground truth — do not invent '
        'modules, layers or files that are not listed.'
    ),
    'focused': (
        'Only the focused module subtree below is in scope. Respect its boundaries: '
        'never route a change through a module outside this sub-graph unless the '
        'dependency arrows below allow it.'
    ),
    'recent': (
        'The codebase changed underneath you. Reconcile your memory with the change '
        'log below — files listed there may already differ from what you remember.'
    ),
}


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------
def _relative(root, path):
    if not path:
        return None
    normalized = str(path).replace(os.sep, '/')
    if not root:
        return normalized
    try:
        rel = os.path.relpath(str(path), root)
    except ValueError:
        return normalized
    if rel.startswith('..'):
        return normalized
    return rel.replace(os.sep, '/')


def _load_nodes(project_id, root):
    rows = Node.query.filter_by(project_id=project_id).all()
    nodes = []
    for row in rows:
        metadata = row.metadata_json or {}
        if not isinstance(metadata, dict):
            metadata = {}
        nodes.append({
            'id': row.id,
            'name': row.name,
            'type': str(row.node_type or 'unknown').lower(),
            'path': _relative(root, row.file_path),
            'metadata': metadata,
            'violations': _violations(metadata),
        })
    return nodes


def _violations(metadata):
    violations = metadata.get('violations')
    if isinstance(violations, list):
        return [str(item) for item in violations if item]
    if isinstance(violations, str) and violations.strip():
        return [violations.strip()]
    return []


def _load_edges(project_id):
    nodes = Node.query.filter_by(project_id=project_id).all()
    node_ids = [node.id for node in nodes]
    if not node_ids:
        return []
    rows = Edge.query.filter(Edge.source_id.in_(node_ids)).all()
    return [
        {
            'source': row.source_id,
            'target': row.target_id,
            'type': str(row.relation_type or 'related'),
        }
        for row in rows
    ]


def _load_rules(project_id):
    rows = ProjectRule.query.filter_by(project_id=project_id).all()
    return [
        {
            'type': str(getattr(row, 'rule_type', 'general')),
            'content': (row.content or '').strip(),
        }
        for row in rows
        if (row.content or '').strip()
    ]


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------
def _layer_section(nodes):
    counts = defaultdict(int)
    for node in nodes:
        counts[node['type']] += 1
    lines = [f'- {kind}: {count}' for kind, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return 'Layer map', lines or ['- (empty graph)']


def _module_section(nodes, limit=MAX_MODULE_LINES):
    lines = []
    for node in sorted(nodes, key=lambda item: (item['type'], item['name'])):
        path = node['path'] or 'path n/a'
        lines.append(f"- [{node['type']}] {node['name']} — {path}")
    truncated = len(lines) > limit
    return 'Modules', lines[:limit], truncated


def _dependency_section(edges, by_id, limit=MAX_EDGE_LINES):
    lines = []
    for edge in edges:
        source = by_id.get(edge['source'])
        target = by_id.get(edge['target'])
        if not source or not target:
            continue
        lines.append(f"- {source['name']} --{edge['type']}--> {target['name']}")
    truncated = len(lines) > limit
    return 'Dependencies', lines[:limit], truncated


def _rules_section(rules):
    lines = []
    for index, rule in enumerate(rules[:MAX_RULE_LINES], start=1):
        content = ' '.join(rule['content'].split())
        if len(content) > 240:
            content = content[:237] + '…'
        lines.append(f"{index}. [{rule['type']}] {content}")
    if len(rules) > MAX_RULE_LINES:
        lines.append(f'… {len(rules) - MAX_RULE_LINES} more rules omitted')
    return 'Architecture rules (do not break)', lines or ['- (no rules defined)']


def _violations_section(nodes):
    lines = []
    for node in nodes:
        if not node['violations']:
            continue
        joined = '; '.join(node['violations'])
        lines.append(f"- {node['name']} ({node['path'] or 'n/a'}): {joined}")
    return 'Detected violations', lines


# ---------------------------------------------------------------------------
# Git integration (best effort — the folder may not be a repository)
# ---------------------------------------------------------------------------
def _recent_git_section(project_path, window_minutes, recent_paths):
    if not project_path or not git_service.is_repository(project_path):
        return []

    lines = []

    status = git_service.status_entries(project_path)
    if status:
        lines.append('Uncommitted changes (`git status --porcelain`):')
        lines.extend(f'  {entry}' for entry in status[:MAX_GIT_LINES])
        if len(status) > MAX_GIT_LINES:
            lines.append('… more entries omitted')

    stat = git_service.diff_stat(project_path)
    if stat:
        lines.append('')
        lines.append('Diff stat (`git diff --stat HEAD`):')
        lines.extend(f'  {row}' for row in stat[:MAX_GIT_LINES])

    commits = git_service.recent_commits(
        project_path, window_minutes=window_minutes, limit=MAX_GIT_LINES
    )
    if commits:
        lines.append('')
        lines.append(f'Recent commits (last {window_minutes} min):')
        lines.extend(f"  {commit['hash']} {commit['subject']}" for commit in commits)

    if recent_paths:
        scoped = git_service.diff_stat(project_path, paths=recent_paths[:MAX_GIT_LINES])
        if scoped:
            lines.append('')
            lines.append('Diff stat for files touched by the watcher:')
            lines.extend(f'  {row}' for row in scoped[:MAX_GIT_LINES])

    return lines


def _recent_changes_section(project_id, window_minutes):
    since_ts = time.time() - window_minutes * 60
    events = watcher_service.recent_changes(project_id, since_ts=since_ts, limit=MAX_RECENT_EVENTS)

    lines = []
    for event in events:
        stamp = datetime.fromtimestamp(event['ts']).strftime('%H:%M:%S')
        path = event.get('dest_relative_path') or event.get('relative_path') or event.get('path')
        arrow = ''
        if event.get('action') == 'moved' and event.get('dest_relative_path'):
            arrow = f" -> {event['dest_relative_path']}"
        lines.append(f"- {stamp}  {event.get('action', 'modified'):8} {path}{arrow}")

    if not lines:
        watcher_state = watcher_service.status(project_id)
        if not watcher_state.get('available'):
            lines.append('- file watcher unavailable on the backend (install `watchdog`)')
        elif not watcher_state.get('watching'):
            lines.append('- live monitoring is off — no change data (enable "Live Monitoring")')
        else:
            lines.append(f'- no file changes recorded in the last {window_minutes} minutes')
    return events, lines


# ---------------------------------------------------------------------------
# Focused sub-graph
# ---------------------------------------------------------------------------
def _resolve_focus(nodes, focus_node_id, focus_node_name):
    if focus_node_id not in (None, ''):
        try:
            wanted = int(focus_node_id)
        except (TypeError, ValueError):
            wanted = None
        if wanted is not None:
            for node in nodes:
                if node['id'] == wanted:
                    return node

    if focus_node_name:
        needle = str(focus_node_name).strip().lower()
        for node in nodes:
            if node['name'].lower() == needle:
                return node
        for node in nodes:
            if needle in node['name'].lower():
                return node
    return None


def _focused_sections(focus, nodes, edges, by_id, depth):
    """Breadth-first walk over both directions (dependents + dependencies)."""
    adjacency = defaultdict(list)
    for edge in edges:
        adjacency[edge['source']].append((edge['target'], edge['type'], 'out'))
        adjacency[edge['target']].append((edge['source'], edge['type'], 'in'))

    seen = {focus['id']}
    frontier = [focus['id']]
    levels = []
    for _ in range(max(1, depth)):
        next_frontier = []
        level_edges = []
        for node_id in frontier:
            for other_id, relation, direction in adjacency.get(node_id, ()):
                level_edges.append((node_id, other_id, relation, direction))
                if other_id not in seen:
                    seen.add(other_id)
                    next_frontier.append(other_id)
        levels.append({'nodes': list(frontier), 'edges': level_edges})
        if not next_frontier:
            break
        frontier = next_frontier

    subset = [node for node in nodes if node['id'] in seen]
    focus_section = (
        'Focus module',
        [
            f"- {focus['name']} [{focus['type']}] — {focus['path'] or 'path n/a'}",
            f'- scope: {focus["name"]} + {len(seen) - 1} neighbours within {depth} hop(s)',
        ],
    )

    lines = []
    for index, level in enumerate(levels, start=1):
        header = f'-- hop {index} --'
        lines.append(header)
        for source_id, target_id, relation, direction in level_edges:
            source = by_id.get(source_id)
            target = by_id.get(target_id)
            if not source or not target:
                continue
            if direction == 'out':
                lines.append(f"- {source['name']} --{relation}--> {target['name']}")
            else:
                lines.append(f"- {target['name']} <--{relation}-- {source['name']}")
        lines.append('')

    return focus_section, ('Sub-graph relations', lines), subset


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_recovery_prompt(project, options):
    """Return `{prompt, scope, generated_at, stats, truncated}` for one project."""
    options = options or {}
    scope = str(options.get('scope') or 'full').lower()
    if scope not in SCOPES:
        raise ValueError(f"Unknown scope '{scope}'. Expected one of {', '.join(SCOPES)}.")

    depth = _clamp(options.get('depth'), 1, 4, default=2)
    window_minutes = _clamp(options.get('window_minutes'), 1, 10080, default=30)

    root = project.path
    nodes = _load_nodes(project.id, root)
    edges = _load_edges(project.id)
    rules = _load_rules(project.id)
    by_id = {node['id']: node for node in nodes}

    sections = []
    stats = {
        'modules': len(nodes),
        'dependencies': len(edges),
        'rules': len(rules),
        'scope': scope,
    }

    if scope == 'focused':
        focus = _resolve_focus(
            nodes, options.get('focus_node_id'), options.get('focus_node_name')
        )
        if not focus:
            raise ValueError('Focus module not found in the current graph.')
        focus_section, relation_section, subset = _focused_sections(
            focus, nodes, edges, by_id, depth
        )
        layer_section = _layer_section(subset)
        sections.append(focus_section)
        sections.append(layer_section)
        sections.append(relation_section)
        sections.append(_module_section(subset))
        stats['focus'] = focus['name']
        stats['scoped_modules'] = len(subset)

    elif scope == 'recent':
        events, change_lines = _recent_changes_section(project.id, window_minutes)
        git_lines = _recent_git_section(root, window_minutes, [
            event.get('relative_path')
            for event in events
            if event.get('relative_path') and not event.get('is_directory')
        ])
        sections.append(_layer_section(nodes))
        sections.append((
            f'File changes (last {window_minutes} min)',
            change_lines,
        ))
        if git_lines:
            sections.append(('Git state', git_lines))
        sections.append(_rules_section(rules))
        violations_lines = _violations_section(nodes)[1]
        if violations_lines:
            sections.append(('Detected violations', violations_lines))
        stats['recent_events'] = len(events)
        stats['window_minutes'] = window_minutes

    else:  # full
        sections.append(_layer_section(nodes))
        sections.append(_module_section(nodes))
        sections.append(_dependency_section(edges, by_id))
        sections.append(_rules_section(rules))
        violations_lines = _violations_section(nodes)[1]
        if violations_lines:
            sections.append(('Detected violations', violations_lines))

    prompt, truncated = _assemble(project, scope, stats, sections, depth, window_minutes)
    return {
        'status': 'success',
        'scope': scope,
        'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'prompt': prompt,
        'truncated': truncated,
        'stats': stats,
    }


def _clamp(value, low, high, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _assemble(project, scope, stats, sections, depth, window_minutes):
    header = [
        f'# Context Recovery — {project.name}',
        f'Repo: {project.path}',
        (
            f'Generated: {datetime.now().astimezone().isoformat(timespec="seconds")} | '
            f'Scope: {scope} | Modules: {stats["modules"]} | '
            f'Dependencies: {stats["dependencies"]}'
        ),
        '',
        '## Mission',
        SCOPE_MISSION[scope],
    ]
    if scope == 'focused':
        header.append(f'Focus: {stats.get("focus")} (depth ≤ {depth} hop(s)).')
    if scope == 'recent':
        header.append(f'Change window: last {window_minutes} minutes.')

    parts = ['\n'.join(header)]
    truncated = False
    used = len(parts[0])

    for section in sections:
        if len(section) == 3:
            title, lines, was_truncated = section
            truncated = truncated or bool(was_truncated)
        else:
            title, lines = section
        if not lines:
            continue

        block = '\n'.join([f'\n## {title}', *lines])
        if used + len(block) > MAX_PROMPT_CHARS:
            remaining = MAX_PROMPT_CHARS - used
            if remaining > 200:
                parts.append(block[:remaining] + '\n… (truncated)')
            truncated = True
            break
        parts.append(block)
        used += len(block)

    parts.append(
        '\n## Contract with the user\n'
        '- Answer strictly from this snapshot; ask before assuming anything not listed.\n'
        '- Keep new code inside the existing layer it belongs to.\n'
        '- Never introduce circular dependencies between layers.'
    )

    return '\n'.join(parts), truncated
