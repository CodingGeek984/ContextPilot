from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Request body for registering / re-scanning a project."""

    name: str = Field(..., min_length=1, max_length=100)
    path: str = Field(..., min_length=1)
    db_connection_url: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    path: Optional[str] = Field(default=None, min_length=1)
    db_connection_url: Optional[str] = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    path: str
    db_connection_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    message: str
    project: ProjectRead


class ErrorResponse(BaseModel):
    error: Optional[str] = None
    message: Optional[str] = None
    details: Optional[str] = None