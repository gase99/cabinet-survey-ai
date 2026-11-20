from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session
from app.models.db_models import AuditEvent


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


_ENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "customer": ("id", "owner_id", "name", "phone", "address", "notes", "version", "is_deleted", "deleted_at"),
    "project": ("id", "owner_id", "customer_id", "title", "status", "site_notes", "version", "is_deleted", "deleted_at"),
    "room": ("id", "project_id", "label", "room_type", "version", "is_deleted", "deleted_at"),
    "wall": (
        "id",
        "room_id",
        "label",
        "length_mm",
        "height_mm",
        "start_x_mm",
        "start_y_mm",
        "end_x_mm",
        "end_y_mm",
        "review_status",
        "approved_by",
        "approved_at",
        "source",
        "confidence",
        "source_observation_id",
        "version",
        "is_deleted",
        "deleted_at",
    ),
    "element": (
        "id",
        "wall_id",
        "label",
        "kind",
        "offset_mm",
        "width_mm",
        "height_mm",
        "sill_mm",
        "depth_mm",
        "review_status",
        "approved_by",
        "approved_at",
        "source",
        "confidence",
        "source_observation_id",
        "version",
        "is_deleted",
        "deleted_at",
    ),
    "export_job": ("id", "project_id", "owner_id", "format", "layout", "status", "file_path"),
    "telegram_delivery": ("id", "owner_id", "project_id", "export_job_id", "chat_id", "status", "version", "is_deleted", "deleted_at"),
    "telegram_link": ("id", "user_id", "telegram_chat_id", "used", "version", "is_deleted", "deleted_at"),
    "observation": (
        "id",
        "owner_id",
        "project_id",
        "source_type",
        "normalized_value_mm",
        "label",
        "confidence",
        "source_asset_id",
        "prompt_id",
        "model_name",
        "review_status",
        "linked_entity_type",
        "linked_entity_id",
    ),
}


def entity_snapshot(entity_type: str, entity: Any) -> dict[str, Any]:
    if entity is None:
        return {}
    if isinstance(entity, dict):
        return _json_safe(entity)
    fields = _ENTITY_FIELDS.get(entity_type, ())
    return {
        field: _json_safe(getattr(entity, field, None))
        for field in fields
        if hasattr(entity, field)
    }


def log_audit(
    db: Session,
    *,
    user_id: str | None,
    project_id: str | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    detail: str | None = None,
    commit: bool = True,
) -> AuditEvent:
    ev = AuditEvent(
        user_id=user_id,
        project_id=project_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=_json_safe(old_values) if old_values is not None else None,
        new_values=_json_safe(new_values) if new_values is not None else None,
        detail=detail,
    )
    db.add(ev)
    if commit:
        db.commit()
    else:
        db.flush()
    return ev


def serialize_audit_event(ev: AuditEvent) -> dict[str, Any]:
    ts = ev.created_at.isoformat() if ev.created_at else None
    return {
        "id": ev.id,
        "actor_id": ev.user_id,
        "user_id": ev.user_id,
        "project_id": ev.project_id,
        "action": ev.action,
        "entity_type": ev.entity_type,
        "entity_id": ev.entity_id,
        "old_values": ev.old_values,
        "new_values": ev.new_values,
        "detail": ev.detail,
        "timestamp": ts,
        "created_at": ts,
    }
