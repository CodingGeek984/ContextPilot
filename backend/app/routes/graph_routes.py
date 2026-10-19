from flask import Blueprint, jsonify, request

from controllers.analysis_controller import AnalysisController
from controllers.graph_controller import GraphController
from schemas.graph_schema import (
    AnalyzeRequest,
    AnalyzeResult,
    GraphRead,
    GraphStatsRead,
    NodeDetailsRead,
)
from schemas.validation import dump, parse_body

graph_bp = Blueprint('graph', __name__)


@graph_bp.post('/api/projects/<int:project_id>/analyze')
def analyze_project(project_id: int):
    """(Re)build the architecture graph from the project folder."""
    payload = request.get_json(silent=True) or {}
    data, error = parse_body(AnalyzeRequest, payload)
    if error is not None:
        return error

    body, status = AnalysisController.analyze(
        project_id, paths=data.paths, full=data.full
    )
    if status != 200:
        return body, status

    return jsonify(dump(AnalyzeResult, body.get_json())), status


@graph_bp.get('/api/projects/<int:project_id>/graph')
def get_graph(project_id: int):
    body, status = GraphController.get_graph(project_id)
    if status != 200:
        return body, status

    return jsonify(dump(GraphRead, body.get_json())), status


@graph_bp.get('/api/projects/<int:project_id>/graph/stats')
def get_graph_stats(project_id: int):
    body, status = GraphController.get_graph_stats(project_id)
    if status != 200:
        return body, status

    return jsonify(dump(GraphStatsRead, body.get_json())), status


@graph_bp.get('/api/projects/<int:project_id>/nodes/<int:node_id>')
def get_graph_details(project_id: int, node_id: int):
    body, status = GraphController.get_graph_details(project_id, node_id)
    if status != 200:
        return body, status

    return jsonify(dump(NodeDetailsRead, body.get_json())), status