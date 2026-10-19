from flask import Blueprint, jsonify, request

from controllers.mcp_controller import McpController
from schemas.mcp_schema import (
    CloseSessionResponse,
    ContextRequest,
    ContextResponse,
    SearchResponse,
)
from schemas.validation import dump, parse_body

mcp_bp = Blueprint('mcp', __name__)


@mcp_bp.post('/api/mcp/context')
def get_context():
    data, error = parse_body(ContextRequest)
    if error is not None:
        return error

    body, status = McpController.get_context()
    if status != 200:
        return body, status

    return jsonify(dump(ContextResponse, body.get_json())), status


@mcp_bp.get('/api/mcp/search')
def search_nodes():
    body, status = McpController.search_nodes()
    if status != 200:
        return body, status

    return jsonify(dump(SearchResponse, body.get_json())), status


@mcp_bp.post('/api/mcp/close')
def close_session():
    body, status = McpController.close()
    if status != 200:
        return body, status

    return jsonify(dump(CloseSessionResponse, body.get_json())), status


@mcp_bp.post('/api/mcp/close/<int:session_id>')
def close_session_by_id(session_id: int):
    body, status = McpController.close(session_id)
    if status != 200:
        return body, status

    return jsonify(dump(CloseSessionResponse, body.get_json())), status