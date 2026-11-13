"""Canonical domain primitives. All persisted lengths are integer millimetres."""
from enum import StrEnum
from pydantic import BaseModel, Field


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    INCOMPLETE = "incomplete"
    APPROVED = "approved"


class Dimension(BaseModel):
    value_mm: int = Field(ge=0, description="Canonical dimension in millimetres")
    source: str = Field(description="manual, sketch_ai, voice_ai, or import")
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    confidence: float | None = Field(default=None, ge=0, le=1)


class Wall(BaseModel):
    id: str
    label: str
    length: Dimension
    height: Dimension
    start_x_mm: int
    start_y_mm: int
    end_x_mm: int
    end_y_mm: int
