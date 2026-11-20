"""Soft-delete tombstones and cross-device delete propagation."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.db_models import (
    Customer,
    Element,
    PairingCode,
    Project,
    Room,
    SyncOperation,
    TelegramDelivery,
    User,
    Wall,
    gen_id,
    now_utc,
)
from app.services.audit import entity_snapshot, log_audit
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
    old_snap = entity_snapshot("element", elem)
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
    log_audit(
        db,
        user_id=user_id,
        project_id=project_id,
        action="element.soft_delete",
        entity_type="element",
        entity_id=elem.id,
        old_values=old_snap,
        new_values=entity_snapshot("element", elem),
        detail=reason,
        commit=False,
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
    old_snap = entity_snapshot("wall", wall)
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
    log_audit(
        db,
        user_id=user_id,
        project_id=project_id,
        action="wall.soft_delete",
        entity_type="wall",
        entity_id=wall.id,
        old_values=old_snap,
        new_values=entity_snapshot("wall", wall),
        detail=reason,
        commit=False,
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
    old_snap = entity_snapshot("room", room)
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
    log_audit(
        db,
        user_id=user_id,
        project_id=project_id,
        action="room.soft_delete",
        entity_type="room",
        entity_id=room.id,
        old_values=old_snap,
        new_values=entity_snapshot("room", room),
        detail=reason,
        commit=False,
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
    old_snap = entity_snapshot("customer", customer)
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
    log_audit(
        db,
        user_id=user_id,
        project_id=None,
        action="customer.soft_delete",
        entity_type="customer",
        entity_id=customer.id,
        old_values=old_snap,
        new_values=entity_snapshot("customer", customer),
        detail="delete",
        commit=False,
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
    old_snap = entity_snapshot("project", project)
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
    log_audit(
        db,
        user_id=user_id,
        project_id=project.id,
        action="project.soft_delete",
        entity_type="project",
        entity_id=project.id,
        old_values=old_snap,
        new_values=entity_snapshot("project", project),
        detail="delete",
        commit=False,
    )


def soft_delete_telegram_unlink(
    db: Session,
    *,
    user: User,
    now: datetime | None = None,
) -> dict:
    ts = now or now_utc()
    old_chat_id = user.telegram_chat_id
    old_username = user.telegram_username

    pending_deliveries = (
        db.query(TelegramDelivery)
        .filter(
            TelegramDelivery.owner_id == user.id,
            TelegramDelivery.status == "pending",
        )
        .all()
    )
    for delivery in pending_deliveries:
        old_deliv = entity_snapshot("telegram_delivery", delivery)
        old_ver = delivery.version
        delivery.status = "cancelled"
        delivery.is_deleted = True
        delivery.deleted_at = ts
        delivery.version += 1
        record_delete_operation(
            db,
            owner_id=user.id,
            entity_type="telegram_delivery",
            entity_id=delivery.id,
            base_version=old_ver,
            new_version=delivery.version,
            deleted_at=ts,
        )
        log_audit(
            db,
            user_id=user.id,
            project_id=delivery.project_id,
            action="telegram_delivery.soft_delete",
            entity_type="telegram_delivery",
            entity_id=delivery.id,
            old_values=old_deliv,
            new_values=entity_snapshot("telegram_delivery", delivery),
            detail="telegram_unlink",
            commit=False,
        )

    pairing_rows = (
        db.query(PairingCode)
        .filter(PairingCode.user_id == user.id, PairingCode.is_deleted.is_(False))
        .order_by(PairingCode.created_at.desc())
        .all()
    )
    primary_link: PairingCode | None = None
    old_link_snap: dict | None = None
    for pc in pairing_rows:
        if primary_link is None:
            primary_link = pc
            old_link_snap = entity_snapshot("telegram_link", pc)
        old_ver = pc.version
        if old_chat_id and not pc.telegram_chat_id:
            pc.telegram_chat_id = old_chat_id
        pc.used = True
        pc.is_deleted = True
        pc.deleted_at = ts
        pc.version += 1
        record_delete_operation(
            db,
            owner_id=user.id,
            entity_type="telegram_link",
            entity_id=pc.id,
            base_version=old_ver,
            new_version=pc.version,
            deleted_at=ts,
        )

    if primary_link is None:
        # Ensure an explicit soft-deleted link tombstone row exists even if chat_id was set directly.
        primary_link = PairingCode(
            user_id=user.id,
            code=f"UNLINK-{gen_id()[:12]}",
            telegram_chat_id=old_chat_id,
            expires_at=ts,
            used=True,
            version=1,
            is_deleted=True,
            deleted_at=ts,
        )
        db.add(primary_link)
        db.flush()
        old_link_snap = {
            "user_id": user.id,
            "telegram_chat_id": old_chat_id,
            "telegram_username": old_username,
            "is_deleted": False,
        }
        record_delete_operation(
            db,
            owner_id=user.id,
            entity_type="telegram_link",
            entity_id=primary_link.id,
            base_version=0,
            new_version=primary_link.version,
            deleted_at=ts,
        )

    user.telegram_chat_id = None
    user.telegram_username = None
    user.version += 1
    db.flush()

    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="telegram.unlinked",
        entity_type="telegram_link",
        entity_id=primary_link.id,
        old_values=old_link_snap,
        new_values=entity_snapshot("telegram_link", primary_link),
        detail="soft_delete",
        commit=False,
    )
    return {
        "status": "unlinked",
        "id": primary_link.id,
        "is_deleted": True,
        "version": primary_link.version,
    }


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

    if entity_type in (None, "telegram_link"):
        q = db.query(PairingCode).filter(
            PairingCode.user_id == user_id,
            PairingCode.is_deleted.is_(True),
        )
        if since is not None:
            q = q.filter(PairingCode.deleted_at > since)
        items.extend(_tombstone_dict("telegram_link", row) for row in q.all())

    if entity_type in (None, "telegram_delivery"):
        q = db.query(TelegramDelivery).filter(
            TelegramDelivery.owner_id == user_id,
            TelegramDelivery.is_deleted.is_(True),
        )
        if since is not None:
            q = q.filter(TelegramDelivery.deleted_at > since)
        items.extend(_tombstone_dict("telegram_delivery", row) for row in q.all())

    return items
