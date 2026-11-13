from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room, Wall, Element
from app.schemas.element import ElementCreate, ElementUpdate, ElementOut
from app.services.audit import log_audit

router = APIRouter(tags=["elements"])

def get_wall_and_project(wall_id: str, db, user):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return wall, room, project

@router.post("/walls/{wall_id}/elements", response_model=ElementOut, status_code=201)
def create_element(wall_id: str, payload: ElementCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wall, room, project = get_wall_and_project(wall_id, db, user)
    # Validate bounds
    if payload.offset_mm + payload.width_mm > wall.length_mm:
        raise HTTPException(status_code=400, detail=f"Element exceeds wall length {wall.length_mm} mm")
    # Overlap check (simple)
    existing = db.query(Element).filter(Element.wall_id == wall_id).all()
    for e in existing:
        a_end = e.offset_mm + e.width_mm
        b_end = payload.offset_mm + payload.width_mm
        if not (b_end <= e.offset_mm or payload.offset_mm >= a_end):
            raise HTTPException(status_code=400, detail=f"Element overlaps with existing element {e.id} ({e.label})")
    elem = Element(
        wall_id=wall_id,
        label=payload.label,
        kind=payload.kind,
        offset_mm=payload.offset_mm,
        width_mm=payload.width_mm,
        height_mm=payload.height_mm,
        sill_mm=payload.sill_mm,
        depth_mm=payload.depth_mm,
        source=payload.source,
        review_status="approved" if payload.source == "manual" else "needs_review",
    )
    db.add(elem)
    project.version += 1
    room.version += 1
    wall.version += 1
    db.commit()
    db.refresh(elem)
    log_audit(db, user_id=user.id, project_id=project.id, action="element.create", entity_type="element", entity_id=elem.id)
    return elem

@router.get("/walls/{wall_id}/elements", response_model=list[ElementOut])
def list_elements(wall_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wall, _, _ = get_wall_and_project(wall_id, db, user)
    return db.query(Element).filter(Element.wall_id == wall_id).order_by(Element.offset_mm).all()

@router.get("/elements/{element_id}", response_model=ElementOut)
def get_element(element_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    elem = db.get(Element, element_id)
    if not elem:
        raise HTTPException(status_code=404, detail="Element not found")
    wall = db.get(Wall, elem.wall_id)
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return elem

@router.put("/elements/{element_id}", response_model=ElementOut)
def update_element(element_id: str, payload: ElementUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    elem = db.get(Element, element_id)
    if not elem:
        raise HTTPException(status_code=404, detail="Element not found")
    wall = db.get(Wall, elem.wall_id)
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = payload.model_dump(exclude_unset=True)
    # If changing offset/width, revalidate
    new_offset = data.get("offset_mm", elem.offset_mm)
    new_width = data.get("width_mm", elem.width_mm)
    if new_offset + new_width > wall.length_mm:
        raise HTTPException(status_code=400, detail="Element exceeds wall length")
    editing_approved = elem.review_status == "approved" and any(k in data for k in ["offset_mm","width_mm","height_mm","sill_mm"])
    for k, v in data.items():
        setattr(elem, k, v)
    if editing_approved and "review_status" not in data:
        elem.review_status = "needs_review"
    elem.version += 1
    project.version += 1
    db.commit()
    db.refresh(elem)
    log_audit(db, user_id=user.id, project_id=project.id, action="element.update", entity_type="element", entity_id=elem.id, detail=str(data))
    return elem

@router.delete("/elements/{element_id}")
def delete_element(element_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    elem = db.get(Element, element_id)
    if not elem:
        raise HTTPException(status_code=404, detail="Element not found")
    wall = db.get(Wall, elem.wall_id)
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(elem)
    project.version += 1
    db.commit()
    log_audit(db, user_id=user.id, project_id=project.id, action="element.delete", entity_type="element", entity_id=elem.id)
    return {"status": "deleted"}

@router.post("/elements/{element_id}/approve", response_model=ElementOut)
def approve_element(element_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    elem = db.get(Element, element_id)
    if not elem:
        raise HTTPException(status_code=404, detail="Element not found")
    wall = db.get(Wall, elem.wall_id)
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elem.review_status = "approved"
    elem.version += 1
    db.commit()
    db.refresh(elem)
    log_audit(db, user_id=user.id, project_id=project.id, action="element.approve", entity_type="element", entity_id=elem.id)
    return elem
