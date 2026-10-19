from datetime import datetime
from database.db import db


class Mcp_Session(db.Model):
    __tablename__ = 'mcp_sessions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    client_name = db.Column(db.String(50), nullable=True, default='unknown')
    query_prompt = db.Column(db.Text, nullable=True)
    injected_context_summary = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='active')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    project = db.relationship('Project', back_populates='mcp_sessions')

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'client_name': self.client_name,
            'query_prompt': self.query_prompt,
            'injected_context_summary': self.injected_context_summary,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<Mcp_Session id={self.id} project_id={self.project_id} status={self.status}>'