from flask import request, jsonify 
from database.db import db 
from models.project import Project 
from models.node import Node 
from models.edge import Edge
from datetime import datetime

class ProjectController:

    @staticmethod 
    def scan_projects(project_id: int):
        data = request.get_json()

        if not data or not data.get('path') or not data.get('name'):
            return jsonify({
                'error': 'Missing required fields: name and path are required'
            }), 400

        name = data.get('name')
        path = data.get('path')
        db_connection_url = data.get('db_connection_url')

        project = Project.query.filter_by(path=path).first()

        if project:
            project.name = name
            project.db_connection_url = db_connection_url
            project.updated_at = datetime.utcnow()
        else:
            project = Project(
                name=name,
                path=path,
                db_connection_url=db_connection_url
            )
            db.session.add(project)
            status_code = 201 

        db.session.commit()

        return jsonify({
            'message': 'Project scan completed successfully',
            'project': {
                'id': project.id,
                'name': project.name,
                'path': project.path,
                'db_connection_url': project.db_connection_url,
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'updated_at': project.updated_at.isoformat() if project.updated_at else None
            }
        }), 201



    @staticmethod 
    def get_projects():

        projects = Project.query.all()
        result = []

        for project in projects:
            result.append({
                'id': project.id,
                'name': project.name,
                'path': project.path,
                'db_connection_url': project.db_connection_url,
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'updated_at': project.updated_at.isoformat() if project.updated_at else None
            })

        return jsonify(result), 200


    @staticmethod 
    def get_project(project_id: int):

        project = Project.query.get(project_id)

        if not project:
            return jsonify({
                'error': 'Project not found'
            }), 404

        return jsonify({
            'id': project.id,
            'name': project.name,
            'path': project.path,
            'db_connection_url': project.db_connection_url,
            'created_at': project.created_at.isoformat() if project.created_at else None,
            'updated_at': project.updated_at.isoformat() if project.updated_at else None 
        }), 200


    @staticmethod 
    def delete_project(project_id: int):

        project = Project.query.get(project_id)

        if not project: 
            return jsonify({
                'message': 'Project not found'
            }), 404

        db.session.delete(project)
        db.session.commit()

        return jsonify({
            'message': 'Project deleted'
        }), 200
    
    