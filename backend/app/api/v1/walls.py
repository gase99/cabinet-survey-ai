from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room, Wall
from app.schemas.wall import WallCreate, WallUpdate, WallOut
from app.services.audit import log_audit

router = APIRouter(tags=["walls"])

def get_room_and_check(room_id: str, db: Session, user: User):
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return room, project

@router.post("/rooms/{room_id}/walls", response_model=WallOut, status_code=201)
def create_wall(room_id: str, payload: WallCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room, project = get_room_and_check(room_id, db, user)
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
        review_status="approved" if payload.source == "manual" else "needs_review",
    )
    db.add(wall)
    project.version += 1
    room.version += 1
    db.commit()
    db.refresh(wall)
    log_audit(db, user_id=user.id, project_id=project.id, action="wall.create", entity_type="wall", entity_id=wall.id)
    return wall

@router.get("/rooms/{room_id}/walls", response_model=list[WallOut])
def list_walls(room_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    room, _ = get_room_and_check(room_id, db, user)
    return db.query(Wall).filter(Wall.room_id == room_id).order_by(Wall.label).all()

@router.get("/walls/{wall_id}", response_model=WallOut)
def get_wall(wall_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return wall

@router.put("/walls/{wall_id}", response_model=WallOut)
def update_wall(wall_id: str, payload: WallUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = payload.model_dump(exclude_unset=True)
    # If approved value edited, reset to needs_review unless explicitly approved
    editing_approved = wall.review_status == "approved" and any(k in data for k in ["length_mm","height_mm","start_x_mm","start_y_mm","end_x_mm","end_y_mm"])
    for k, v in data.items():
        setattr(wall, k, v)
    if editing_approved and "review_status" not in data:
        wall.review_status = "needs_review"
    wall.version += 1
    project.version += 1
    room.version += 1
    db.commit()
    db.refresh(wall)
    log_audit(db, user_id=user.id, project_id=project.id, action="wall.update", entity_type="wall", entity_id=wall.id, detail=str(data))
    return wall

@router.delete("/walls/{wall_id}")
def delete_wall(wall_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(wall)
    project.version += 1
    room.version += 1
    db.commit()
    log_audit(db, user_id=user.id, project_id=project.id, action="wall.delete", entity_type="wall", entity_id=wall.id)
    return {"status": "deleted"}

@router.post("/walls/{wall_id}/approve", response_model=WallOut)
def approve_wall(wall_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    wall.review_status = "approved"
    wall.version += 1
    db.commit()
    db.refresh(wall)
    log_audit(db, user_id=user.id, project_id=project.id, action="wall.approve", entity_type="wall", entity_id=wall.id)
    return wall
