"""Measurement approval integrity and append-only revision history."""
from typing import Any
from sqlalchemy.orm import Session
from app.models.db_models import Element, MeasurementRevision, Project, Room, Wall, now_utc

WALL_PAYLOAD_FIELDS = (
    "room_id",
    "label",
    "length_mm",
    "height_mm",
    "start_x_mm",
    "start_y_mm",
    "end_x_mm",
    "end_y_mm",
    "source",
    "confidence",
)

ELEMENT_PAYLOAD_FIELDS = (
    "wall_id",
    "label",
    "kind",
    "offset_mm",
    "width_mm",
    "height_mm",
    "sill_mm",
    "depth_mm",
    "source",
    "confidence",
)


def _get_val(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def missing_wall_dimensions(wall_or_values: Any) -> list[str]:
    missing: list[str] = []
    for field in ("length_mm", "height_mm"):
        val = _get_val(wall_or_values, field)
        if val is None or (isinstance(val, int) and val <= 0):
            missing.append(field)
    return missing


def missing_element_dimensions(elem_or_values: Any) -> list[str]:
    missing: list[str] = []
    offset_val = _get_val(elem_or_values, "offset_mm")
    if offset_val is None or (isinstance(offset_val, int) and offset_val < 0):
        missing.append("offset_mm")
    width_val = _get_val(elem_or_values, "width_mm")
    if width_val is None or (isinstance(width_val, int) and width_val <= 0):
        missing.append("width_mm")
    height_val = _get_val(elem_or_values, "height_mm")
    if height_val is None or (isinstance(height_val, int) and height_val <= 0):
        missing.append("height_mm")
    sill_val = _get_val(elem_or_values, "sill_mm")
    if sill_val is None or (isinstance(sill_val, int) and sill_val < 0):
        missing.append("sill_mm")
    return missing


def missing_required_dimensions(entity_type: str, entity_or_values: Any) -> list[str]:
    if entity_type == "wall":
        return missing_wall_dimensions(entity_or_values)
    if entity_type == "element":
        return missing_element_dimensions(entity_or_values)
    raise ValueError(f"Unsupported measurement entity_type: {entity_type}")


def derive_initial_review_status(entity_type: str, values: Any) -> str:
    """New items never start approved; missing required dimensions yield 'incomplete'."""
    if missing_required_dimensions(entity_type, values):
        return "incomplete"
    return "needs_review"


def derive_updated_review_status(
    entity_type: str,
    values: Any,
    requested_status: str | None = None,
) -> str:
    """Edits never auto-approve; missing required dimensions always yield 'incomplete'."""
    if missing_required_dimensions(entity_type, values):
        return "incomplete"
    if requested_status == "incomplete":
        return "incomplete"
    return "needs_review"


def measurement_payload(entity_type: str, entity_or_values: Any) -> dict[str, Any]:
    fields = WALL_PAYLOAD_FIELDS if entity_type == "wall" else ELEMENT_PAYLOAD_FIELDS
    payload = {field: _get_val(entity_or_values, field) for field in fields}
    if bool(_get_val(entity_or_values, "is_deleted")):
        payload["is_deleted"] = True
    return payload


def resolve_project_id(db: Session, entity_type: str, entity: Wall | Element) -> str:
    if entity_type == "wall":
        room = db.get(Room, entity.room_id)
        if room is None:
            raise ValueError("Room not found for wall")
        return room.project_id
    if entity_type == "element":
        wall = db.get(Wall, entity.wall_id)
        if wall is None:
            raise ValueError("Wall not found for element")
        room = db.get(Room, wall.room_id)
        if room is None:
            raise ValueError("Room not found for element")
        return room.project_id
    raise ValueError(f"Unsupported measurement entity_type: {entity_type}")


def latest_revision(db: Session, entity_type: str, entity_id: str) -> MeasurementRevision | None:
    return (
        db.query(MeasurementRevision)
        .filter(
            MeasurementRevision.entity_type == entity_type,
            MeasurementRevision.entity_id == entity_id,
        )
        .order_by(MeasurementRevision.revision_number.desc())
        .first()
    )


def list_revisions(db: Session, entity_type: str, entity_id: str) -> list[MeasurementRevision]:
    return (
        db.query(MeasurementRevision)
        .filter(
            MeasurementRevision.entity_type == entity_type,
            MeasurementRevision.entity_id == entity_id,
        )
        .order_by(MeasurementRevision.revision_number.asc())
        .all()
    )


def ensure_baseline_revision(
    db: Session,
    *,
    project_id: str,
    entity_type: str,
    entity: Wall | Element,
    fallback_user_id: str,
) -> MeasurementRevision:
    existing = latest_revision(db, entity_type, entity.id)
    if existing is not None:
        return existing
    baseline = MeasurementRevision(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity.id,
        revision_number=1,
        previous_revision_id=None,
        payload=measurement_payload(entity_type, entity),
        review_status=entity.review_status,
        change_reason="baseline",
        changed_by=entity.approved_by or fallback_user_id,
        approved_by=entity.approved_by,
        approved_at=entity.approved_at,
    )
    db.add(baseline)
    db.flush()
    return baseline


def append_revision(
    db: Session,
    *,
    project_id: str,
    entity_type: str,
    entity: Wall | Element,
    change_reason: str,
    user_id: str,
) -> MeasurementRevision:
    prev = latest_revision(db, entity_type, entity.id)
    rev = MeasurementRevision(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity.id,
        revision_number=(prev.revision_number + 1) if prev is not None else 1,
        previous_revision_id=prev.id if prev is not None else None,
        payload=measurement_payload(entity_type, entity),
        review_status=entity.review_status,
        change_reason=change_reason,
        changed_by=user_id,
        approved_by=entity.approved_by,
        approved_at=entity.approved_at,
    )
    db.add(rev)
    db.flush()
    return rev


def approve_entity(
    db: Session,
    *,
    project_id: str,
    entity_type: str,
    entity: Wall | Element,
    user_id: str,
    change_reason: str = "approve",
) -> MeasurementRevision:
    missing = missing_required_dimensions(entity_type, entity)
    if missing:
        raise ValueError(
            f"Cannot approve incomplete {entity_type}; missing required dimensions: {', '.join(missing)}"
        )
    ensure_baseline_revision(
        db,
        project_id=project_id,
        entity_type=entity_type,
        entity=entity,
        fallback_user_id=user_id,
    )
    approved_time = now_utc()
    entity.review_status = "approved"
    entity.approved_by = user_id
    entity.approved_at = approved_time
    entity.version += 1
    return append_revision(
        db,
        project_id=project_id,
        entity_type=entity_type,
        entity=entity,
        change_reason=change_reason,
        user_id=user_id,
    )
