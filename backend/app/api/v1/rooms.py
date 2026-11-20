from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import Project, Room, User
from app.schemas.room import RoomCreate, RoomOut, RoomUpdate
from app.services.audit import entity_snapshot, log_audit
from app.services.concurrency import lock_and_verify_version, resolve_expected_version, set_etag
from app.services.tombstones import soft_delete_room

router = APIRouter(tags=["rooms"])


@router.post("/projects/{project_id}/rooms", response_model=RoomOut, status_code=201)
def create_room(
    project_id: str,
    payload: RoomCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    room = Room(project_id=project_id, label=payload.label, room_type=payload.room_type)
    db.add(room)
    db.commit()
    db.refresh(room)
    log_audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="room.create",
        entity_type="room",
        entity_id=room.id,
        old_values=None,
        new_values=entity_snapshot("room", room),
    )
    set_etag(response, room.version)
    return room


@router.get("/projects/{project_id}/rooms", response_model=list[RoomOut])
def list_rooms(
    project_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    q = db.query(Room).filter(Room.project_id == project_id)
    if not include_deleted:
        q = q.filter(Room.is_deleted.is_(False))
    return q.order_by(Room.created_at).all()


@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(
    room_id: str,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if not room or (room.is_deleted and not include_deleted):
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    set_etag(response, room.version)
    return room


@router.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(
    room_id: str,
    payload: RoomUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if not room or room.is_deleted:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    room = lock_and_verify_version(db, Room, room_id, expected)
    old_snap = entity_snapshot("room", room)
    data = payload.model_dump(exclude_unset=True, exclude={"version", "base_version"})
    for k, v in data.items():
        setattr(room, k, v)
    room.version += 1
    db.commit()
    db.refresh(room)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="room.update",
        entity_type="room",
        entity_id=room.id,
        old_values=old_snap,
        new_values=entity_snapshot("room", room),
    )
    set_etag(response, room.version)
    return room


@router.delete("/rooms/{room_id}")
def delete_room(
    room_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(Room, room_id)
    if not room or room.is_deleted:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    soft_delete_room(db, room=room, project_id=project.id, user_id=user.id)
    db.commit()
    return {"status": "deleted", "id": room.id, "is_deleted": True, "version": room.version}
