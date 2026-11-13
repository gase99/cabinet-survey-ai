from pydantic import BaseModel
from typing import Any

class SyncPushItem(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    operation: str  # create, update, delete
    payload: dict
    base_version: int | None = None
    timestamp: str | None = None

class SyncPushRequest(BaseModel):
    operations: list[SyncPushItem]

class SyncPullResponse(BaseModel):
    operations: list[dict]
    server_time: str

class ConflictOut(BaseModel):
    operation_id: str
    entity_type: str
    entity_id: str
    local_version: int | None
    server_version: int | None
    message: str
