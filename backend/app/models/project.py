from database.db import db
from datetime import datetime


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    path = db.Column(db.Text, nullable=False, unique=True)
    db_connection_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    nodes = db.relationship(
        'Node',
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    rules = db.relationship(
        'ProjectRule',
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    mcp_sessions = db.relationship(
        'Mcp_Session',
        back_populates='project',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'db_connection_url': self.db_connection_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }