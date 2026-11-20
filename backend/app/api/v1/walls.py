from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room, Wall, Element
from app.schemas.revision import MeasurementRevisionOut
from app.schemas.wall import WallCreate, WallUpdate, WallOut
from app.services.audit import log_audit
from app.services.revisions import (
    append_revision,
    approve_entity,
    derive_initial_review_status,
    derive_updated_review_status,
    ensure_baseline_revision,
    list_revisions,
)

router = APIRouter(tags=["walls"])


def get_room_and_check(room_id: str, db: Session, user: User):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return room, project


def get_wall_and_check(wall_id: str, db: Session, user: User):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return wall, room, project


@router.post("/rooms/{room_id}/walls", response_model=WallOut, status_code=201)
def create_wall(
    room_id: str,
    payload: WallCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room, project = get_room_and_check(room_id, db, user)
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
        review_status=initial_status,
        approved_by=None,
        approved_at=None,
    )
    db.add(wall)
    db.flush()
    append_revision(
        db,
        project_id=project.id,
        entity_type="wall",
        entity=wall,
        change_reason="create",
        user_id=user.id,
    )
    project.version += 1
    room.version += 1
    db.commit()
    db.refresh(wall)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.create",
        entity_type="wall",
        entity_id=wall.id,
    )
    return wall


@router.get("/rooms/{room_id}/walls", response_model=list[WallOut])
def list_walls(
    room_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_room_and_check(room_id, db, user)
    return db.query(Wall).filter(Wall.room_id == room_id).order_by(Wall.label).all()


@router.get("/walls/{wall_id}", response_model=WallOut)
def get_wall(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, _ = get_wall_and_check(wall_id, db, user)
    return wall


@router.get("/walls/{wall_id}/revisions", response_model=list[MeasurementRevisionOut])
def get_wall_revisions(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, _ = get_wall_and_check(wall_id, db, user)
    return list_revisions(db, "wall", wall.id)


@router.put("/walls/{wall_id}", response_model=WallOut)
def update_wall(
    wall_id: str,
    payload: WallUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, room, project = get_wall_and_check(wall_id, db, user)
    data = payload.model_dump(exclude_unset=True)
    if "review_status" in data and data["review_status"] is None:
        raise HTTPException(status_code=422, detail="review_status cannot be null")

    merged = {c.name: getattr(wall, c.name) for c in wall.__table__.columns}
    merged.update(data)
    try:
        WallCreate.model_validate(merged)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid wall dimensions")
    for element in db.query(Element).filter_by(wall_id=wall.id).all():
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
    for k, v in data.items():
        if k != "review_status":
            setattr(wall, k, v)
    wall.review_status = derive_updated_review_status(
        "wall", merged, data.get("review_status")
    )
    wall.approved_by = None
    wall.approved_at = None
    wall.version += 1
    project.version += 1
    room.version += 1
    append_revision(
        db,
        project_id=project.id,
        entity_type="wall",
        entity=wall,
        change_reason="update",
        user_id=user.id,
    )
    db.commit()
    db.refresh(wall)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.update",
        entity_type="wall",
        entity_id=wall.id,
        detail=str(data),
    )
    return wall


@router.delete("/walls/{wall_id}")
def delete_wall(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, room, project = get_wall_and_check(wall_id, db, user)
    db.delete(wall)
    project.version += 1
    room.version += 1
    db.commit()
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.delete",
        entity_type="wall",
        entity_id=wall.id,
    )
    return {"status": "deleted"}


@router.post("/walls/{wall_id}/approve", response_model=WallOut)
def approve_wall(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, room, project = get_wall_and_check(wall_id, db, user)
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
    project.version += 1
    room.version += 1
    db.commit()
    db.refresh(wall)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="wall.approve",
        entity_type="wall",
        entity_id=wall.id,
        detail=f"approved_by={user.id} approved_at={wall.approved_at.isoformat()}",
    )
    return wall
