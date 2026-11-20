from pydantic import BaseModel, Field
from typing import Any

class SyncPushItem(BaseModel):
    id: str = Field(min_length=1,max_length=36)
    entity_type: str
    entity_id: str = Field(min_length=1,max_length=36)
    operation: str  # create, update, delete
    payload: dict
    base_version: int | None = None
    timestamp: str | None = None

class SyncPushRequest(BaseModel):
    operations: list[SyncPushItem] = Field(max_length=100)

class SyncPullResponse(BaseModel):
    operations: list[dict]
    server_time: str

class ConflictOut(BaseModel):
    operation_id: str
    entity_type: str
    entity_id: str = Field(min_length=1,max_length=36)
    local_version: int | None
    server_version: int | None
    message: str
