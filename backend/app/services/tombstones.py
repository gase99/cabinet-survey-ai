"""Soft-delete tombstones and cross-device delete propagation."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.db_models import (
    Customer,
    Element,
    Project,
    Room,
    SyncOperation,
    Wall,
    gen_id,
    now_utc,
)
from app.services.revisions import append_revision, ensure_baseline_revision


def record_delete_operation(
    db: Session,
    *,
    owner_id: str,
    entity_type: str,
    entity_id: str,
    base_version: int,
    new_version: int,
    deleted_at: datetime,
    op_id: str | None = None,
) -> SyncOperation:
    op = SyncOperation(
        id=op_id or gen_id(),
        owner_id=owner_id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation="delete",
        payload={
            "is_deleted": True,
            "deleted_at": deleted_at.isoformat(),
            "version": new_version,
        },
        base_version=base_version,
        status="applied",
    )
    db.add(op)
    return op


def soft_delete_element(
    db: Session,
    *,
    elem: Element,
    project_id: str,
    user_id: str,
    reason: str = "delete",
    op_id: str | None = None,
    now: datetime | None = None,
) -> None:
    ts = now or now_utc()
    old_version = elem.version
    ensure_baseline_revision(
        db,
        project_id=project_id,
        entity_type="element",
        entity=elem,
        fallback_user_id=user_id,
    )
    elem.is_deleted = True
    elem.deleted_at = ts
    elem.version += 1
    db.flush()
    append_revision(
        db,
        project_id=project_id,
        entity_type="element",
        entity=elem,
        change_reason=reason,
        user_id=user_id,
    )
    record_delete_operation(
        db,
        owner_id=user_id,
        entity_type="element",
        entity_id=elem.id,
        base_version=old_version,
        new_version=elem.version,
        deleted_at=ts,
        op_id=op_id,
    )


def soft_delete_wall(
    db: Session,
    *,
    wall: Wall,
    project_id: str,
    user_id: str,
    reason: str = "delete",
    op_id: str | None = None,
    now: datetime | None = None,
) -> None:
    ts = now or now_utc()
    children = (
        db.query(Element)
        .filter(Element.wall_id == wall.id, Element.is_deleted.is_(False))
        .all()
    )
    for elem in children:
        soft_delete_element(
            db,
            elem=elem,
            project_id=project_id,
            user_id=user_id,
            reason=f"{reason}_cascade",
            now=ts,
        )
    old_version = wall.version
    ensure_baseline_revision(
        db,
        project_id=project_id,
        entity_type="wall",
        entity=wall,
        fallback_user_id=user_id,
    )
    wall.is_deleted = True
    wall.deleted_at = ts
    wall.version += 1
    db.flush()
    append_revision(
        db,
        project_id=project_id,
        entity_type="wall",
        entity=wall,
        change_reason=reason,
        user_id=user_id,
    )
    record_delete_operation(
        db,
        owner_id=user_id,
        entity_type="wall",
        entity_id=wall.id,
        base_version=old_version,
        new_version=wall.version,
        deleted_at=ts,
        op_id=op_id,
    )


def soft_delete_room(
    db: Session,
    *,
    room: Room,
    project_id: str,
    user_id: str,
    reason: str = "delete",
    op_id: str | None = None,
    now: datetime | None = None,
) -> None:
    ts = now or now_utc()
    walls = (
        db.query(Wall)
        .filter(Wall.room_id == room.id, Wall.is_deleted.is_(False))
        .all()
    )
    for wall in walls:
        soft_delete_wall(
            db,
            wall=wall,
            project_id=project_id,
            user_id=user_id,
            reason=f"{reason}_cascade",
            now=ts,
        )
    old_version = room.version
    room.is_deleted = True
    room.deleted_at = ts
    room.version += 1
    record_delete_operation(
        db,
        owner_id=user_id,
        entity_type="room",
        entity_id=room.id,
        base_version=old_version,
        new_version=room.version,
        deleted_at=ts,
        op_id=op_id,
    )


def soft_delete_customer(
    db: Session,
    *,
    customer: Customer,
    user_id: str,
    op_id: str | None = None,
    now: datetime | None = None,
) -> None:
    ts = now or now_utc()
    old_version = customer.version
    customer.is_deleted = True
    customer.deleted_at = ts
    customer.version += 1
    record_delete_operation(
        db,
        owner_id=user_id,
        entity_type="customer",
        entity_id=customer.id,
        base_version=old_version,
        new_version=customer.version,
        deleted_at=ts,
        op_id=op_id,
    )


def soft_delete_project(
    db: Session,
    *,
    project: Project,
    user_id: str,
    op_id: str | None = None,
    now: datetime | None = None,
) -> None:
    ts = now or now_utc()
    old_version = project.version
    project.is_deleted = True
    project.deleted_at = ts
    project.status = "archived"
    project.version += 1
    record_delete_operation(
        db,
        owner_id=user_id,
        entity_type="project",
        entity_id=project.id,
        base_version=old_version,
        new_version=project.version,
        deleted_at=ts,
        op_id=op_id,
    )


def _tombstone_dict(entity_type: str, row) -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": row.id,
        "version": row.version,
        "is_deleted": True,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


def collect_tombstones(
    db: Session,
    *,
    user_id: str,
    since: datetime | None = None,
    entity_type: str | None = None,
) -> list[dict]:
    items: list[dict] = []

    if entity_type in (None, "customer"):
        q = db.query(Customer).filter(
            Customer.owner_id == user_id,
            Customer.is_deleted.is_(True),
        )
        if since is not None:
            q = q.filter(Customer.deleted_at > since)
        items.extend(_tombstone_dict("customer", row) for row in q.all())

    if entity_type in (None, "project"):
        q = db.query(Project).filter(
            Project.owner_id == user_id,
            Project.is_deleted.is_(True),
        )
        if since is not None:
            q = q.filter(Project.deleted_at > since)
        items.extend(_tombstone_dict("project", row) for row in q.all())

    if entity_type in (None, "room"):
        q = (
            db.query(Room)
            .join(Project, Room.project_id == Project.id)
            .filter(Project.owner_id == user_id, Room.is_deleted.is_(True))
        )
        if since is not None:
            q = q.filter(Room.deleted_at > since)
        items.extend(_tombstone_dict("room", row) for row in q.all())

    if entity_type in (None, "wall"):
        q = (
            db.query(Wall)
            .join(Room, Wall.room_id == Room.id)
            .join(Project, Room.project_id == Project.id)
            .filter(Project.owner_id == user_id, Wall.is_deleted.is_(True))
        )
        if since is not None:
            q = q.filter(Wall.deleted_at > since)
        items.extend(_tombstone_dict("wall", row) for row in q.all())

    if entity_type in (None, "element"):
        q = (
            db.query(Element)
            .join(Wall, Element.wall_id == Wall.id)
            .join(Room, Wall.room_id == Room.id)
            .join(Project, Room.project_id == Project.id)
            .filter(Project.owner_id == user_id, Element.is_deleted.is_(True))
        )
        if since is not None:
            q = q.filter(Element.deleted_at > since)
        items.extend(_tombstone_dict("element", row) for row in q.all())

    return items
