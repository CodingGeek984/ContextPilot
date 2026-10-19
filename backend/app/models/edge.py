from datetime import datetime
from database.db import db


class Edge(db.Model):
    __tablename__ = 'edges'
    __table_args__ = (
        db.UniqueConstraint('source_id', 'target_id', 'relation_type', name='uq_edge'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_id = db.Column(
        db.Integer,
        db.ForeignKey('nodes.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    target_id = db.Column(
        db.Integer,
        db.ForeignKey('nodes.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    relation_type = db.Column(db.String(50), nullable=False, default='related')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    source_node = db.relationship('Node', foreign_keys=[source_id], back_populates='outgoing_edges')
    target_node = db.relationship('Node', foreign_keys=[target_id], back_populates='incoming_edges')

    def to_dict(self):
        return {
            'id': self.id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation_type': self.relation_type,
        }