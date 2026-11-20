from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import Element, Project, Room, User, Wall
from app.schemas.revision import MeasurementRevisionOut
from app.schemas.wall import WallCreate, WallOut, WallUpdate
from app.services.audit import entity_snapshot, log_audit
from app.services.concurrency import lock_and_verify_version, resolve_expected_version, set_etag
from app.services.provenance import bind_observation_to_measurement, sync_linked_observation_approval
from app.services.revisions import (
    append_revision,
    approve_entity,
    derive_initial_review_status,
    derive_updated_review_status,
    ensure_baseline_revision,
    list_revisions,
)
from app.services.tombstones import soft_delete_wall

router = APIRouter(tags=["walls"])


def get_room_and_check(room_id: str, db: Session, user: User, *, allow_deleted: bool = False):
    room = db.get(Room, room_id)
    if not room or (room.is_deleted and not allow_deleted):
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if project.is_deleted and not allow_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return room, project


def get_wall_and_check(wall_id: str, db: Session, user: User, *, allow_deleted: bool = False):
    wall = db.get(Wall, wall_id)
    if not wall or (wall.is_deleted and not allow_deleted):
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if (room.is_deleted or project.is_deleted) and not allow_deleted:
        raise HTTPException(status_code=404, detail="Wall not found")
    return wall, room, project


@router.post("/rooms/{room_id}/walls", response_model=WallOut, status_code=201)
def create_wall(
    room_id: str,
    payload: WallCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, project = get_room_and_check(room_id, db, user)
    values = payload.model_dump()
    initial_status = derive_initial_review_status("wall", values)
    wall = Wall(
        room_id=room_id,
        label=payload.label,
        length_mm=payload.length_mm,
        height_mm=payload.height_mm,
        start_x_mm=payload.start_x_mm,
        start_y_mm=payload.start_y_mm,
        end_x_mm=payload.end_x_mm,
        end_y_mm=payload.end_y_mm,
        source=payload.source,
        confidence=payload.confidence,
        source_observation_id=payload.source_observation_id,
        review_status=initial_status,
        approved_by=None,
        approved_at=None,
    )
    db.add(wall)
    db.flush()
    if payload.source_observation_id:
        bind_observation_to_measurement(
            db,
            observation_id=payload.source_observation_id,
            user_id=user.id,
            project_id=project.id,
            entity_type="wall",
            entity_id=wall.id,
        )
    append_revision(
        db,
        project_id=project.id,
        entity_type="wall",
        entity=wall,
        change_reason="create",
        user_id=user.id,
    )
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.create",
        entity_type="wall",
        entity_id=wall.id,
        old_values=None,
        new_values=entity_snapshot("wall", wall),
        commit=False,
    )
    db.commit()
    db.refresh(wall)
    set_etag(response, wall.version)
    return wall


@router.get("/rooms/{room_id}/walls", response_model=list[WallOut])
def list_walls(
    room_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_room_and_check(room_id, db, user, allow_deleted=include_deleted)
    q = db.query(Wall).filter(Wall.room_id == room_id)
    if not include_deleted:
        q = q.filter(Wall.is_deleted.is_(False))
    return q.order_by(Wall.label).all()


@router.get("/walls/{wall_id}", response_model=WallOut)
def get_wall(
    wall_id: str,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, _ = get_wall_and_check(wall_id, db, user, allow_deleted=include_deleted)
    set_etag(response, wall.version)
    return wall


@router.get("/walls/{wall_id}/revisions", response_model=list[MeasurementRevisionOut])
def get_wall_revisions(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, _ = get_wall_and_check(wall_id, db, user, allow_deleted=True)
    return list_revisions(db, "wall", wall.id)


@router.put("/walls/{wall_id}", response_model=WallOut)
def update_wall(
    wall_id: str,
    payload: WallUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, project = get_wall_and_check(wall_id, db, user)
    data = payload.model_dump(exclude_unset=True, exclude={"version", "base_version"})
    if "review_status" in data and data["review_status"] is None:
        raise HTTPException(status_code=422, detail="review_status cannot be null")

    merged_preview = {c.name: getattr(wall, c.name) for c in wall.__table__.columns}
    merged_preview.update(data)
    try:
        WallCreate.model_validate(merged_preview)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid wall dimensions")

    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    wall = lock_and_verify_version(db, Wall, wall_id, expected)
    merged = {c.name: getattr(wall, c.name) for c in wall.__table__.columns}
    merged.update(data)
    try:
        WallCreate.model_validate(merged)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid wall dimensions")

    for element in (
        db.query(Element)
        .filter(Element.wall_id == wall.id, Element.is_deleted.is_(False))
        .all()
    ):
        if (
            element.offset_mm + element.width_mm > merged["length_mm"]
            or (element.sill_mm or 0) + (element.height_mm or 0) > merged["height_mm"]
        ):
            raise HTTPException(
                status_code=400,
                detail="Wall resize would place an element outside bounds",
            )

    ensure_baseline_revision(
        db,
        project_id=project.id,
        entity_type="wall",
        entity=wall,
        fallback_user_id=user.id,
    )
    old_snap = entity_snapshot("wall", wall)
    was_approved = wall.review_status == "approved"
    if data.get("source_observation_id"):
        bind_observation_to_measurement(
            db,
            observation_id=data["source_observation_id"],
            user_id=user.id,
            project_id=project.id,
            entity_type="wall",
            entity_id=wall.id,
        )
    for k, v in data.items():
        if k != "review_status":
            setattr(wall, k, v)
    wall.review_status = derive_updated_review_status(
        "wall", merged, data.get("review_status")
    )
    wall.approved_by = None
    wall.approved_at = None
    wall.version += 1
    sync_linked_observation_approval(
        db, observation_id=wall.source_observation_id, approved=False
    )
    append_revision(
        db,
        project_id=project.id,
        entity_type="wall",
        entity=wall,
        change_reason="update",
        user_id=user.id,
    )
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.edit_after_approval" if was_approved else "wall.update",
        entity_type="wall",
        entity_id=wall.id,
        old_values=old_snap,
        new_values=entity_snapshot("wall", wall),
        detail=str(data),
        commit=False,
    )
    db.commit()
    db.refresh(wall)
    set_etag(response, wall.version)
    return wall


@router.delete("/walls/{wall_id}")
def delete_wall(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, project = get_wall_and_check(wall_id, db, user)
    soft_delete_wall(db, wall=wall, project_id=project.id, user_id=user.id)
    db.commit()
    return {"status": "deleted", "id": wall.id, "is_deleted": True, "version": wall.version}


@router.post("/walls/{wall_id}/approve", response_model=WallOut)
def approve_wall(
    wall_id: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, project = get_wall_and_check(wall_id, db, user)
    old_snap = entity_snapshot("wall", wall)
    try:
        approve_entity(
            db,
            project_id=project.id,
            entity_type="wall",
            entity=wall,
            user_id=user.id,
        )
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err))
    sync_linked_observation_approval(
        db, observation_id=wall.source_observation_id, approved=True
    )
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.approve",
        entity_type="wall",
        entity_id=wall.id,
        old_values=old_snap,
        new_values=entity_snapshot("wall", wall),
        detail=f"approved_by={user.id} approved_at={wall.approved_at.isoformat()}",
        commit=False,
    )
    db.commit()
    db.refresh(wall)
    set_etag(response, wall.version)
    return wall
