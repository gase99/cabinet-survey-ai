"""Deterministic geometry boundary; no AI calls are permitted in this module."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PointMM:
    x: int
    y: int


@dataclass(frozen=True)
class SegmentMM:
    start: PointMM
    end: PointMM

    @property
    def length_squared(self) -> int:
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return dx * dx + dy * dy


def validate_positive_length(length_mm: int) -> None:
    if length_mm <= 0:
        raise ValueError("Wall length must be greater than zero millimetres")
