from pydantic import BaseModel, Field
from datetime import datetime

class WallCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    length_mm: int = Field(ge=1, le=50000, description="Length in mm")
    height_mm: int = Field(ge=1, le=10000, default=2700)
    start_x_mm: int = 0
    start_y_mm: int = 0
    end_x_mm: int = 0
    end_y_mm: int = 0
    source: str = Field(default="manual", pattern="^(manual|sketch_ai|voice_ai|import)$")
    confidence: float | None = Field(default=None, ge=0, le=1)

class WallUpdate(BaseModel):
    label: str | None = None
    length_mm: int | None = Field(default=None, ge=1, le=50000)
    height_mm: int | None = Field(default=None, ge=1, le=10000)
    start_x_mm: int | None = None
    start_y_mm: int | None = None
    end_x_mm: int | None = None
    end_y_mm: int | None = None
    review_status: str | None = Field(default=None, pattern="^(needs_review|incomplete|approved)$")

class WallOut(BaseModel):
    id: str
    room_id: str
    label: str
    length_mm: int
    height_mm: int
    start_x_mm: int
    start_y_mm: int
    end_x_mm: int
    end_y_mm: int
    review_status: str
    source: str
    confidence: float | None
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
