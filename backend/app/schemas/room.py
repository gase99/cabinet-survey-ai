from pydantic import BaseModel, Field
from datetime import datetime

class RoomCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    room_type: str = Field(default="rectangular", pattern="^(rectangular|L|U|irregular)$")

class RoomUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    room_type: str | None = Field(default=None, pattern="^(rectangular|L|U|irregular)$")

class RoomOut(BaseModel):
    id: str
    project_id: str
    label: str
    room_type: str
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
