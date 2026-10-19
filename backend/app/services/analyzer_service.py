"""Static repository analyzer — the component that actually populates the graph.

Walks a registered project folder and materialises one :class:`Node` per source
file plus one :class:`Edge` per *resolved* import. The extractor is pure stdlib:
imports are pulled with per-language regular expressions and then resolved
against the real filesystem, so an unresolvable specifier (a third-party
package, a broken path) produces no edge instead of a false positive.

The service is intentionally incremental-friendly:

  * nodes are upserted by absolute file path, so ids — and therefore the
    frontend's saved node positions — stay stable across re-analyses;
  * edges are rebuilt from the `imports` list cached in node metadata, so a
    one-file change does not require re-reading the whole tree;
  * circular dependencies are detected and stamped onto the participating
    nodes as metadata violations, which the Context Recovery Engine reports and
    the canvas renders as warning nodes.
"""

import json
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

from database.db import db
from models.edge import Edge
from models.node import Node
from models.project import Project
from services.watcher_service import _is_noise

# ---------------------------------------------------------------------------
# Limits — keep a runaway folder from freezing a request.
# ---------------------------------------------------------------------------
MAX_FILES = 5000
MAX_FILE_BYTES = 512 * 1024
MAX_EDGES = 20000
MAX_IMPORTS_PER_FILE = 200
MAX_EXPORT_NAMES = 20
MAX_VIOLATIONS = 200
MAX_NAME_LENGTH = 150

_ANALYZE_LOCK = threading.RLock()


LANGUAGE_BY_EXTENSION = {
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.mjs': 'javascript',
    '.cjs': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.vue': 'vue',
    '.svelte': 'svelte',
    '.py': 'python',
    '.rb': 'ruby',
    '.go': 'go',
    '.java': 'java',
    '.kt': 'kotlin',
    '.rs': 'rust',
    '.php': 'php',
    '.cs': 'csharp',
    '.c': 'c',
    '.h': 'c',
    '.cc': 'cpp',
    '.cpp': 'cpp',
    '.hpp': 'cpp',
    '.swift': 'swift',
    '.m': 'objc',
}

# Modules whose imports we can turn into graph edges.
RESOLVABLE_LANGUAGES = {'javascript', 'typescript', 'vue', 'svelte', 'python'}

JS_RESOLVE_EXTENSIONS = (
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.json', '.vue', '.svelte',
)

# ---------------------------------------------------------------------------
# Import extractors
# ---------------------------------------------------------------------------
JS_IMPORT_PATTERNS = (
    re.compile(r"""import\s+(?:type\s+)?(?:[^'";]*?\s+from\s+)?['"]([^'"]+)['"]"""),
    re.compile(r"""export\s+(?:type\s+)?(?:\*|\{[^}]*\})\s+from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)"""),
)

PY_IMPORT_RE = re.compile(
    r"^\s*import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*)", re.MULTILINE
)
PY_FROM_RE = re.compile(
    r"^\s*from\s+(\.*)([A-Za-z_][\w.]*)?\s+import\b", re.MULTILINE
)

GO_BLOCK_RE = re.compile(r"import\s*\(([^)]*)\)", re.DOTALL)
GO_SINGLE_RE = re.compile(r'^\s*import\s+(?:\w+\s+)?"([^"]+)"', re.MULTILINE)
GO_QUOTED_RE = re.compile(r'"([^"]+)"')

JVM_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;?", re.MULTILINE)
RUBY_REQUIRE_RE = re.compile(
    r"""require(?:_relative)?\s*\(?\s*['"]([^'"]+)['"]"""
)

JS_EXPORT_RE = re.compile(
    r"export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)"
)
PY_DEF_RE = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.MULTILINE)

COMPLEXITY_RE = re.compile(
    r"\b(?:if|elif|else\s+if|for|while|case|catch|except|when)\b|&&|\|\||\?\?"
)

# ---------------------------------------------------------------------------
# Layer heuristics (mirrors the frontend's `normalizeLayer`)
# ---------------------------------------------------------------------------
LAYER_WORDS = (
    ('route', ('routes', 'route', 'router', 'routers', 'urls', 'endpoints', 'endpoint')),
    ('controller', ('controllers', 'controller', 'handlers', 'handler', 'resolvers', 'resolver')),
    ('service', ('services', 'service', 'usecases', 'usecase', 'managers', 'manager', 'providers', 'provider', 'stores', 'store', 'domain', 'core')),
    ('repository', ('repositories', 'repository', 'repos', 'repo', 'dao', 'adapters', 'adapter', 'gateways', 'gateway', 'database', 'persistence', 'infra', 'infrastructure')),
    ('model', ('models', 'model', 'entities', 'entity', 'schemas', 'schema', 'dto', 'dtos', 'migrations', 'types')),
    ('view', ('components', 'component', 'views', 'view', 'screens', 'screen', 'pages', 'page', 'ui', 'widgets', 'widget', 'layouts', 'layout', 'templates', 'template')),
    ('util', ('utils', 'util', 'helpers', 'helper', 'shared', 'common', 'lib', 'libs', 'config', 'configs', 'constants', 'middleware', 'hooks', 'hook')),
)

TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|specs?|__mocks__)(/|$)", re.IGNORECASE)
TEST_FILE_RE = re.compile(r"(^|[._-])(test|spec)s?([._-]|$)", re.IGNORECASE)

# Dependencies are expected to flow "downward" through these ranks
# (controller -> service -> repository -> model), with `util` treated as a
# leaf that anything may depend on. A module that imports a *higher* layer
# inverts the architecture. `test`/`unknown` are intentionally unranked so
# they never raise false positives.
LAYER_RANK = {
    'controller': 0,
    'route': 1,
    'view': 2,
    'service': 3,
    'repository': 4,
    'model': 5,
    'util': 6,
}
INVERSION_SOURCES = frozenset({'controller', 'route', 'view', 'service', 'repository', 'model'})
MAX_VIOLATIONS_PER_NODE = 6


def language_for(path):
    return LANGUAGE_BY_EXTENSION.get(os.path.splitext(path)[1].lower())


def is_supported(path):
    return language_for(path) is not None


def _is_test_file(relative_path, filename):
    if TEST_PATH_RE.search(relative_path):
        return True
    stem = os.path.splitext(filename)[0]
    return bool(TEST_FILE_RE.search(stem)) and not filename.lower().startswith('__init__')


def classify_layer(relative_path, filename):
    """Coarse architecture layer inferred from the file's location/name."""
    if _is_test_file(relative_path, filename):
        return 'test'

    stem = os.path.splitext(filename)[0].lower()
    segments = [part for part in relative_path.lower().replace('\\', '/').split('/') if part]

    for layer, words in LAYER_WORDS:
        for segment in segments[:-1]:
            if segment in words or segment.rstrip('s') in words:
                return layer
        if stem in words or stem.rstrip('s') in words:
            return layer
    return 'unknown'


# ---------------------------------------------------------------------------
# Small filesystem / parsing helpers
# ---------------------------------------------------------------------------
def _normalize_relative(path):
    normalized = str(path).replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    return normalized.lstrip('/')


def _relative_to(root, path):
    if not path:
        return None
    try:
        relative = os.path.relpath(os.path.abspath(path), root)
    except ValueError:
        return _normalize_relative(path)
    if relative.startswith('..'):
        return _normalize_relative(path)
    return _normalize_relative(relative)


def _normalize_abs(root, path):
    if not path:
        return None
    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    return os.path.normpath(candidate)


def _read_text(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return None
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return None


def _strip_json_comments(text):
    """Best-effort tsconfig/jsconfig reader (tolerates comments, trailing commas)."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'(^|[^:])//[^\n]*', r'\1', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _load_path_aliases(root):
    """Read `baseUrl`/`paths` from tsconfig.json or jsconfig.json."""
    aliases = {}
    for name in ('tsconfig.json', 'jsconfig.json'):
        raw = _read_text(os.path.join(root, name))
        if not raw:
            continue
        try:
            data = json.loads(_strip_json_comments(raw))
        except (ValueError, TypeError):
            continue
        compiler = data.get('compilerOptions') if isinstance(data, dict) else None
        if not isinstance(compiler, dict):
            continue
        base_url = _normalize_relative(compiler.get('baseUrl') or '.')
        paths = compiler.get('paths') or {}
        if not isinstance(paths, dict):
            continue
        for key, targets in paths.items():
            if not isinstance(targets, (list, tuple)) or not targets:
                continue
            prefix = str(key).split('*')[0]
            target = _normalize_relative(str(targets[0]).split('*')[0])
            joined = os.path.normpath(os.path.join(base_url, target)).replace(os.sep, '/')
            aliases[prefix] = '' if joined == '.' else _normalize_relative(joined)
    return aliases


def _extract_raw_imports(content, language):
    """Pull raw import specifiers out of a source file (no resolution here)."""
    if language in ('javascript', 'typescript', 'vue', 'svelte'):
        found = []
        for pattern in JS_IMPORT_PATTERNS:
            found.extend(pattern.findall(content))
        return found

    if language == 'python':
        found = []
        for match in PY_FROM_RE.finditer(content):
            dots, module = match.group(1), match.group(2) or ''
            found.append(f'{dots}{module}')
        for match in PY_IMPORT_RE.finditer(content):
            for name in match.group(1).split(','):
                name = name.strip()
                if not name or name.startswith('.'):
                    continue
                found.append(name)
        return found

    if language == 'go':
        found = list(GO_QUOTED_RE.findall(''.join(GO_BLOCK_RE.findall(content))))
        found.extend(GO_SINGLE_RE.findall(content))
        return found

    if language in ('java', 'kotlin', 'csharp'):
        return JVM_IMPORT_RE.findall(content)

    if language == 'ruby':
        return RUBY_REQUIRE_RE.findall(content)

    return []


def _extract_export_names(content, language):
    if language in ('javascript', 'typescript', 'vue', 'svelte'):
        return JS_EXPORT_RE.findall(content)[:MAX_EXPORT_NAMES]
    if language == 'python':
        return PY_DEF_RE.findall(content)[:MAX_EXPORT_NAMES]
    return []


def _complexity_score(content):
    return len(COMPLEXITY_RE.findall(content))


# ---------------------------------------------------------------------------
# Target collection
# ---------------------------------------------------------------------------
def _collect_targets(root, relative_paths=None):
    """Return `(absolute_paths, truncated)` for a full walk or a subset."""
    if relative_paths is not None:
        targets = []
        for relative in relative_paths:
            if not relative:
                continue
            normalized = _normalize_relative(relative)
            if not normalized or _is_noise(normalized):
                continue
            absolute = _normalize_abs(root, normalized)
            if absolute and _is_within(root, absolute) and os.path.isfile(absolute) and is_supported(absolute):
                targets.append(absolute)
        return sorted(set(targets)), False

    targets = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames
            if not _is_noise(_relative_to(root, os.path.join(dirpath, name)) or name, is_directory=True)
            and name not in ('.git', '.hg')
        )
        for filename in sorted(filenames):
            relative = _relative_to(root, os.path.join(dirpath, filename))
            if relative is None or _is_noise(relative):
                continue
            if not is_supported(filename):
                continue
            if len(targets) >= MAX_FILES:
                truncated = True
                return targets, truncated
            targets.append(os.path.join(dirpath, filename))
    return targets, truncated


def _is_within(root, path):
    try:
        return os.path.commonpath([root, os.path.abspath(path)]) == root
    except ValueError:
        return False


def _parse_file(absolute, root):
    content = _read_text(absolute)
    if content is None:
        return None
    language = language_for(absolute)
    if language is None:
        return None
    relative = _relative_to(root, absolute)
    filename = os.path.basename(absolute)
    imports = [item for item in _extract_raw_imports(content, language) if item][:MAX_IMPORTS_PER_FILE]
    return {
        'absolute': os.path.normpath(absolute),
        'relative': relative,
        'filename': filename,
        'language': language,
        'loc': content.count('\n') + 1,
        'imports': imports,
        'exports': _extract_export_names(content, language),
        'complexity': _complexity_score(content),
        'is_test': _is_test_file(relative, filename),
        'layer': classify_layer(relative, filename),
    }


# ---------------------------------------------------------------------------
# Import resolution
# ---------------------------------------------------------------------------
def _expand_js_candidate(base):
    candidates = [base]
    for extension in JS_RESOLVE_EXTENSIONS:
        candidates.append(base + extension)
    for extension in JS_RESOLVE_EXTENSIONS:
        candidates.append(f'{base}/index{extension}')
    return candidates


def _resolve_js(spec, current_relative, aliases):
    candidates = []
    if spec.startswith('.'):
        base = os.path.normpath(os.path.join(os.path.dirname(current_relative), spec))
        candidates.extend(_expand_js_candidate(base.replace(os.sep, '/')))
    else:
        for prefix, target in aliases.items():
            if spec == prefix or spec.startswith(prefix):
                remainder = spec[len(prefix):]
                joined = os.path.normpath(f'{target}/{remainder}') if target else os.path.normpath(remainder)
                candidates.extend(_expand_js_candidate(joined.replace(os.sep, '/')))
                break
    return [_normalize_relative(candidate) for candidate in candidates]


def _expand_python_candidate(base_parts):
    if not base_parts:
        return []
    joined = '/'.join(base_parts)
    return [f'{joined}.py', f'{joined}/__init__.py']


def _resolve_python(spec, current_relative):
    level = len(spec) - len(spec.lstrip('.'))
    module = spec[level:]
    candidates = []

    if level > 0:
        package_parts = _normalize_relative(os.path.dirname(current_relative)).split('/')
        package_parts = [part for part in package_parts if part]
        keep = len(package_parts) - (level - 1)
        if keep < 0:
            return []
        base_parts = package_parts[:keep]
        if module:
            base_parts = base_parts + module.split('.')
        candidates.extend(_expand_python_candidate(base_parts))
        return candidates

    parts = [part for part in module.split('.') if part]
    for start in range(len(parts)):
        candidates.extend(_expand_python_candidate(parts[start:]))
    return candidates


def _resolve_import(spec, language, current_relative, known_relative, aliases):
    if language not in RESOLVABLE_LANGUAGES:
        return None

    if language == 'python':
        candidates = _resolve_python(spec, current_relative)
    else:
        candidates = _resolve_js(spec, current_relative, aliases)

    for candidate in candidates:
        if candidate in known_relative:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------
def _desired_names(relative):
    filename = os.path.basename(relative)
    stem = os.path.splitext(filename)[0]
    if filename == '__init__.py':
        parent = os.path.basename(os.path.dirname(relative)) if os.path.dirname(relative) else ''
        stem = parent or 'root'
    relative_stem = os.path.splitext(relative)[0]
    return [stem, relative_stem]


def _unique_name(relative, used_names):
    for candidate in _desired_names(relative):
        name = candidate[:MAX_NAME_LENGTH]
        if name and name not in used_names:
            used_names.add(name)
            return name
    base = _desired_names(relative)[-1][:MAX_NAME_LENGTH - 4]
    counter = 2
    name = f'{base}-{counter}'
    while name in used_names:
        counter += 1
        name = f'{base}-{counter}'
    used_names.add(name)
    return name


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------
def _strongly_connected_components(node_ids, adjacency):
    """Iterative Tarjan — avoids recursion limits on deep import chains."""
    index_of = {}
    lowlink = {}
    on_stack = set()
    stack = []
    result = []
    counter = [0]

    for start in node_ids:
        if start in index_of:
            continue
        work = [(start, 0)]
        while work:
            node, pointer = work[-1]
            if pointer == 0:
                index_of[node] = counter[0]
                lowlink[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack.add(node)

            neighbors = adjacency.get(node, ())
            recursed = False
            while pointer < len(neighbors):
                neighbor = neighbors[pointer]
                pointer += 1
                if neighbor not in index_of:
                    work[-1] = (node, pointer)
                    work.append((neighbor, 0))
                    recursed = True
                    break
                if neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[neighbor])

            if recursed:
                continue

            work.pop()
            if lowlink[node] == index_of[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(component)
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return result


def _cycle_violations(node_ids, adjacency, name_by_id):
    violations = {}
    for component in _strongly_connected_components(node_ids, adjacency):
        is_cycle = len(component) > 1 or (
            len(component) == 1 and component[0] in adjacency.get(component[0], ())
        )
        if not is_cycle:
            continue
        names = sorted(name_by_id.get(member, str(member)) for member in component)
        sample = ', '.join(names[:6])
        if len(names) > 6:
            sample += f', +{len(names) - 6} more'
        message = f'Circular dependency among: {sample}'
        for member in component:
            bucket = violations.setdefault(member, [])
            if len(bucket) < MAX_VIOLATIONS_PER_NODE and len(violations) <= MAX_VIOLATIONS:
                bucket.append(message)
    return violations


def _layer_violations(edge_pairs, layer_by_id, name_by_id):
    """Flag dependencies that point back up the intended layer stack."""
    violations = {}
    for source_id, target_id in edge_pairs:
        source_layer = layer_by_id.get(source_id)
        target_layer = layer_by_id.get(target_id)
        if source_layer not in INVERSION_SOURCES or target_layer not in LAYER_RANK:
            continue
        if LAYER_RANK[target_layer] >= LAYER_RANK[source_layer]:
            continue
        message = (
            f'Layer inversion: {source_layer} module imports '
            f"{target_layer} '{name_by_id.get(target_id, target_id)}'"
        )
        bucket = violations.setdefault(source_id, [])
        if len(bucket) < MAX_VIOLATIONS_PER_NODE and len(violations) <= MAX_VIOLATIONS:
            bucket.append(message)
    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_project(project_id, paths=None, full=False):
    """(Re)build the graph for a project.

    `paths` is a list of project-relative files to refresh (watcher-driven
    incremental mode); pass `full=True` to force a complete re-walk.
    """
    project = Project.query.get(project_id)
    if project is None:
        raise LookupError(f'Project {project_id} not found')

    root = os.path.abspath(project.path)
    if not os.path.isdir(root):
        raise NotADirectoryError(f'Project folder does not exist: {project.path}')

    relative_subset = None if full or paths is None else list(paths)

    with _ANALYZE_LOCK:
        started = time.time()
        targets, truncated = _collect_targets(root, relative_subset)
        aliases = _load_path_aliases(root)

        existing_nodes = Node.query.filter_by(project_id=project_id).all()
        by_absolute = {}
        for node in existing_nodes:
            absolute = _normalize_abs(root, node.file_path)
            if absolute:
                by_absolute[absolute] = node

        target_set = set(targets)
        created = updated = skipped = 0

        touched_nodes = []
        for absolute in targets:
            parsed = _parse_file(absolute, root)
            if parsed is None:
                skipped += 1
                continue

            node = by_absolute.pop(absolute, None)
            if node is None:
                node = Node(project_id=project_id, name=parsed['filename'], file_path=absolute)
                node.metadata_json = {}
                db.session.add(node)
                created += 1
            else:
                updated += 1
            node.file_path = absolute
            node.node_type = parsed['layer']
            node.metadata_json = {
                'language': parsed['language'],
                'loc': parsed['loc'],
                'imports': parsed['imports'],
                'imports_count': len(parsed['imports']),
                'exports': parsed['exports'],
                'exports_count': len(parsed['exports']),
                'complexity': parsed['complexity'],
                'is_test': parsed['is_test'],
                'analyzed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            }
            touched_nodes.append(node)

        # Files that vanished from disk (deleted or renamed) leave the graph.
        # Files merely absent from an incremental subset stay untouched.
        deleted = 0
        deleted_ids = set()
        for absolute, node in by_absolute.items():
            if os.path.isfile(absolute):
                continue
            db.session.delete(node)
            deleted_ids.add(id(node))
            deleted += 1

        # --- naming pass (deterministic, collision-free) --------------------
        # Runs before the flush so duplicate placeholder names never reach the
        # UNIQUE(project_id, name) index.
        touched_node_ids = {id(node) for node in touched_nodes}
        used_names = {
            node.name
            for node in existing_nodes
            if id(node) not in touched_node_ids and id(node) not in deleted_ids
        }
        for node in sorted(touched_nodes, key=lambda item: item.file_path or ''):
            relative = _relative_to(root, node.file_path) or node.name
            node.name = _unique_name(relative, used_names)

        db.session.flush()

        # --- edge rebuild --------------------------------------------------
        nodes = Node.query.filter_by(project_id=project_id).all()
        node_ids = [node.id for node in nodes]
        name_by_id = {node.id: node.name for node in nodes}
        relative_by_id = {node.id: _relative_to(root, node.file_path) for node in nodes}
        layer_by_id = {node.id: (node.node_type or 'unknown') for node in nodes}
        known_relative = {
            relative: node.id
            for node in nodes
            if (relative := _relative_to(root, node.file_path)) is not None
        }

        if node_ids:
            Edge.query.filter(Edge.source_id.in_(node_ids)).delete(synchronize_session=False)
            db.session.flush()
            # SQLite reuses primary keys after a full delete, so stale Edge
            # identities must not linger in the session's identity map.
            for instance in list(db.session.identity_map.values()):
                if isinstance(instance, Edge):
                    db.session.expunge(instance)

        adjacency = defaultdict(list)
        edge_pairs = set()
        edges_truncated = False
        for node in nodes:
            metadata = node.metadata_json or {}
            language = metadata.get('language')
            current_relative = relative_by_id.get(node.id)
            if not current_relative:
                continue
            for spec in metadata.get('imports') or []:
                target_relative = _resolve_import(
                    spec, language, current_relative, known_relative, aliases
                )
                if not target_relative or target_relative == current_relative:
                    continue
                target_id = known_relative.get(target_relative)
                if target_id is None:
                    continue
                pair = (node.id, target_id)
                if pair in edge_pairs:
                    continue
                if len(edge_pairs) >= MAX_EDGES:
                    edges_truncated = True
                    break
                edge_pairs.add(pair)
                adjacency[node.id].append(target_id)
                db.session.add(
                    Edge(source_id=node.id, target_id=target_id, relation_type='imports')
                )
            if edges_truncated:
                break

        db.session.flush()

        # --- metrics + violation stamping ---------------------------------
        dependents = defaultdict(int)
        for source_id, target_id in edge_pairs:
            dependents[target_id] += 1

        cycle_violations = _cycle_violations(node_ids, adjacency, name_by_id)
        layer_violations = _layer_violations(edge_pairs, layer_by_id, name_by_id)
        violations = {}
        for node_id in set(cycle_violations) | set(layer_violations):
            combined = (
                cycle_violations.get(node_id, []) + layer_violations.get(node_id, [])
            )
            violations[node_id] = combined[:MAX_VIOLATIONS_PER_NODE]

        for node in nodes:
            metadata = dict(node.metadata_json or {})
            metadata['deps_count'] = len(adjacency.get(node.id, ()))
            metadata['dependents_count'] = dependents.get(node.id, 0)
            if violations.get(node.id):
                metadata['violations'] = violations[node.id]
            else:
                metadata.pop('violations', None)
            node.metadata_json = metadata

        db.session.commit()

        return {
            'status': 'success',
            'project_id': project_id,
            'mode': 'full' if relative_subset is None else 'incremental',
            'files_scanned': len(targets),
            'nodes_created': created,
            'nodes_updated': updated,
            'nodes_deleted': deleted,
            'nodes_skipped': skipped,
            'nodes_total': len(nodes),
            'edges': len(edge_pairs),
            'violations': len(violations),
            'truncated': bool(truncated or edges_truncated),
            'duration_ms': int((time.time() - started) * 1000),
        }
