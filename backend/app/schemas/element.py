from pydantic import BaseModel, Field
from datetime import datetime

ELEMENT_KINDS = ["window","door","column","beam","gas_pipe","water_pipe","drain","electrical","switch","socket","ventilation","recess","protrusion","custom"]

class ElementCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(window|door|column|beam|gas_pipe|water_pipe|drain|electrical|switch|socket|ventilation|recess|protrusion|custom)$")
    offset_mm: int = Field(strict=True, ge=0)
    width_mm: int = Field(strict=True, ge=1, le=50000)
    height_mm: int | None = Field(strict=True, default=None, ge=1)
    sill_mm: int | None = Field(strict=True, default=None, ge=0)
    depth_mm: int | None = Field(strict=True, default=None, ge=0)
    source: str = Field(default="manual", pattern="^(manual|sketch_ai|voice_ai|import)$")

class ElementUpdate(BaseModel):
    label: str | None = None
    kind: str | None = Field(default=None)
    offset_mm: int | None = Field(strict=True, default=None, ge=0)
    width_mm: int | None = Field(strict=True, default=None, ge=1)
    height_mm: int | None = None
    sill_mm: int | None = None
    depth_mm: int | None = None
    review_status: str | None = Field(default=None, pattern="^(needs_review|incomplete|approved)$")

class ElementOut(BaseModel):
    id: str
    wall_id: str
    label: str
    kind: str
    offset_mm: int
    width_mm: int
    height_mm: int | None
    sill_mm: int | None
    depth_mm: int | None
    review_status: str
    source: str
    confidence: float | None
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
