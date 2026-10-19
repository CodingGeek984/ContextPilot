"""End-to-end smoke test: exercises every endpoint against a real SQLite DB.

    python smoke_test.py

Exits non-zero if any check fails.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['FLASK_CONFIG'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ.setdefault('SECRET_KEY', 'test-secret')

from app import create_app  # noqa: E402
from database.db import db  # noqa: E402
from models.edge import Edge  # noqa: E402
from models.node import Node  # noqa: E402

FAILURES = []
CHECKS = 0


def check(label, condition, extra=''):
    global CHECKS
    CHECKS += 1
    if condition:
        print(f'  PASS  {label}')
    else:
        print(f'  FAIL  {label} {extra}')
        FAILURES.append(label)


def section(title):
    print(f'\n== {title}')


def main():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        db.drop_all()
        db.create_all()

    section('health')
    res = client.get('/api/health')
    body = res.get_json()
    check('GET /api/health -> 200', res.status_code == 200, res.status_code)
    check('health reports ok', body.get('status') == 'ok', body)
    check('health db connected', body.get('database') == 'connected', body)
    res = client.get('/api/health/live')
    check('GET /api/health/live -> 200', res.status_code == 200, res.status_code)

    section('projects')
    res = client.post('/api/projects/scan', json={'name': 'Scooter', 'path': '/tmp/scooter'})
    body = res.get_json()
    project = body.get('project') or {}
    check('POST scan -> 201', res.status_code == 201, (res.status_code, body))
    check('scan returns project id', isinstance(project.get('id'), int), body)
    check('scan returns path', project.get('path') == '/tmp/scooter', body)
    check('scan returns timestamps', project.get('created_at') is not None, body)
    project_id = project.get('id') or 1

    res = client.post('/api/projects/scan', json={'name': 'Scooter2', 'path': '/tmp/scooter'})
    body = res.get_json()
    rescan = body.get('project') or {}
    check('re-scan updates same project', rescan.get('id') == project_id, body)
    check('re-scan updates name', rescan.get('name') == 'Scooter2', body)

    res = client.post('/api/projects/scan', json={'name': 'Second', 'path': '/tmp/second'})
    check('second project created -> 201', res.status_code == 201, res.status_code)

    res = client.get('/api/projects')
    body = res.get_json()
    check('GET /api/projects -> 200', res.status_code == 200, res.status_code)
    check('projects list has 2 items', isinstance(body, list) and len(body) == 2, body)
    check('project item has isoformat timestamps',
          all('T' in (p.get('created_at') or '') for p in body), body)

    res = client.get(f'/api/projects/{project_id}')
    check('GET project -> 200', res.status_code == 200, res.status_code)
    check('project payload fields',
          set(res.get_json() or {}) >= {'id', 'name', 'path', 'created_at'}, res.get_json())

    res = client.get('/api/projects/99999')
    check('GET unknown project -> 404', res.status_code == 404, res.status_code)

    res = client.post('/api/projects/scan', json={'name': 'NoPath'})
    check('scan without path -> 400', res.status_code == 400, (res.status_code, res.get_json()))

    res = client.post('/api/projects/scan', data='not-json', content_type='text/plain')
    check('scan with non-JSON body -> 400', res.status_code == 400, (res.status_code, res.get_json()))

    section('graph (seeded directly, no ingestion endpoint exists)')
    with app.app_context():
        nodes = [
            Node(project_id=project_id, name='OrderController', node_type='class',
                 file_path='app/controllers/order_controller.py',
                 metadata_json={'lines': 120}),
            Node(project_id=project_id, name='OrderService', node_type='class',
                 file_path='app/services/order_service.py', metadata_json={'lines': 80}),
            Node(project_id=project_id, name='create_order', node_type='function',
                 file_path='app/routes/order_routes.py'),
        ]
        db.session.add_all(nodes)
        db.session.flush()
        db.session.add_all([
            Edge(source_id=nodes[0].id, target_id=nodes[1].id, relation_type='uses'),
            Edge(source_id=nodes[0].id, target_id=nodes[2].id, relation_type='calls'),
            Edge(source_id=nodes[1].id, target_id=nodes[2].id, relation_type='imports'),
        ])
        db.session.commit()
        first_node_id = nodes[0].id
        third_node_id = nodes[2].id

    res = client.get(f'/api/projects/{project_id}/graph')
    body = res.get_json()
    check('GET graph -> 200', res.status_code == 200, res.status_code)
    check('graph has 3 nodes', len(body.get('nodes', [])) == 3, body)
    check('graph has 3 edges', len(body.get('edges', [])) == 3, body)
    check('graph node has name/type',
          all({'id', 'name', 'type', 'file_path'} <= set(n) for n in body.get('nodes', [])), body)
    check('graph edges expose source/target',
          all({'source', 'target', 'relation_type'} <= set(e) for e in body.get('edges', [])), body)
    check('graph node metadata serialised',
          any(n.get('metadata') == {'lines': 120} for n in body.get('nodes', [])), body)

    res = client.get(f'/api/projects/{project_id}/graph/stats')
    body = res.get_json()
    check('GET graph/stats -> 200', res.status_code == 200, res.status_code)
    check('stats counts nodes/edges',
          body.get('total_nodes') == 3 and body.get('total_edges') == 3, body)

    res = client.get(f'/api/projects/{project_id}/nodes/{first_node_id}')
    body = res.get_json()
    check('GET node details -> 200', res.status_code == 200, res.status_code)
    check('node details outgoing links', len(body.get('outgoing_links', [])) == 2, body)
    check('node details incoming links', len(body.get('incoming_links', [])) == 0, body)

    res = client.get(f'/api/projects/{project_id}/nodes/{third_node_id}')
    body = res.get_json()
    check('target node incoming links', len(body.get('incoming_links', [])) == 2, body)

    res = client.get(f'/api/projects/{project_id}/nodes/99999')
    check('GET unknown node -> 404', res.status_code == 404, res.status_code)

    res = client.get('/api/projects/99999/graph')
    check('GET graph unknown project -> 404', res.status_code == 404, res.status_code)

    res = client.get('/api/projects/99999/graph/stats')
    check('GET stats unknown project -> 404', res.status_code == 404, res.status_code)

    section('rules')
    res = client.post('/api/rules/sync', json={
        'project_id': project_id,
        'rules': ['Always use type hints', {'content': 'Run tests before commit'}],
    })
    body = res.get_json()
    check('POST sync -> 200', res.status_code == 200, (res.status_code, body))
    check('sync counted 2 rules', body.get('synced_count') == 2, body)

    res = client.get(f'/api/rules?project_id={project_id}')
    body = res.get_json()
    check('GET rules -> 200', res.status_code == 200, res.status_code)
    check('rules list key present', 'rules' in body, body)
    check('rules count == 2', body.get('count') == 2, body)
    check('rules content correct',
          {r['content'] for r in body.get('rules', [])} ==
          {'Always use type hints', 'Run tests before commit'}, body)
    check('rule_type defaults to general',
          all(r['rule_type'] == 'general' for r in body.get('rules', [])), body)

    rule_id = (body.get('rules') or [{}])[0].get('id', 1)
    res = client.get(f'/api/rules/{rule_id}')
    body = res.get_json()
    check('GET rule -> 200', res.status_code == 200, res.status_code)
    check('rule payload has project_id', body.get('rule', {}).get('project_id') == project_id, body)

    res = client.get('/api/rules/99999')
    check('GET unknown rule -> 404', res.status_code == 404, res.status_code)

    res = client.get('/api/rules')
    check('GET rules without project_id -> 400', res.status_code == 400, res.status_code)

    res = client.get('/api/rules?project_id=99999')
    check('GET rules unknown project -> 404', res.status_code == 404, res.status_code)

    res = client.post('/api/rules/sync', json={'project_id': project_id, 'rules': []})
    check('sync with empty rules -> 400', res.status_code == 400, (res.status_code, res.get_json()))

    res = client.post('/api/rules/sync', json={'project_id': 99999, 'rules': ['x']})
    check('sync unknown project -> 404', res.status_code == 404, res.status_code)

    res = client.post('/api/rules/sync', json={'project_id': project_id, 'rules': ['replaced']})
    body = res.get_json()
    check('re-sync replaces rules', body.get('synced_count') == 1, body)
    res = client.get(f'/api/rules?project_id={project_id}')
    check('only 1 rule after re-sync', res.get_json().get('count') == 1, res.get_json())

    section('mcp')
    res = client.post('/api/mcp/context', json={
        'project_id': project_id,
        'node_name': 'OrderController',
    })
    body = res.get_json()
    check('POST context -> 200', res.status_code == 200, (res.status_code, body))
    check('context main node', body.get('main_node', {}).get('name') == 'OrderController', body)
    check('context has 2 relations', len(body.get('relations', [])) == 2, body)
    session_id = body.get('session_id')
    check('context returned session_id', isinstance(session_id, int), body)

    res = client.post('/api/mcp/context', json={
        'project_id': project_id,
        'node_name': 'OrderController',
        'session_id': session_id,
    })
    check('context reuses session', res.get_json().get('session_id') == session_id, res.get_json())

    res = client.post('/api/mcp/context', json={'project_id': project_id, 'node_name': 'Ghost'})
    check('context unknown node -> 404', res.status_code == 404, res.status_code)

    res = client.post('/api/mcp/context', json={'project_id': 99999, 'node_name': 'x'})
    check('context unknown project -> 404', res.status_code == 404, res.status_code)

    res = client.post('/api/mcp/context', json={'project_id': project_id})
    check('context without node_name -> 400', res.status_code == 400, res.status_code)

    res = client.get(f'/api/mcp/search?project_id={project_id}&query=Order')
    body = res.get_json()
    check('GET search -> 200', res.status_code == 200, res.status_code)
    check('search found 3 nodes', body.get('count') == 3, body)
    check('search result shape',
          all({'id', 'name', 'file_path', 'type'} <= set(r) for r in body.get('results', [])), body)

    res = client.get(f'/api/mcp/search?query=Order')
    check('search without project_id -> 400', res.status_code == 400, res.status_code)

    res = client.get(f'/api/mcp/search?project_id={project_id}')
    check('search without query -> 400', res.status_code == 400, res.status_code)

    res = client.post(f'/api/mcp/close/{session_id}')
    body = res.get_json()
    check('POST close -> 200', res.status_code == 200, (res.status_code, body))
    check('close returns closed status', body.get('status') == 'closed', body)

    res = client.post('/api/mcp/close/99999')
    check('close unknown session -> 404', res.status_code == 404, res.status_code)

    res = client.post('/api/mcp/close', json={})
    check('close without session_id -> 400', res.status_code == 400, res.status_code)

    with app.app_context():
        from models.mcp_session import Mcp_Session
        from models.project_rule import ProjectRule
        session = db.session.get(Mcp_Session, session_id)
        check('session status persisted', session is not None and session.status == 'closed',
              session.status if session else None)
        check('session updated_at tracked', session is not None and session.updated_at is not None)
        check('rule_type filter works',
              ProjectRule.query.filter_by(project_id=project_id, rule_type='general').count() == 1)

    section('cascade delete')
    res = client.delete(f'/api/projects/{project_id}')
    check('DELETE project -> 200', res.status_code == 200, res.status_code)

    with app.app_context():
        check('nodes cascade deleted', Node.query.filter_by(project_id=project_id).count() == 0)
        check('edges cascade deleted', Edge.query.filter_by(source_id=first_node_id).count() == 0)
        from models.mcp_session import Mcp_Session
        from models.project_rule import ProjectRule
        check('rules cascade deleted', ProjectRule.query.filter_by(project_id=project_id).count() == 0)
        check('sessions cascade deleted', Mcp_Session.query.filter_by(project_id=project_id).count() == 0)

    res = client.get('/api/projects')
    check('one project left after delete', len(res.get_json()) == 1, res.get_json())

    res = client.get('/api/projects')
    check('unknown route -> 404 json', client.get('/api/nope').status_code == 404)
    check('404 returns JSON', client.get('/api/nope').is_json)

    print(f'\n{"=" * 46}')
    print(f'{CHECKS - len(FAILURES)}/{CHECKS} checks passed')
    if FAILURES:
        print('FAILED:')
        for name in FAILURES:
            print(f'  - {name}')
        return 1
    print('ALL GREEN')
    return 0


if __name__ == '__main__':
    sys.exit(main())