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

# Unit conversion helpers - canonical is mm
UNIT_TO_MM = {
    "mm": 1,
    "cm": 10,
    "m": 1000,
    "millimeter": 1,
    "millimetre": 1,
    "centimeter": 10,
    "centimetre": 10,
    "meter": 1000,
    "metre": 1000,
    "in": 25.4,
    "inch": 25.4,
    "ft": 304.8,
    "foot": 304.8,
}

def to_mm(value: float, unit: str) -> int:
    u = unit.lower().strip()
    factor = UNIT_TO_MM.get(u)
    if factor is None:
        raise ValueError(f"Unknown unit: {unit}")
    return int(round(value * factor))

def from_mm(value_mm: int, unit: str) -> float:
    u = unit.lower().strip()
    factor = UNIT_TO_MM.get(u)
    if factor is None:
        raise ValueError(f"Unknown unit: {unit}")
    return value_mm / factor

# Persian / Arabic numeral normalization
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
ARABIC_DECIMAL = {"٫": ".", "،": ".", "٫": "."}

def normalize_numerals(s: str) -> str:
    t = s.translate(PERSIAN_DIGITS)
    for k, v in ARABIC_DECIMAL.items():
        t = t.replace(k, v)
    return t
