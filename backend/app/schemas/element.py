from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field


class ElementKind(StrEnum):
    WINDOW = "window"
    DOOR = "door"
    COLUMN = "column"
    BEAM = "beam"
    GAS_PIPE = "gas_pipe"
    WATER_PIPE = "water_pipe"
    DRAIN = "drain"
    ELECTRICAL = "electrical"
    SWITCH = "switch"
    SOCKET = "socket"
    VENTILATION = "ventilation"
    RECESS = "recess"
    PROTRUSION = "protrusion"
    CUSTOM = "custom"


ELEMENT_KINDS = [k.value for k in ElementKind]


class ElementCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    kind: ElementKind
    offset_mm: int = Field(strict=True, ge=0, le=50000)
    width_mm: int = Field(strict=True, ge=1, le=50000)
    height_mm: int | None = Field(strict=True, default=None, ge=1, le=10000)
    sill_mm: int | None = Field(strict=True, default=None, ge=0, le=10000)
    depth_mm: int | None = Field(strict=True, default=None, ge=0, le=10000)
    source: str = Field(default="manual", pattern="^(manual|sketch_ai|voice_ai|import)$")


class ElementUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    kind: ElementKind | None = None
    offset_mm: int | None = Field(strict=True, default=None, ge=0, le=50000)
    width_mm: int | None = Field(strict=True, default=None, ge=1, le=50000)
    height_mm: int | None = Field(strict=True, default=None, ge=1, le=10000)
    sill_mm: int | None = Field(strict=True, default=None, ge=0, le=10000)
    depth_mm: int | None = Field(strict=True, default=None, ge=0, le=10000)
    review_status: str | None = Field(default=None, pattern="^(needs_review|incomplete)$")
    version: int | None = Field(strict=True, default=None, ge=1)
    base_version: int | None = Field(strict=True, default=None, ge=1)


class ElementOut(BaseModel):
    id: str
    wall_id: str
    label: str
    kind: ElementKind
    offset_mm: int
    width_mm: int
    height_mm: int | None
    sill_mm: int | None
    depth_mm: int | None
    review_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    source: str
    confidence: float | None
    version: int
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
