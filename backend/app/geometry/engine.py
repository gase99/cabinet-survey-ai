"""Deterministic geometry engine — no AI/network calls permitted."""
from html import escape
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

def walls_to_polygon(walls: List[WallInput], tolerance_mm: int = 1) -> Tuple[List[PointMM], List[GeometryValidationError]]:
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
            if w.end != nxt.start:  # type: ignore
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
    errors = []
    wall_by_id = {w.id:w for w in walls}
    for e in elements:
        wall = wall_by_id.get(e.wall_id)
        if wall is None:
            errors.append(GeometryValidationError('unknown_wall','Element references unknown wall',[e.id,e.wall_id]))
            continue
        dimensions=[e.offset_mm,e.width_mm,*[v for v in (e.height_mm,e.sill_mm,e.depth_mm) if v is not None]]
        if any(type(v) is not int for v in dimensions):
            errors.append(GeometryValidationError('non_integer_dimension','Dimensions must be integer mm',[e.id]))
            continue
        if e.offset_mm < 0 or e.width_mm <= 0 or e.offset_mm+e.width_mm > wall.length_mm:
            errors.append(GeometryValidationError('out_of_bounds','Element exceeds wall length',[e.id,wall.id]))
        if (e.height_mm is not None and (e.height_mm <= 0 or e.height_mm > wall.height_mm)) or (e.sill_mm is not None and (e.sill_mm < 0 or e.sill_mm > wall.height_mm)) or (e.sill_mm is not None and e.height_mm is not None and e.sill_mm+e.height_mm > wall.height_mm) or (e.depth_mm is not None and e.depth_mm < 0):
            errors.append(GeometryValidationError('height_exceeds_wall','Invalid vertical/depth bounds',[e.id,wall.id]))
    for i,a in enumerate(elements):
        for b in elements[i+1:]:
            if a.wall_id != b.wall_id or a.wall_id not in wall_by_id:
                continue
            h=wall_by_id[a.wall_id].height_mm
            # Unknown vertical spans cannot prove separation; conservatively block overlap.
            ay,at=(a.sill_mm,a.sill_mm+a.height_mm) if a.sill_mm is not None and a.height_mm is not None else (0,h)
            by,bt=(b.sill_mm,b.sill_mm+b.height_mm) if b.sill_mm is not None and b.height_mm is not None else (0,h)
            if a.offset_mm < b.offset_mm+b.width_mm and b.offset_mm < a.offset_mm+a.width_mm and ay < bt and by < at:
                errors.append(GeometryValidationError('overlap','Elements overlap or separation is unmeasured',[a.id,b.id,a.wall_id]))
    return errors


def validate_topology(points):
    errors=[]
    def orient(a,b,c): return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)
    def intersects(a,b,c,d):
        bounds=max(min(a.x,b.x),min(c.x,d.x))<=min(max(a.x,b.x),max(c.x,d.x)) and max(min(a.y,b.y),min(c.y,d.y))<=min(max(a.y,b.y),max(c.y,d.y))
        return bounds and orient(a,b,c)*orient(a,b,d)<=0 and orient(c,d,a)*orient(c,d,b)<=0
    for i in range(len(points)):
        for j in range(i+1,len(points)):
            if j==i+1 or (i==0 and j==len(points)-1):continue
            if intersects(points[i],points[(i+1)%len(points)],points[j],points[(j+1)%len(points)]):
                errors.append(GeometryValidationError('self_intersection','Room edges intersect'))
    if points and compute_polygon_area(points)==0:
        errors.append(GeometryValidationError('zero_area','Room has zero area'))
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
        wall_labels += f'<text x="{mx}" y="{my}" font-size="120" text-anchor="middle" fill="#1a1a1a">{escape(w.label)} ({w.length_mm}mm)</text>\n'
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
            elem_markers += f'<line x1="{cx - ux*e.width_mm/2}" y1="{cy - uy*e.width_mm/2}" x2="{cx + ux*e.width_mm/2}" y2="{cy + uy*e.width_mm/2}" stroke="#d32f2f" stroke-width="40"/>\n'
            elem_markers += f'<text x="{cx}" y="{cy - 100}" font-size="80" text-anchor="middle" fill="#d32f2f">{escape(e.label)}</text>\n'
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
            elem_markers += f'<line x1="{cx - ux*e.width_mm/2}" y1="{cy - uy*e.width_mm/2}" x2="{cx + ux*e.width_mm/2}" y2="{cy + uy*e.width_mm/2}" stroke="#d32f2f" stroke-width="40"/>\n'
            elem_markers += f'<text x="{cx}" y="{cy - 100}" font-size="80" text-anchor="middle" fill="#d32f2f">{escape(e.label)}</text>\n'

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
    vb_w = w + 2*padding; vb_h = h + 2*padding + 100*sum(1 for e in elements if e.wall_id == wall.id and (e.height_mm is None or e.sill_mm is None)) + 200
    elem_svg = ""
    for e in elements:
        if e.wall_id != wall.id:
            continue
        x = e.offset_mm
        y = e.sill_mm if e.sill_mm is not None else 0
        ew = e.width_mm
        eh = e.height_mm
        if eh is None or e.sill_mm is None:
            # Unknown dimensions/vertical references are explicitly unpositioned;
            # do not draw an invented 800mm box or assume a floor reference.
            elem_svg += f'<text x="{x}" y="{h + 240 + 100 * len([v for v in elements[:elements.index(e)] if v.wall_id == wall.id and (v.height_mm is None or v.sill_mm is None)])}" font-size="70" fill="#b45309">{escape(e.label)}: offset {x} mm; width {ew} mm; height {eh if eh is not None else "?"} mm; sill {e.sill_mm if e.sill_mm is not None else "?"} mm (unpositioned)</text>\n'
            continue
        sy = h - y - eh
        elem_svg += f'<rect x="{x}" y="{sy}" width="{ew}" height="{eh}" fill="#fee2e2" stroke="#d32f2f" stroke-width="15"/>\n'
        elem_svg += f'<text x="{x+ew/2}" y="{sy - 20}" font-size="90" text-anchor="middle" fill="#333">{escape(e.label)} {ew}×{eh}</text>\n'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="{vb_x} {vb_y} {vb_w} {vb_h}" style="background:#fff">
  <rect x="{vb_x}" y="{vb_y}" width="{vb_w}" height="{vb_h}" fill="#fafafa"/>
  <rect x="0" y="0" width="{w}" height="{h}" fill="#fff" stroke="#1a1a1a" stroke-width="25"/>
  <text x="{w/2}" y="-60" font-size="110" text-anchor="middle" fill="#1a1a1a">{escape(wall.label)} — {w} mm × {h} mm</text>
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

    if len(walls) < 3:
        errors.append(GeometryValidationError('insufficient_walls','A room requires at least three walls'))
    if len({w.id for w in walls}) != len(walls) or len({e.id for e in elements}) != len(elements):
        errors.append(GeometryValidationError('duplicate_id','Stable entity IDs must be unique'))
    for w in walls:
        values=[w.length_mm,w.height_mm]
        if w.start: values.extend([w.start.x,w.start.y])
        if w.end: values.extend([w.end.x,w.end.y])
        if any(type(v) is not int for v in values):
            raise ValueError('Geometry accepts integer millimetres only')
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
    errors.extend(validate_topology(points))

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
