from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContextRequest(BaseModel):
    project_id: int
    node_name: str = Field(..., min_length=1)
    session_id: Optional[int] = None


class RelatedNode(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    type: Optional[str] = None
    file_path: Optional[str] = None


class MainNode(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    file_path: Optional[str] = None


class ContextResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'success'
    main_node: MainNode
    relations: List[RelatedNode] = []
    session_id: Optional[int] = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'success'
    count: int = 0
    results: List[RelatedNode] = []


class CloseSessionRequest(BaseModel):
    session_id: Optional[int] = None


class CloseSessionResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'closed'
    session_id: Optional[int] = None
    message: str = ''