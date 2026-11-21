"""Versioned local outbox writes. Never trust parent IDs or arbitrary ORM fields."""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import (
    Customer,
    Element,
    Project,
    Room,
    SyncOperation,
    User,
    Wall,
)
from app.schemas.customer import CustomerCreate
from app.schemas.element import ElementCreate
from app.schemas.project import ProjectCreate
from app.schemas.room import RoomCreate
from app.schemas.sync import ConflictResolveRequest, SyncPushRequest
from app.schemas.wall import WallCreate
from app.services.audit import entity_snapshot, log_audit
from app.services.provenance import (
    bind_observation_to_measurement,
    sync_linked_observation_approval,
    unlink_replaced_observation,
)
from app.services.revisions import (
    append_revision,
    approve_entity,
    derive_initial_review_status,
    derive_updated_review_status,
    ensure_baseline_revision,
    resolve_project_id,
)
from app.services.tombstones import (
    collect_tombstones,
    soft_delete_customer,
    soft_delete_element,
    soft_delete_project,
    soft_delete_room,
    soft_delete_wall,
)

router = APIRouter(prefix="/sync", tags=["sync"])
SyncEntity = Customer | Project | Room | Wall | Element
MODELS: dict[str, type[SyncEntity]] = {
    "customer": Customer,
    "project": Project,
    "room": Room,
    "wall": Wall,
    "element": Element,
}
SCHEMAS: dict[str, type[BaseModel]] = {
    "customer": CustomerCreate,
    "project": ProjectCreate,
    "room": RoomCreate,
    "wall": WallCreate,
    "element": ElementCreate,
}
PARENTS: dict[str, tuple[str, type[SyncEntity]]] = {
    "room": ("project_id", Project),
    "wall": ("room_id", Room),
    "element": ("wall_id", Wall),
}


def _get_sync_entity(
    db: Session, model: type[SyncEntity], entity_id: str
) -> SyncEntity | None:
    if model is Customer:
        return db.get(Customer, entity_id)
    if model is Project:
        return db.get(Project, entity_id)
    if model is Room:
        return db.get(Room, entity_id)
    if model is Wall:
        return db.get(Wall, entity_id)
    return db.get(Element, entity_id)


def _lock_sync_entity(
    db: Session, model: type[SyncEntity], entity_id: str
) -> SyncEntity | None:
    if model is Customer:
        return (
            db.query(Customer)
            .filter(Customer.id == entity_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
    if model is Project:
        return (
            db.query(Project)
            .filter(Project.id == entity_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
    if model is Room:
        return (
            db.query(Room)
            .filter(Room.id == entity_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
    if model is Wall:
        return (
            db.query(Wall)
            .filter(Wall.id == entity_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
    return (
        db.query(Element)
        .filter(Element.id == entity_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def owned(entity: SyncEntity, db: Session, user: User) -> bool:
    if isinstance(entity, (Customer, Project)):
        return entity.owner_id == user.id
    parent: SyncEntity | None
    if isinstance(entity, Room):
        parent = db.get(Project, entity.project_id)
    elif isinstance(entity, Wall):
        parent = db.get(Room, entity.room_id)
    elif isinstance(entity, Element):
        parent = db.get(Wall, entity.wall_id)
    else:
        return False
    return parent is not None and owned(parent, db, user)


def snapshot(entity: Any) -> dict[str, Any]:
    encoded: dict[str, Any] = jsonable_encoder(
        {c.name: getattr(entity, c.name) for c in entity.__table__.columns}
    )
    return encoded


def _project_id_for_entity(
    db: Session, entity_type: str, entity: SyncEntity
) -> str | None:
    if entity_type == "customer":
        return None
    if isinstance(entity, Project):
        return entity.id
    if isinstance(entity, Room):
        return entity.project_id
    if isinstance(entity, (Wall, Element)):
        return resolve_project_id(db, entity_type, entity)
    return None


def _mark_entity_conflicts_resolved(
    db: Session,
    *,
    owner_id: str,
    entity_type: str,
    entity_id: str,
) -> list[str]:
    rows = (
        db.query(SyncOperation)
        .filter(
            SyncOperation.owner_id == owner_id,
            SyncOperation.entity_type == entity_type,
            SyncOperation.entity_id == entity_id,
            SyncOperation.status == "conflict",
        )
        .all()
    )
    ids: list[str] = []
    for row in rows:
        row.status = "resolved"
        ids.append(row.id)
    return ids


def check_element(values, wall, db, exclude=None):
    if values["offset_mm"] + values["width_mm"] > wall.length_mm:
        raise ValueError("Element exceeds wall length")
    bottom = values.get("sill_mm") or 0
    height = values.get("height_mm")
    if height is not None and bottom + height > wall.height_mm:
        raise ValueError("Element exceeds wall height")
    for e in (
        db.query(Element)
        .filter(Element.wall_id == wall.id, Element.is_deleted.is_(False))
        .all()
    ):
        if e.id == exclude:
            continue
        horizontal = (
            values["offset_mm"] < e.offset_mm + e.width_mm
            and e.offset_mm < values["offset_mm"] + values["width_mm"]
        )
        vertical = bottom < (e.sill_mm or 0) + (e.height_mm or wall.height_mm) and (
            e.sill_mm or 0
        ) < bottom + (height or wall.height_mm)
        if horizontal and vertical:
            raise ValueError("Element overlaps another element")


@router.post("/push")
def sync_push(
    payload: SyncPushRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    results: list[dict[str, Any]] = []
    for op in payload.operations:
        try:
            # Atomic receipt + mutation. A lost response can safely retry the same ID.
            with db.begin_nested():
                receipt = db.get(SyncOperation, op.id)
                if receipt:
                    if (
                        receipt.owner_id != user.id
                        or receipt.entity_id != op.entity_id
                        or receipt.entity_type != op.entity_type
                        or receipt.operation != op.operation
                        or (
                            op.operation != "delete"
                            and receipt.payload != op.payload
                        )
                        or receipt.base_version != op.base_version
                    ):
                        raise ValueError("Operation ID already used")
                    result: dict[str, Any] = {"id": op.id, "status": receipt.status}
                    receipt_model = MODELS.get(op.entity_type)
                    existing = (
                        _get_sync_entity(db, receipt_model, op.entity_id)
                        if receipt_model is not None
                        else None
                    )
                    if existing and owned(existing, db, user):
                        result.update(
                            server_version=existing.version,
                            server_payload=snapshot(existing),
                        )
                    results.append(result)
                    continue

                model = MODELS.get(op.entity_type)
                if not model or op.operation not in {"create", "update", "delete"}:
                    raise ValueError("Unsupported entity or operation")

                if op.operation == "delete":
                    if op.payload:
                        raise ValueError("Delete operation payload must be empty")
                    found = _get_sync_entity(db, model, op.entity_id)
                    if found is None or not owned(found, db, user):
                        raise ValueError("Entity not found or forbidden")
                    if op.base_version is None:
                        raise ValueError("base_version is required for deletes")
                    locked_del = _lock_sync_entity(db, model, op.entity_id)
                    if locked_del is None:
                        raise ValueError("Entity not found or forbidden")
                    entity = locked_del
                    proj_id = _project_id_for_entity(db, op.entity_type, entity)
                    if op.base_version != entity.version:
                        db.add(
                            SyncOperation(
                                id=op.id,
                                owner_id=user.id,
                                entity_type=op.entity_type,
                                entity_id=op.entity_id,
                                operation=op.operation,
                                payload=op.payload,
                                base_version=op.base_version,
                                status="conflict",
                            )
                        )
                        log_audit(
                            db,
                            user_id=user.id,
                            project_id=proj_id,
                            action="sync.conflict_detected",
                            entity_type=op.entity_type,
                            entity_id=op.entity_id,
                            old_values=entity_snapshot(op.entity_type, entity),
                            new_values={
                                "operation": "delete",
                                "base_version": op.base_version,
                            },
                            commit=False,
                        )
                        results.append(
                            {
                                "id": op.id,
                                "status": "conflict",
                                "server_version": entity.version,
                                "server_payload": snapshot(entity),
                            }
                        )
                        continue
                    if entity.is_deleted:
                        raise ValueError("Entity is already deleted")
                    before_snap = entity_snapshot(op.entity_type, entity)
                    del_resolved_ids = _mark_entity_conflicts_resolved(
                        db,
                        owner_id=user.id,
                        entity_type=op.entity_type,
                        entity_id=op.entity_id,
                    )
                    if isinstance(entity, Customer):
                        soft_delete_customer(
                            db, customer=entity, user_id=user.id, op_id=op.id
                        )
                    elif isinstance(entity, Project):
                        soft_delete_project(
                            db, project=entity, user_id=user.id, op_id=op.id
                        )
                    elif isinstance(entity, Room):
                        soft_delete_room(
                            db,
                            room=entity,
                            project_id=entity.project_id,
                            user_id=user.id,
                            reason="sync_delete",
                            op_id=op.id,
                        )
                    elif isinstance(entity, Wall):
                        if proj_id is None:
                            raise ValueError("Project not found for wall")
                        soft_delete_wall(
                            db,
                            wall=entity,
                            project_id=proj_id,
                            user_id=user.id,
                            reason="sync_delete",
                            op_id=op.id,
                        )
                    elif isinstance(entity, Element):
                        if proj_id is None:
                            raise ValueError("Project not found for element")
                        soft_delete_element(
                            db,
                            elem=entity,
                            project_id=proj_id,
                            user_id=user.id,
                            reason="sync_delete",
                            op_id=op.id,
                        )
                    if del_resolved_ids:
                        log_audit(
                            db,
                            user_id=user.id,
                            project_id=proj_id,
                            action="sync.conflict_resolved",
                            entity_type=op.entity_type,
                            entity_id=op.entity_id,
                            old_values=before_snap,
                            new_values={
                                **entity_snapshot(op.entity_type, entity),
                                "resolution": "keep_local",
                                "resolved_conflicts": del_resolved_ids,
                            },
                            commit=False,
                        )
                    db.flush()
                    results.append(
                        {
                            "id": op.id,
                            "status": "applied",
                            "new_version": entity.version,
                            "is_deleted": True,
                        }
                    )
                    continue

                schema = SCHEMAS[op.entity_type]
                parent_spec = PARENTS.get(op.entity_type)
                parent_key = parent_spec[0] if parent_spec is not None else None
                allowed = set(schema.model_fields)
                if op.operation == "create" and parent_key:
                    allowed.add(parent_key)
                if op.operation == "update":
                    allowed.discard("source")
                    allowed.discard("confidence")
                    if op.entity_type in {"wall", "element"}:
                        allowed.add("review_status")
                if set(op.payload) - allowed:
                    raise ValueError("Protected or unknown fields in payload")
                preexisting = _get_sync_entity(db, model, op.entity_id)
                revision_reason = None
                audit_action = None
                audit_old = None
                resolved_ids: list[str] = []
                if op.operation == "create":
                    if preexisting is not None:
                        # An existing ID without a matching receipt is NOT an idempotent create.
                        raise ValueError("Entity ID already exists")
                    values = schema.model_validate(op.payload).model_dump(mode="json")
                    if parent_spec is not None and parent_key is not None:
                        parent_id = op.payload.get(parent_key)
                        parent = (
                            _get_sync_entity(db, parent_spec[1], str(parent_id))
                            if parent_id
                            else None
                        )
                        if (
                            parent is None
                            or getattr(parent, "is_deleted", False)
                            or not owned(parent, db, user)
                        ):
                            raise ValueError("Parent not found or forbidden")
                        values[parent_key] = parent_id
                    else:
                        values["owner_id"] = user.id
                    if op.entity_type in {"wall", "element"}:
                        values["review_status"] = derive_initial_review_status(
                            op.entity_type, values
                        )
                        values["approved_by"] = None
                        values["approved_at"] = None
                        revision_reason = "sync_create"
                    entity = model(id=op.entity_id, **values)
                    db.add(entity)
                    entity.version = 1
                    db.flush()
                    if isinstance(entity, (Wall, Element)) and values.get("source_observation_id"):
                        proj_id = resolve_project_id(db, op.entity_type, entity)
                        bind_observation_to_measurement(
                            db,
                            observation_id=values["source_observation_id"],
                            user_id=user.id,
                            project_id=proj_id,
                            entity_type=op.entity_type,
                            entity_id=entity.id,
                        )
                    audit_action = "sync.create"
                else:
                    if preexisting is None or not owned(preexisting, db, user):
                        raise ValueError("Entity not found or forbidden")
                    if op.base_version is None:
                        raise ValueError("base_version is required for updates")
                    # Lock the row before checking its version (PostgreSQL).
                    locked_upd = _lock_sync_entity(db, model, op.entity_id)
                    if locked_upd is None:
                        raise ValueError("Entity not found or forbidden")
                    entity = locked_upd
                    proj_id = _project_id_for_entity(db, op.entity_type, entity)
                    if op.base_version != entity.version or entity.is_deleted:
                        db.add(
                            SyncOperation(
                                id=op.id,
                                owner_id=user.id,
                                entity_type=op.entity_type,
                                entity_id=op.entity_id,
                                operation=op.operation,
                                payload=op.payload,
                                base_version=op.base_version,
                                status="conflict",
                            )
                        )
                        log_audit(
                            db,
                            user_id=user.id,
                            project_id=proj_id,
                            action="sync.conflict_detected",
                            entity_type=op.entity_type,
                            entity_id=op.entity_id,
                            old_values=entity_snapshot(op.entity_type, entity),
                            new_values=op.payload,
                            commit=False,
                        )
                        results.append(
                            {
                                "id": op.id,
                                "status": "conflict",
                                "server_version": entity.version,
                                "server_payload": snapshot(entity),
                            }
                        )
                        continue
                    audit_old = entity_snapshot(op.entity_type, entity)
                    was_approved = getattr(entity, "review_status", None) == "approved"
                    resolved_ids = _mark_entity_conflicts_resolved(
                        db,
                        owner_id=user.id,
                        entity_type=op.entity_type,
                        entity_id=op.entity_id,
                    )
                    # Validate the complete resulting model, not just changed fields.
                    merged = {**snapshot(entity), **op.payload}
                    validated = schema.model_validate(merged).model_dump(mode="json")
                    if isinstance(entity, (Wall, Element)):
                        if proj_id is None:
                            raise ValueError("Project not found for measurement")
                        if "review_status" in op.payload and op.payload[
                            "review_status"
                        ] not in {"approved", "needs_review", "incomplete"}:
                            raise ValueError("Invalid review status")
                        approval = op.payload.get("review_status")
                        if approval == "approved" and set(op.payload) != {
                            "review_status"
                        }:
                            raise ValueError(
                                "Approval must be a separate explicit operation"
                            )
                        if approval == "approved":
                            approve_entity(
                                db,
                                project_id=proj_id,
                                entity_type=op.entity_type,
                                entity=entity,
                                user_id=user.id,
                                change_reason="sync_approve",
                            )
                            sync_linked_observation_approval(
                                db,
                                observation_id=entity.source_observation_id,
                                approved=True,
                            )
                            audit_action = "sync.approve"
                        else:
                            ensure_baseline_revision(
                                db,
                                project_id=proj_id,
                                entity_type=op.entity_type,
                                entity=entity,
                                fallback_user_id=user.id,
                            )
                            previous_obs_id = entity.source_observation_id
                            if "source_observation_id" in op.payload:
                                if op.payload["source_observation_id"]:
                                    bind_observation_to_measurement(
                                        db,
                                        observation_id=op.payload["source_observation_id"],
                                        user_id=user.id,
                                        project_id=proj_id,
                                        entity_type=op.entity_type,
                                        entity_id=entity.id,
                                    )
                                unlink_replaced_observation(
                                    db,
                                    previous_observation_id=previous_obs_id,
                                    new_observation_id=op.payload["source_observation_id"],
                                )
                            for key in op.payload:
                                if key != "review_status":
                                    setattr(entity, key, validated.get(key, op.payload[key]))
                            entity.review_status = derive_updated_review_status(
                                op.entity_type, merged, approval
                            )
                            entity.approved_by = None
                            entity.approved_at = None
                            entity.version += 1
                            sync_linked_observation_approval(
                                db,
                                observation_id=entity.source_observation_id,
                                approved=False,
                            )
                            revision_reason = "sync_update"
                            audit_action = "sync.edit_after_approval" if was_approved else "sync.update"
                    else:
                        for key in op.payload:
                            setattr(entity, key, validated.get(key, op.payload[key]))
                        entity.version += 1
                        audit_action = "sync.update"
                if isinstance(entity, Project) and entity.customer_id:
                    customer = db.get(Customer, entity.customer_id)
                    if (
                        customer is None
                        or customer.owner_id != user.id
                        or customer.is_deleted
                    ):
                        raise ValueError("Customer not found or forbidden")
                if isinstance(entity, Element):
                    with db.no_autoflush:
                        check_element(
                            snapshot(entity),
                            db.get(Wall, entity.wall_id),
                            db,
                            exclude=entity.id,
                        )
                if isinstance(entity, Wall):
                    with db.no_autoflush:
                        for element in (
                            db.query(Element)
                            .filter(
                                Element.wall_id == entity.id,
                                Element.is_deleted.is_(False),
                            )
                            .all()
                        ):
                            if (
                                element.offset_mm + element.width_mm > entity.length_mm
                                or (element.sill_mm or 0) + (element.height_mm or 0)
                                > entity.height_mm
                            ):
                                raise ValueError(
                                    "Wall resize would place an element out of bounds"
                                )
                proj_id = _project_id_for_entity(db, op.entity_type, entity)
                if revision_reason is not None and isinstance(entity, (Wall, Element)):
                    if proj_id is None:
                        raise ValueError("Project not found for measurement")
                    db.flush()
                    append_revision(
                        db,
                        project_id=proj_id,
                        entity_type=op.entity_type,
                        entity=entity,
                        change_reason=revision_reason,
                        user_id=user.id,
                    )
                new_snap = entity_snapshot(op.entity_type, entity)
                if audit_action is not None:
                    log_audit(
                        db,
                        user_id=user.id,
                        project_id=proj_id,
                        action=audit_action,
                        entity_type=op.entity_type,
                        entity_id=entity.id,
                        old_values=audit_old,
                        new_values=new_snap,
                        commit=False,
                    )
                if resolved_ids:
                    log_audit(
                        db,
                        user_id=user.id,
                        project_id=proj_id,
                        action="sync.conflict_resolved",
                        entity_type=op.entity_type,
                        entity_id=entity.id,
                        old_values=audit_old,
                        new_values={
                            **new_snap,
                            "resolution": "keep_local",
                            "resolved_conflicts": resolved_ids,
                        },
                        commit=False,
                    )
                db.add(
                    SyncOperation(
                        id=op.id,
                        owner_id=user.id,
                        entity_type=op.entity_type,
                        entity_id=op.entity_id,
                        operation=op.operation,
                        payload=op.payload,
                        base_version=op.base_version,
                        status="applied",
                    )
                )
                db.flush()
                results.append(
                    {"id": op.id, "status": "applied", "new_version": entity.version}
                )
            db.commit()
        except (ValueError, ValidationError, IntegrityError) as exc:
            # Savepoint rollback leaves subsequent independent operations usable.
            results.append(
                {
                    "id": op.id,
                    "status": "failed",
                    "error": (
                        "Invalid operation or conflicting identifier"
                        if isinstance(exc, IntegrityError)
                        else str(exc)
                    ),
                }
            )
    db.commit()
    return {"results": results}


@router.get("/pull")
def sync_pull(
    since: str | None = None,
    entity_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_since: datetime | None = None
    q = db.query(SyncOperation).filter(SyncOperation.owner_id == user.id)
    if since:
        try:
            parsed_since = datetime.fromisoformat(since)
            q = q.filter(SyncOperation.created_at > parsed_since)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid timestamp")
    if entity_type:
        q = q.filter(SyncOperation.entity_type == entity_type)
    operations = q.order_by(SyncOperation.created_at, SyncOperation.id).limit(100).all()
    tombstones = collect_tombstones(
        db,
        user_id=user.id,
        since=parsed_since,
        entity_type=entity_type,
    )
    return {
        "operations": [snapshot(o) for o in operations],
        "tombstones": tombstones,
        "server_time": datetime.now(UTC).isoformat(),
    }


@router.get("/conflicts")
def list_conflicts(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return [
        snapshot(o)
        for o in db.query(SyncOperation)
        .filter_by(owner_id=user.id, status="conflict")
        .limit(100)
        .all()
    ]


@router.post("/conflicts/{operation_id}/resolve")
def resolve_conflict(
    operation_id: str,
    payload: ConflictResolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conflict_op = db.get(SyncOperation, operation_id)
    if conflict_op is None or conflict_op.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Conflict operation not found")
    if conflict_op.status != "conflict":
        raise HTTPException(status_code=409, detail="Operation is not in conflict state")

    model = MODELS.get(conflict_op.entity_type)
    if model is None:
        raise HTTPException(status_code=400, detail="Unsupported entity type")
    entity = _lock_sync_entity(db, model, conflict_op.entity_id)
    if entity is None or not owned(entity, db, user):
        raise HTTPException(status_code=404, detail="Entity not found")

    proj_id = _project_id_for_entity(db, conflict_op.entity_type, entity)

    if payload.resolution == "keep_server":
        resolved_ids = _mark_entity_conflicts_resolved(
            db,
            owner_id=user.id,
            entity_type=conflict_op.entity_type,
            entity_id=conflict_op.entity_id,
        )
        server_snap = entity_snapshot(conflict_op.entity_type, entity)
        log_audit(
            db,
            user_id=user.id,
            project_id=proj_id,
            action="sync.conflict_resolved",
            entity_type=conflict_op.entity_type,
            entity_id=conflict_op.entity_id,
            old_values={
                "conflicted_payload": conflict_op.payload,
                "base_version": conflict_op.base_version,
            },
            new_values={
                **server_snap,
                "resolution": "keep_server",
                "resolved_conflicts": resolved_ids,
            },
            commit=False,
        )
        db.commit()
        return {
            "status": "resolved",
            "resolution": "keep_server",
            "server_version": entity.version,
            "server_payload": snapshot(entity),
        }

    # keep_local: rebase and apply against current server version
    expected_version = payload.base_version if payload.base_version is not None else entity.version
    if expected_version != entity.version:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Version conflict",
                "expected_version": expected_version,
                "current_version": entity.version,
            },
        )
    if entity.is_deleted:
        raise HTTPException(status_code=409, detail="Entity is deleted on server")

    local_payload = payload.payload if payload.payload is not None else (conflict_op.payload or {})
    schema = SCHEMAS[conflict_op.entity_type]
    allowed = set(schema.model_fields) - {"source", "confidence"}
    if conflict_op.entity_type in {"wall", "element"}:
        allowed.add("review_status")
    if set(local_payload) - allowed:
        raise HTTPException(status_code=422, detail="Protected or unknown fields in payload")
    if local_payload.get("review_status") == "approved":
        raise HTTPException(
            status_code=422,
            detail="Conflict resolution cannot set review_status to approved",
        )

    old_snap = entity_snapshot(conflict_op.entity_type, entity)
    was_approved = getattr(entity, "review_status", None) == "approved"
    merged = {**snapshot(entity), **local_payload}
    try:
        validated = schema.model_validate(merged).model_dump(mode="json")
    except ValidationError as err:
        raise HTTPException(status_code=422, detail=str(err))

    if isinstance(entity, (Wall, Element)):
        if proj_id is None:
            raise HTTPException(status_code=404, detail="Project not found")
        ensure_baseline_revision(
            db,
            project_id=proj_id,
            entity_type=conflict_op.entity_type,
            entity=entity,
            fallback_user_id=user.id,
        )
        for key in local_payload:
            if key != "review_status":
                setattr(entity, key, validated.get(key, local_payload[key]))
        entity.review_status = derive_updated_review_status(
            conflict_op.entity_type, merged, local_payload.get("review_status")
        )
        entity.approved_by = None
        entity.approved_at = None
        entity.version += 1
        sync_linked_observation_approval(
            db, observation_id=entity.source_observation_id, approved=False
        )
        if isinstance(entity, Element):
            try:
                check_element(snapshot(entity), db.get(Wall, entity.wall_id), db, exclude=entity.id)
            except ValueError as err:
                raise HTTPException(status_code=400, detail=str(err))
        db.flush()
        append_revision(
            db,
            project_id=proj_id,
            entity_type=conflict_op.entity_type,
            entity=entity,
            change_reason="conflict_keep_local",
            user_id=user.id,
        )
    else:
        for key in local_payload:
            setattr(entity, key, validated.get(key, local_payload[key]))
        entity.version += 1
        db.flush()

    resolved_ids = _mark_entity_conflicts_resolved(
        db,
        owner_id=user.id,
        entity_type=conflict_op.entity_type,
        entity_id=conflict_op.entity_id,
    )
    new_snap = entity_snapshot(conflict_op.entity_type, entity)
    if was_approved:
        log_audit(
            db,
            user_id=user.id,
            project_id=proj_id,
            action="sync.edit_after_approval",
            entity_type=conflict_op.entity_type,
            entity_id=conflict_op.entity_id,
            old_values=old_snap,
            new_values=new_snap,
            commit=False,
        )
    log_audit(
        db,
        user_id=user.id,
        project_id=proj_id,
        action="sync.conflict_resolved",
        entity_type=conflict_op.entity_type,
        entity_id=conflict_op.entity_id,
        old_values=old_snap,
        new_values={
            **new_snap,
            "resolution": "keep_local",
            "resolved_conflicts": resolved_ids,
        },
        commit=False,
    )
    db.commit()
    return {
        "status": "resolved",
        "resolution": "keep_local",
        "new_version": entity.version,
        "server_payload": snapshot(entity),
    }
