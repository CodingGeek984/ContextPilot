from datetime import datetime
from database.db import db


class Node(db.Model):
    __tablename__ = 'nodes'
    __table_args__ = (
        db.UniqueConstraint('project_id', 'name', name='uq_nodes_project_name'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(150), nullable=False, index=True)
    node_type = db.Column(db.String(50), nullable=False, default='unknown')
    file_path = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    project = db.relationship('Project', back_populates='nodes')

    outgoing_edges = db.relationship(
        'Edge',
        foreign_keys='Edge.source_id',
        back_populates='source_node',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    incoming_edges = db.relationship(
        'Edge',
        foreign_keys='Edge.target_id',
        back_populates='target_node',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'node_type': self.node_type,
            'file_path': self.file_path,
            'metadata': self.metadata_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }