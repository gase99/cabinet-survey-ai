from datetime import datetime
from pydantic import BaseModel, Field


class RoomCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    room_type: str = Field(default="rectangular", pattern="^(rectangular|L|U|irregular)$")


class RoomUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    room_type: str | None = Field(default=None, pattern="^(rectangular|L|U|irregular)$")
    version: int | None = Field(strict=True, default=None, ge=1)
    base_version: int | None = Field(strict=True, default=None, ge=1)


class RoomOut(BaseModel):
    id: str
    project_id: str
    label: str
    room_type: str
    version: int
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
