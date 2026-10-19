from datetime import datetime, timezone
from flask import request, jsonify
from models.project import Project
from models.project_rule import ProjectRule
from database.db import db


class RulesController:

    @staticmethod 
    def list_rules():

        project_id = request.args.get('project_id')

        if not project_id:
            return jsonify({
                'error': 'project_id is required'
            }), 400

        project = Project.query.get(project_id)

        if not project:
            return jsonify({
                'error': 'Project not found'
            }), 404

        rules = ProjectRule.query.filter_by(project_id=project_id).all()

        rules_list = []
        for rule in rules:
            rules_list.append({
                'id': rule.id,
                'rule_type': getattr(rule, 'rule_type', 'general'),
                'content': rule.content,
                'created_at': rule.created_at.isoformat() if hasattr(rule, 'created_at') and rule.created_at else None 
            })

        return jsonify({
            'status': 'success',
            'count': len(rules_list),
            'rules': rules_list 
        }), 200


    @staticmethod 
    def get_rule(rule_id):

        rule = ProjectRule.query.get(rule_id)

        if not rule:
            return jsonify({
                'message': 'Rule not found'
            }), 404

        return jsonify({
            'status': 'success',
            'rule': {
                'id': rule.id,
                'project_id': rule.project_id,
                'rule_type': getattr(rule, 'rule_type', 'general'),
                'content': rule.content
            }
        }), 200


    @staticmethod 
    def sync_rules():

        data = request.get_json(silent=True) or {}

        project_id = data.get('project_id')
        rules_data = data.get('rules')
        rule_type = data.get('rule_type', 'general')

        if not project_id:
            return jsonify({
                'error': 'Project ID is required'
            }), 400

        if rules_data is None or not isinstance(rules_data, list):
            return jsonify({
                'error': 'Rules must be a non-empty list'
            }), 400

        project = Project.query.get(project_id)

        if not project:
            return jsonify({
                'error': 'Project not found'
            }), 404


        try:
            ProjectRule.query.filter_by(project_id=project_id, rule_type=rule_type).delete()

            new_rules = []
            for item in rules_data:
                content_str = item if isinstance(item, str) else (item or {}).get('content', '')

                if not content_str or not content_str.strip():
                    continue

                new_rules.append(ProjectRule(
                    project_id=project_id,
                    rule_type=rule_type,
                    content=content_str.strip()
                ))

            db.session.add_all(new_rules)
            db.session.commit()

            return jsonify({
                'status': 'success',
                'synced_count': len(new_rules),
                'message': f"Successfully synced {len(new_rules)} rules"
            }), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({
                'error': 'Failed to sync rules',
                'details': str(e)
            }), 500

    @staticmethod 
    def clear_rules():

        project_id = request.args.get('project_id')

        if not project_id:
            data = request.get_json(silent=True) or {}
            project_id = data.get('project_id')

        if not project_id:
            return jsonify({
                'error': 'Projet ID is required'
            }), 400

        deleted_count = ProjectRule.query.filter_by(project_id=project_id).delete()
        db.session.commit()

        return jsonify({
            'status': 'success',
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} rules for project {project_id}'
        }), 200

    