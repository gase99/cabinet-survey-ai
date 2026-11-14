from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room
from app.schemas.room import RoomCreate, RoomUpdate, RoomOut
from app.services.audit import log_audit

router = APIRouter(tags=["rooms"])

@router.post("/projects/{project_id}/rooms", response_model=RoomOut, status_code=201)
def create_room(project_id: str, payload: RoomCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    room = Room(project_id=project_id, label=payload.label, room_type=payload.room_type)
    db.add(room)
    project.version += 1
    db.commit()
    db.refresh(room)
    log_audit(db, user_id=user.id, project_id=project_id, action="room.create", entity_type="room", entity_id=room.id)
    return room

@router.get("/projects/{project_id}/rooms", response_model=list[RoomOut])
def list_rooms(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return db.query(Room).filter(Room.project_id == project_id).order_by(Room.created_at).all()

@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return room

@router.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: str, payload: RoomUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(room, k, v)
    room.version += 1
    project.version += 1
    db.commit()
    db.refresh(room)
    log_audit(db, user_id=user.id, project_id=project.id, action="room.update", entity_type="room", entity_id=room.id)
    return room

@router.delete("/rooms/{room_id}")
def delete_room(room_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(room)
    project.version += 1
    db.commit()
    log_audit(db, user_id=user.id, project_id=project.id, action="room.delete", entity_type="room", entity_id=room.id)
    return {"status": "deleted"}
