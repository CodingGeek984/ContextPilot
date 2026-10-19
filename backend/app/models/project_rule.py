from datetime import datetime, timezone
from database.db import db


class ProjectRule(db.Model):
    __tablename__ = 'project_rules'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    project_id = db.Column(
        db.Integer,
        db.ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    # 'general', 'cursor', 'opencode', 'mcp', ...
    rule_type = db.Column(db.String(50), nullable=False, default='general')

    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    project = db.relationship('Project', back_populates='rules')

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'rule_type': self.rule_type,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<ProjectRule id={self.id} project_id={self.project_id} type={self.rule_type}>'