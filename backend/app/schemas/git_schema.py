from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class GitCommitRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    hash: str
    subject: str = ''


class GitDiffRead(BaseModel):
    """Response for GET /projects/<id>/diff."""

    model_config = ConfigDict(extra='ignore')

    status: str
    project_id: int
    available: bool
    is_repository: bool
    branch: Optional[str] = None
    window_minutes: int
    status_entries: List[str] = []
    changed_files: List[str] = []
    diff_stat: List[str] = []
    commits: List[GitCommitRead] = []
    diff: List[str] = []
    truncated: bool = False
