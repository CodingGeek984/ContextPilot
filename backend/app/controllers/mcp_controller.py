from datetime import datetime, timezone
from flask import request, jsonify
from models.mcp_session import Mcp_Session
from models.project import Project
from models.edge import Edge
from models.node import Node 
from database.db import db 


class McpController:

    @staticmethod 
    def get_context():
        # 1. Безопасно получаем JSON из запроса
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                'error': 'Incorrect or missing JSON'
            }), 400

        # 2. Извлекаем переменные
        project_id = data.get('project_id')
        node_name = data.get('node_name')
        session_id = data.get('session_id')

        # 3. Валидация обязательных полей (session_id необязателен)
        if not project_id or not node_name:
            return jsonify({
                'error': 'project_id and node_name are required'
            }), 400

        # 4. Проверка существования проекта
        project = Project.query.get(project_id)
        if project is None:
            return jsonify({
                'error': 'Project not found'
            }), 404

        # 5. Поиск целевого узла по project_id и name
        target_node = Node.query.filter_by(project_id=project_id, name=node_name).first()
        if target_node is None:
            return jsonify({
                'error': 'Target node not found'
            }), 404

        # 6. Получаем исходящие связи из БД
        outgoing_edges = Edge.query.filter_by(source_id=target_node.id).all()

        # 7. Сбор связанных узлов в список
        related_list = []
        for edge in outgoing_edges:
            connected_id = edge.target_id 

            if not connected_id:
                continue 

            connected_node = Node.query.get(connected_id)

            if connected_node is not None:
                related_list.append({
                    'id': connected_node.id,
                    'name': connected_node.name,
                    'type': getattr(connected_node, 'type', None) or getattr(connected_node, 'node_type', None),
                    'file_path': connected_node.file_path 
                })

        # 8. Логика работы с сессией
        if session_id:
            mcp_session = Mcp_Session.query.get(session_id)
            if mcp_session:
                mcp_session.updated_at = datetime.now(timezone.utc)
            else:
                mcp_session = Mcp_Session(project_id=project_id, status='active')
                db.session.add(mcp_session)
                db.session.flush()
                session_id = mcp_session.id
        else:
            mcp_session = Mcp_Session(project_id=project_id, status='active')
            db.session.add(mcp_session)
            db.session.flush()
            session_id = mcp_session.id

        db.session.commit()

        # 9. Возврат итогового контекста
        return jsonify({
            'status': 'success',
            'main_node': {
                'id': target_node.id,
                'name': target_node.name,
                'file_path': target_node.file_path
            },
            'relations': related_list,
            'session_id': session_id
        }), 200

    @staticmethod
    def search_nodes():
        # Принимаем параметры из query string (например: /api/mcp/search?project_id=1&query=Scooter)
        project_id = request.args.get('project_id')
        query = request.args.get('query')

        if not project_id:
            return jsonify({
                'error': 'Project ID is required'
            }), 400

        if not query:
            return jsonify({
                'error': 'Query is required'
            }), 400

        # Поиск по базе через LIKE
        found_nodes = Node.query.filter(
            Node.project_id == project_id,
            Node.name.ilike(f"%{query}%")
        ).all()

        results_list = []
        for node in found_nodes:
            results_list.append({
                'id': node.id,
                'name': node.name,
                'file_path': node.file_path,
                'type': getattr(node, 'type', None) or getattr(node, 'node_type', None)
            })

        return jsonify({
            'status': 'success',
            'count': len(results_list),
            'results': results_list
        }), 200

    @staticmethod 
    def close(session_id=None):
        # Если session_id не пришел из URL, пробуем достать из JSON
        if session_id is None:
            data = request.get_json(silent=True) or {}
            session_id = data.get('session_id')

        if not session_id:
            return jsonify({
                'error': 'session_id is required'
            }), 400

        mcp_session = Mcp_Session.query.get(session_id)

        if mcp_session is None:
            return jsonify({
                'error': 'Mcp session not found'
            }), 404

        mcp_session.status = 'closed'
        mcp_session.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            'status': 'closed',
            'session_id': mcp_session.id,
            'message': 'Mcp session closed successfully'
        }), 200

