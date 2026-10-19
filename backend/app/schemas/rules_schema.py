from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuleCreate(BaseModel):
    content: str = Field(..., min_length=1)
    rule_type: str = Field(default='general', max_length=50)


class RuleRead(BaseModel):
    model_config = ConfigDict(extra='ignore')

    id: int
    project_id: Optional[int] = None
    rule_type: str = 'general'
    content: str
    created_at: Optional[str] = None


class RulesListResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'success'
    count: int = 0
    rules: List[RuleRead] = []


class RuleResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'success'
    rule: RuleRead


class SyncRulesRequest(BaseModel):
    project_id: int
    rules: List[Union[str, RuleCreate]]
    rule_type: str = Field(default='general', max_length=50)

    @field_validator('rules')
    @classmethod
    def _rules_not_empty(cls, value):
        if not value:
            raise ValueError('rules must be a non-empty list')
        return value


class SyncRulesResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'success'
    synced_count: int = 0
    message: str = ''


class ClearRulesResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')

    status: str = 'success'
    deleted_count: int = 0
    message: str = ''