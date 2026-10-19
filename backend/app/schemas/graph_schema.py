from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EdgeRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    source: Optional[int] = None
    target: Optional[int] = None
    source_id: Optional[int] = None
    target_id: Optional[int] = None
    relation_type: str


class NodeRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    type: Optional[str] = None
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    filter_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class GraphRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    project_id: int
    nodes: List[NodeRead] = []
    edges: List[EdgeRead] = []


class GraphLink(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = None
    target_id: Optional[int] = None
    source_id: Optional[int] = None
    relation_type: Optional[str] = None


class NodeDetailsRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    node_type: Optional[str] = None
    file_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    outgoing_links: List[GraphLink] = []
    incoming_links: List[GraphLink] = []


class GraphStatsRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    project_id: int
    total_nodes: int
    total_edges: int


class AnalyzeRequest(BaseModel):
    """Body for POST /projects/<id>/analyze."""

    model_config = ConfigDict(extra='ignore')

    paths: Optional[List[str]] = None
    full: bool = False


class AnalyzeResult(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str
    project_id: int
    mode: str
    files_scanned: int
    nodes_created: int
    nodes_updated: int
    nodes_deleted: int
    nodes_skipped: int
    nodes_total: int
    edges: int
    violations: int
    truncated: bool
    duration_ms: int


class NodeCreate(BaseModel):
    """Payload used by graph ingestion tooling."""

    name: str = Field(..., min_length=1, max_length=150)
    node_type: str = Field(default='unknown', max_length=50)
    file_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EdgeCreate(BaseModel):
    source_id: int
    target_id: int
    relation_type: str = Field(default='related', max_length=50)