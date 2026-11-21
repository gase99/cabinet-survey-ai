
from pydantic import BaseModel, Field


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


class ConflictResolveRequest(BaseModel):
    resolution: str = Field(pattern="^(keep_server|keep_local)$")
    payload: dict | None = None
    base_version: int | None = Field(strict=True, default=None, ge=1)

