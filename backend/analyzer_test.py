"""Analyzer + git-diff end-to-end test against a throwaway fixture folder.

    python analyzer_test.py

Builds a small mixed-language fixture, runs the real ``/analyze`` endpoint and
asserts that nodes, import edges, circular dependencies, layer inversions,
incremental updates, file removal and the ``/diff`` endpoint all behave.

Exits non-zero if any check fails.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['FLASK_CONFIG'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ.setdefault('SECRET_KEY', 'test-secret')

from app import create_app  # noqa: E402
from database.db import db  # noqa: E402

FIXTURE_FILES = {
    'controllers/order_controller.py': (
        'from services.order_service import OrderService\n\n'
        'class OrderController:\n'
        '    def create(self):\n'
        '        return OrderService().create()\n'
    ),
    'services/order_service.py': (
        'from repositories.order_repository import OrderRepository\n\n'
        'class OrderService:\n'
        '    def create(self):\n'
        '        return OrderRepository().save()\n'
    ),
    'repositories/order_repository.py': (
        'from models.order import Order\n\n'
        'class OrderRepository:\n'
        '    def save(self):\n'
        '        return Order()\n'
    ),
    'models/order.py': (
        'from services.audit_service import AuditService\n\n'
        'class Order:\n'
        '    def validate(self):\n'
        '        return AuditService()\n'
    ),
    'services/audit_service.py': (
        'class AuditService:\n'
        '    def record(self):\n'
        '        return True\n'
    ),
    'src/lib/helper.js': 'export function helper() {\n  return 1;\n}\n',
    'src/app.js': "import { helper } from '@/lib/helper';\n\nexport const value = helper();\n",
    'web/a.js': "import { b } from './b';\n\nexport const a = () => b();\n",
    'web/b.js': "import { a } from './a';\n\nexport const b = () => a();\n",
    'jsconfig.json': json.dumps({
        'compilerOptions': {'baseUrl': '.', 'paths': {'@/*': ['src/*']}}
    }),
}


def check(label, condition, extra=''):
    print(('  PASS  ' if condition else '  FAIL  ') + label + ('' if condition else f'  {extra}'))
    return bool(condition)


def section(title):
    print(f'\n== {title}')


def write_fixture(root):
    for relative, content in FIXTURE_FILES.items():
        absolute = os.path.join(root, relative)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, 'w', encoding='utf-8') as handle:
            handle.write(content)


def git(args, cwd):
    return subprocess.run(
        ['git', '-C', cwd, *args], capture_output=True, text=True, check=True
    )


def main():
    app = create_app('testing')
    client = app.test_client()
    with app.app_context():
        db.drop_all()
        db.create_all()

    results = []
    root = tempfile.mkdtemp(prefix='contextpilot-analyzer-')
    try:
        write_fixture(root)

        section('scan + full analyze')
        res = client.post('/api/projects/scan', json={'name': 'Fixture', 'path': root})
        project_id = (res.get_json().get('project') or {}).get('id')
        results.append(check('project registered', bool(project_id), res.get_json()))

        res = client.post(f'/api/projects/{project_id}/analyze', json={'full': True})
        body = res.get_json()
        results.append(check('analyze -> 200', res.status_code == 200, body))
        results.append(check('analyze scanned the fixture', body.get('files_scanned') == 9, body))
        results.append(check('node per source file', body.get('nodes_total') == 9, body))
        results.append(check('import edges resolved', body.get('edges') == 7, body))
        results.append(check('incremental mode is full', body.get('mode') == 'full', body))

        section('graph payload')
        res = client.get(f'/api/projects/{project_id}/graph')
        graph = res.get_json()
        nodes = {n['name']: n for n in graph.get('nodes', [])}
        layers = {n.get('type') for n in graph.get('nodes', [])}
        results.append(check('graph exposes 9 nodes', len(graph.get('nodes', [])) == 9, graph))
        results.append(check('layers classified',
                             {'controller', 'service', 'repository', 'model', 'util'} <= layers,
                             layers))

        section('violations')
        order = nodes['order']
        order_violations = (order.get('metadata') or {}).get('violations') or []
        results.append(check('layer inversion detected on model',
                             any('Layer inversion' in v for v in order_violations),
                             order_violations))
        circular = [n['name'] for n in graph['nodes']
                    if any('Circular dependency' in v
                           for v in (n.get('metadata') or {}).get('violations') or [])]
        results.append(check('circular dependency detected',
                             set(circular) == {'a', 'b'}, circular))
        results.append(check('no false-positive inversions on controllers/services',
                             not any('Layer inversion' in v
                                     for name in ('order_controller', 'order_service',
                                                  'order_repository')
                                     for v in (nodes[name].get('metadata') or {}).get('violations') or [])))

        section('incremental analyze')
        extra = os.path.join(root, 'src/lib/extra.js')
        with open(extra, 'w', encoding='utf-8') as handle:
            handle.write("import { helper } from '@/lib/helper';\nexport const x = helper();\n")
        res = client.post(f'/api/projects/{project_id}/analyze',
                          json={'paths': ['src/lib/extra.js']})
        body = res.get_json()
        results.append(check('incremental -> 200', res.status_code == 200, body))
        results.append(check('incremental mode reported', body.get('mode') == 'incremental', body))
        results.append(check('incremental added one node', body.get('nodes_total') == 10, body))
        results.append(check('incremental added one edge', body.get('edges') == 8, body))

        section('file removal')
        os.remove(os.path.join(root, 'web/b.js'))
        res = client.post(f'/api/projects/{project_id}/analyze', json={'full': True})
        body = res.get_json()
        results.append(check('removal deleted node', body.get('nodes_total') == 9, body))
        graph = client.get(f'/api/projects/{project_id}/graph').get_json()
        remaining = [n['name'] for n in graph['nodes']
                     if any('Circular dependency' in v
                            for v in (n.get('metadata') or {}).get('violations') or [])]
        results.append(check('cycle cleared after removal', remaining == [], remaining))

        section('git diff endpoint')
        if shutil.which('git'):
            git(['init', '-q'], root)
            git(['config', 'user.email', 'test@example.com'], root)
            git(['config', 'user.name', 'Test'], root)
            git(['add', '-A'], root)
            git(['commit', '-qm', 'initial'], root)
            with open(os.path.join(root, 'src/lib/helper.js'), 'a', encoding='utf-8') as handle:
                handle.write('export const changed = true;\n')

            res = client.get(f'/api/projects/{project_id}/diff?include_diff=true')
            body = res.get_json()
            results.append(check('diff -> 200', res.status_code == 200, body))
            results.append(check('diff sees the repository', body.get('is_repository') is True, body))
            results.append(check('diff lists the changed file',
                                 any('helper.js' in f for f in body.get('changed_files', [])),
                                 body.get('changed_files')))
            results.append(check('diff includes a unified patch',
                                 any('changed' in line for line in body.get('diff', [])),
                                 body.get('diff')))

            res = client.get(f'/api/projects/{project_id}/diff?window_minutes=abc')
            results.append(check('diff clamps bad window param', res.status_code == 200))
        else:
            print('  SKIP  git not installed')

        res = client.get('/api/projects/99999/diff')
        results.append(check('diff unknown project -> 404', res.status_code == 404, res.status_code))

        section('cleanup')
        res = client.delete(f'/api/projects/{project_id}')
        results.append(check('DELETE project -> 200', res.status_code == 200, res.status_code))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    passed = sum(1 for r in results if r)
    print(f'\n{"=" * 46}')
    print(f'{passed}/{len(results)} checks passed')
    if passed != len(results):
        print('FAILED')
        return 1
    print('ALL GREEN')
    return 0


if __name__ == '__main__':
    sys.exit(main())
