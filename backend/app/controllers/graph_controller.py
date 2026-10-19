from flask import jsonify, request
from database.db import db 
from models.node import Node 
from models.edge import Edge 
from models.project import Project

class GraphController:

    @staticmethod 
    def get_graph(project_id: int):

        project = Project.query.get(project_id)

        if not project:
            return jsonify({
                'message': 'Project with this ID not found'
            }), 404

        nodes = Node.query.filter_by(project_id=project_id).all()

        node_ids = []
        for node in nodes:
            node_ids.append(node.id)

        edges = []
        if node_ids:
            edges = Edge.query.filter(Edge.source_id.in_(node_ids)).all()

        node_list = []
        for node in nodes:
            node_list.append({
                'id': node.id,
                'name': node.name,
                'type': node.node_type,
                'file_path': node.file_path,
                'metadata': node.metadata_json
            })

        edges_list = []
        for edge in edges:
            edges_list.append({
                'id': edge.id,
                'source': edge.source_id,
                'target': edge.target_id,
                'relation_type': edge.relation_type
            })

        return jsonify({
            'project_id': project_id,
            'nodes': node_list,
            'edges': edges_list
        }), 200


    @staticmethod 
    def get_graph_details(project_id: int, node_id: str):

        node = Node.query.filter_by(id=node_id, project_id=project_id).first()

        if not node:
            return jsonify({
                'error': 'Node not found'
            }), 404

        outgoing_edge = Edge.query.filter_by(source_id=node_id).all()
        outgoing_list = []
        for edge in outgoing_edge:
            outgoing_list.append({
                'target_id': edge.target_id,
                'relation_type': edge.relation_type
            })

        incoming_edges = Edge.query.filter_by(target_id=node_id).all()
        incoming_list = []
        for edge in incoming_edges:
            incoming_list.append({
                'source_id': edge.source_id,
                'relation_type': edge.relation_type
            })

        return jsonify({
            'id': node.id,
            'name': node.name,
            'node_type': node.node_type,
            'file_path': node.file_path,
            'metadata': node.metadata_json,
            'outgoing_links': outgoing_list,
            'incoming_links': incoming_list
        }), 200


    @staticmethod 
    def get_graph_stats(project_id: int):

        project = Project.query.get(project_id)

        if not project:
            return jsonify({
                'error': 'Project not found'
            }), 404

        nodes = Node.query.filter_by(project_id=project_id).all()
        node_ids = []
        for node in nodes:
            node_ids.append(node.id)

        edges_count = 0
        if node_ids:
            edges_count = Edge.query.filter(Edge.source_id.in_(node_ids)).count()

        return jsonify({
            'project_id': project_id,
            'total_nodes': len(nodes),
            'total_edges': edges_count
        }), 200

    

        