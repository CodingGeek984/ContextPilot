from flask import Blueprint, jsonify

from controllers.rules_controller import RulesController
from schemas.rules_schema import (
    ClearRulesResponse,
    RuleResponse,
    RulesListResponse,
    SyncRulesRequest,
    SyncRulesResponse,
)
from schemas.validation import dump, parse_body

rules_bp = Blueprint('rules', __name__)


@rules_bp.get('/api/rules')
def list_rules():
    body, status = RulesController.list_rules()
    if status != 200:
        return body, status

    return jsonify(dump(RulesListResponse, body.get_json())), status


@rules_bp.get('/api/rules/<int:rule_id>')
def get_rule(rule_id: int):
    body, status = RulesController.get_rule(rule_id)
    if status != 200:
        return body, status

    return jsonify(dump(RuleResponse, body.get_json())), status


@rules_bp.post('/api/rules/sync')
def sync_rules():
    data, error = parse_body(SyncRulesRequest)
    if error is not None:
        return error

    body, status = RulesController.sync_rules()
    if status != 200:
        return body, status

    return jsonify(dump(SyncRulesResponse, body.get_json())), status


@rules_bp.delete('/api/rules')
def clear_rules():
    body, status = RulesController.clear_rules()
    if status != 200:
        return body, status

    return jsonify(dump(ClearRulesResponse, body.get_json())), status