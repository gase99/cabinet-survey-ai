"""Deterministic geometry engine — no AI/network calls permitted."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import math

@dataclass(frozen=True)
class PointMM:
    x: int
    y: int

    def distance_to(self, other: "PointMM") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

@dataclass(frozen=True)
class SegmentMM:
    start: PointMM
    end: PointMM

    @property
    def length_squared(self) -> int:
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return dx*dx + dy*dy

    @property
    def length_mm(self) -> float:
        return math.sqrt(self.length_squared)

    def is_zero_length(self, tol: int = 0) -> bool:
        return self.length_squared <= tol*tol

def validate_positive_length(length_mm: int) -> None:
    if length_mm <= 0:
        raise ValueError("Wall length must be greater than zero millimetres")

class ValidationErrorItem(BaseModelLike := object):
    pass

@dataclass
class GeometryValidationError:
    code: str
    message: str
    entity_ids: List[str] = field(default_factory=list)
    severity: str = "error"  # error | warning

@dataclass
class WallInput:
    id: str
    label: str
    length_mm: int
    height_mm: int
    # Optional explicit coordinates; if not provided, engine computes from topology
    start: Optional[PointMM] = None
    end: Optional[PointMM] = None
    # For auto-layout: wall connections define ordering
    # Walls are given in order around room perimeter, with direction
    # Alternatively, explicit start/end coordinates are validated

@dataclass
class ElementInput:
    id: str
    wall_id: str
    label: str
    kind: str  # window, door, column, pipe, outlet, custom etc.
    offset_mm: int  # along wall from reference corner (left)
    width_mm: int
    height_mm: int | None = None
    sill_mm: int | None = None  # elevation from floor
    depth_mm: int | None = None

@dataclass
class RoomGeometryResult:
    walls: List[WallInput]
    points: List[PointMM]  # ordered perimeter points
    segments: List[SegmentMM]
    area_mm2: int
    perimeter_mm: int
    errors: List[GeometryValidationError]
    warnings: List[GeometryValidationError]
    # SVG-ready
    svg_plan: str
    elevations: Dict[str, str]  # wall_id -> SVG string
    dimension_annotations: List[dict]
    metadata: dict

# Core functions

def compute_polygon_area(points: List[PointMM]) -> int:
    """Shoelace formula, integer mm2"""
    n = len(points)
    if n < 3:
        return 0
    s = 0
    for i in range(n):
        j = (i+1) % n
        s += points[i].x * points[j].y - points[j].x * points[i].y
    return abs(s)//2

def walls_to_polygon(walls: List[WallInput], tolerance_mm: int = 5) -> Tuple[List[PointMM], List[GeometryValidationError]]:
    """
    Compute room polygon from walls.
    Supports two modes:
    - Walls have explicit start/end coordinates -> validate closure
    - Missing endpoints are an error, not permission to infer room topology.
    """
    errors: List[GeometryValidationError] = []
    # Check if any wall has coordinates
    has_coords = any(w.start is not None and w.end is not None for w in walls)
    if has_coords:
        # Validate all have coords
        missing = [w.id for w in walls if w.start is None or w.end is None]
        if missing:
            errors.append(GeometryValidationError(
                code="missing_coordinates",
                message=f"Walls {missing} missing coordinates while others have them. Provide all or none.",
                entity_ids=missing
            ))
            return [], errors
        points: List[PointMM] = []
        segments: List[SegmentMM] = []
        for w in walls:
            seg = SegmentMM(start=w.start, end=w.end)  # type: ignore
            if seg.is_zero_length():
                errors.append(GeometryValidationError(code="zero_length", message=f"Wall {w.id} has zero length", entity_ids=[w.id]))
            # Validate length matches explicit coordinates within tolerance
            actual = seg.length_mm
            if abs(actual - w.length_mm) > tolerance_mm:
                errors.append(GeometryValidationError(
                    code="length_mismatch",
                    message=f"Wall {w.id} length {w.length_mm} mm does not match coordinates distance {actual:.1f} mm",
                    entity_ids=[w.id]
                ))
            segments.append(seg)
        # Validate closure: each wall end should match next wall start (within tolerance), and last to first
        for i, w in enumerate(walls):
            nxt = walls[(i+1) % len(walls)]
            if w.end.distance_to(nxt.start) > tolerance_mm:  # type: ignore
                errors.append(GeometryValidationError(
                    code="disconnected_walls",
                    message=f"Wall {w.id} end does not connect to wall {nxt.id} start (gap {w.end.distance_to(nxt.start):.1f} mm)",
                    entity_ids=[w.id, nxt.id]
                ))
        # Build points in order
        points = [w.start for w in walls]  # type: ignore
        return points, errors
    else:
        # Lengths alone do not determine corner angles or topology. Never choose a
        # plausible rectangle/L/U on behalf of the surveyor.
        return [], [GeometryValidationError(code="missing_coordinates",
            message="Explicit wall endpoints are required; lengths alone do not define room topology",
            entity_ids=[w.id for w in walls])]

def validate_elements(elements: List[ElementInput], walls: List[WallInput]) -> List[GeometryValidationError]:
    errors: List[GeometryValidationError] = []
    wall_by_id = {w.id: w for w in walls}
    # Group by wall to detect overlaps
    by_wall: Dict[str, List[ElementInput]] = {}
    for e in elements:
        by_wall.setdefault(e.wall_id, []).append(e)
        if e.wall_id not in wall_by_id:
            errors.append(GeometryValidationError(code="unknown_wall", message=f"Element {e.id} references unknown wall {e.wall_id}", entity_ids=[e.id, e.wall_id]))
            continue
        wall = wall_by_id[e.wall_id]
        # Bounds: offset >=0 and offset+width <= wall length
        if e.offset_mm < 0:
            errors.append(GeometryValidationError(code="negative_offset", message=f"Element {e.id} offset negative", entity_ids=[e.id]))
        if e.width_mm <= 0:
            errors.append(GeometryValidationError(code="invalid_width", message=f"Element {e.id} width must be >0", entity_ids=[e.id]))
        if e.offset_mm + e.width_mm > wall.length_mm:
            errors.append(GeometryValidationError(code="out_of_bounds", message=f"Element {e.id} exceeds wall {wall.id} length {wall.length_mm} mm (offset {e.offset_mm}+width {e.width_mm})", entity_ids=[e.id, wall.id]))
        # Height vs wall height
        if e.height_mm is not None and e.height_mm > wall.height_mm:
            errors.append(GeometryValidationError(code="height_exceeds_wall", message=f"Element {e.id} height {e.height_mm} exceeds wall height {wall.height_mm}", entity_ids=[e.id]))

    # Overlap detection per wall
    for wall_id, elems in by_wall.items():
        # Sort by offset
        elems_sorted = sorted(elems, key=lambda x: x.offset_mm)
        for i in range(len(elems_sorted)-1):
            a = elems_sorted[i]
            b = elems_sorted[i+1]
            a_end = a.offset_mm + a.width_mm
            if a_end > b.offset_mm:
                # Overlap
                # Allow if kinds are compatible? For now all overlaps are errors
                errors.append(GeometryValidationError(
                    code="overlap",
                    message=f"Elements {a.id} and {b.id} overlap on wall {wall_id} ({a_end - b.offset_mm} mm)",
                    entity_ids=[a.id, b.id, wall_id]
                ))
    return errors

def generate_plan_svg(points: List[PointMM], walls: List[WallInput], elements: List[ElementInput], padding_mm: int = 500) -> str:
    """Simple SVG plan: polygon + dimensions + legends"""
    if not points:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><text x="20" y="20">No geometry</text></svg>'
    min_x = min(p.x for p in points); max_x = max(p.x for p in points)
    min_y = min(p.y for p in points); max_y = max(p.y for p in points)
    width = max_x - min_x; height = max_y - min_y
    # ViewBox with padding
    vb_x = min_x - padding_mm; vb_y = min_y - padding_mm
    vb_w = width + 2*padding_mm; vb_h = height + 2*padding_mm
    # Scale for display: use VB directly, width/height attributes scaled down for screen (1mm = 0.1px at 100 dpi approx)
    # For simplicity, set SVG width/height proportional
    svg_w = 800; svg_h = 600
    # Build polygon points string
    pts_str = " ".join(f"{p.x},{p.y}" for p in points)  # y will be flipped via transform? We'll keep as is with negative y handling
    # Build wall labels at midpoints
    wall_labels = ""
    for w in walls:
        if w.start and w.end:
            mx = (w.start.x + w.end.x)//2
            my = (w.start.y + w.end.y)//2
        else:
            # For auto-layout, compute from points index
            idx = walls.index(w)
            p1 = points[idx % len(points)]
            p2 = points[(idx+1) % len(points)]
            mx = (p1.x + p2.x)//2
            my = (p1.y + p2.y)//2
        wall_labels += f'<text x="{mx}" y="{my}" font-size="120" text-anchor="middle" fill="#1a1a1a">{w.label} ({w.length_mm}mm)</text>\n'
    # Elements markers (project onto walls: along wall line)
    elem_markers = ""
    for e in elements:
        # Find wall segment
        wall = next((w for w in walls if w.id == e.wall_id), None)
        if not wall:
            continue
        # Compute approx position: start + offset along wall direction
        if wall.start and wall.end:
            # vector
            dx = wall.end.x - wall.start.x; dy = wall.end.y - wall.start.y
            length = math.hypot(dx, dy) or 1
            ux = dx / length; uy = dy / length
            # element center along wall
            cx = wall.start.x + ux * (e.offset_mm + e.width_mm/2)
            cy = wall.start.y + uy * (e.offset_mm + e.width_mm/2)
            # perpendicular outward offset for marker
            elem_markers += f'<rect x="{cx - e.width_mm/2}" y="{cy - 80}" width="{e.width_mm}" height="160" fill="none" stroke="#d32f2f" stroke-width="20"/>\n'
            elem_markers += f'<text x="{cx}" y="{cy - 100}" font-size="80" text-anchor="middle" fill="#d32f2f">{e.label}</text>\n'
        else:
            # auto-layout case: use points
            idx = next((i for i,w in enumerate(walls) if w.id == e.wall_id), None)
            if idx is None:
                continue
            p1 = points[idx % len(points)]; p2 = points[(idx+1) % len(points)]
            dx = p2.x - p1.x; dy = p2.y - p1.y
            length = math.hypot(dx, dy) or 1
            ux = dx/length; uy = dy/length
            cx = p1.x + ux * (e.offset_mm + e.width_mm/2)
            cy = p1.y + uy * (e.offset_mm + e.width_mm/2)
            elem_markers += f'<rect x="{cx - e.width_mm/2}" y="{cy - 80}" width="{e.width_mm}" height="160" fill="none" stroke="#d32f2f" stroke-width="20"/>\n'
            elem_markers += f'<text x="{cx}" y="{cy - 100}" font-size="80" text-anchor="middle" fill="#d32f2f">{e.label}</text>\n'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="{vb_x} {vb_y} {vb_w} {vb_h}" style="background:#fff">
  <rect x="{vb_x}" y="{vb_y}" width="{vb_w}" height="{vb_h}" fill="#fafafa"/>
  <polygon points="{pts_str}" fill="#e8f0fe" stroke="#1a1a1a" stroke-width="30" stroke-linejoin="round"/>
  {wall_labels}
  {elem_markers}
  <text x="{vb_x+50}" y="{vb_y+120}" font-size="100" fill="#555">Plan — scale not for construction; verify on site</text>
</svg>'''
    return svg

def generate_elevation_svg(wall: WallInput, elements: List[ElementInput]) -> str:
    """Elevation: wall width = length, height = height, origin (0,0) at bottom-left"""
    w = wall.length_mm; h = wall.height_mm
    padding = 200
    vb_x = -padding; vb_y = -padding
    vb_w = w + 2*padding; vb_h = h + 2*padding
    elem_svg = ""
    for e in elements:
        if e.wall_id != wall.id:
            continue
        x = e.offset_mm
        y = e.sill_mm if e.sill_mm is not None else 0
        ew = e.width_mm
        eh = e.height_mm if e.height_mm is not None else 800  # default for outlets
        # In SVG, y=0 at top, so invert: wall bottom at h, top at 0
        # Let's place origin at bottom-left, y up, so SVG viewBox y is 0 at bottom? We'll keep simple: rect from (x, h - y - eh)
        sy = h - y - eh
        elem_svg += f'<rect x="{x}" y="{sy}" width="{ew}" height="{eh}" fill="rgba(211,47,47,0.15)" stroke="#d32f2f" stroke-width="15"/>\n'
        elem_svg += f'<text x="{x+ew/2}" y="{sy - 20}" font-size="90" text-anchor="middle" fill="#333">{e.label} {ew}×{eh or ""}</text>\n'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="{vb_x} {vb_y} {vb_w} {vb_h}" style="background:#fff">
  <rect x="{vb_x}" y="{vb_y}" width="{vb_w}" height="{vb_h}" fill="#fafafa"/>
  <rect x="0" y="0" width="{w}" height="{h}" fill="#fff" stroke="#1a1a1a" stroke-width="25"/>
  <text x="{w/2}" y="-60" font-size="110" text-anchor="middle" fill="#1a1a1a">{wall.label} — {w} mm × {h} mm</text>
  {elem_svg}
  <text x="0" y="{h+60}" font-size="70" fill="#777">Reference: left corner • FFL datum</text>
  <!-- dimension line bottom -->
  <line x1="0" y1="{h+100}" x2="{w}" y2="{h+100}" stroke="#1a1a1a" stroke-width="8"/>
  <text x="{w/2}" y="{h+160}" font-size="80" text-anchor="middle">{w} mm</text>
</svg>'''
    return svg

def build_geometry(walls: List[WallInput], elements: List[ElementInput] | None = None) -> RoomGeometryResult:
    elements = elements or []
    errors: List[GeometryValidationError] = []
    warnings: List[GeometryValidationError] = []

    # Validate walls positive
    for w in walls:
        if w.length_mm <= 0:
            errors.append(GeometryValidationError(code="invalid_length", message=f"Wall {w.id} length must be >0", entity_ids=[w.id]))
        if w.height_mm <= 0:
            errors.append(GeometryValidationError(code="invalid_height", message=f"Wall {w.id} height must be >0", entity_ids=[w.id]))
        # Duplicate zero check
        if w.id.strip() == "":
            errors.append(GeometryValidationError(code="missing_id", message="Wall missing id"))

    # Compute polygon
    points, poly_errors = walls_to_polygon(walls)
    errors.extend(poly_errors)

    # Validate elements
    elem_errors = validate_elements(elements, walls)
    errors.extend(elem_errors)

    # Compute area/perimeter if no fatal errors and points exist
    area = compute_polygon_area(points) if points else 0
    perimeter = sum(w.length_mm for w in walls) if walls else 0

    # Generate drawings even with errors (for preview), but flag
    svg_plan = generate_plan_svg(points, walls, elements) if points else '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><text x="20" y="20">Insufficient geometry to generate plan</text></svg>'
    elevations = {}
    for w in walls:
        elevations[w.id] = generate_elevation_svg(w, elements)

    # Dimension annotations
    dims = []
    for w in walls:
        dims.append({"wall_id": w.id, "label": w.label, "length_mm": w.length_mm, "height_mm": w.height_mm})

    return RoomGeometryResult(
        walls=walls,
        points=points,
        segments=[SegmentMM(start=points[i], end=points[(i+1)%len(points)]) for i in range(len(points))] if len(points)>=2 else [],
        area_mm2=area,
        perimeter_mm=perimeter,
        errors=[e for e in errors if e.severity=="error"],
        warnings=warnings,
        svg_plan=svg_plan,
        elevations=elevations,
        dimension_annotations=dims,
        metadata={"engine_version": "1.0.0", "deterministic": True}
    )
