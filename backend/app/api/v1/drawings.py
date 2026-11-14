from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room, Wall, Element, DrawingVersion
from app.services.geometry_service import walls_and_elements_from_room
from app.services.audit import log_audit

router = APIRouter(prefix="/drawings", tags=["drawings"])

def get_project_and_check(project_id: str, db, user):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.get("/{project_id}/plan")
def get_plan(project_id: str, room_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project_and_check(project_id, db, user)
    # Pick first room if not specified
    if room_id:
        room = db.get(Room, room_id)
        if not room or room.project_id != project_id:
            raise HTTPException(status_code=404, detail="Room not found")
    else:
        room = db.query(Room).filter(Room.project_id == project_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="No rooms in project")
    walls = db.query(Wall).filter(Wall.room_id == room.id).order_by(Wall.created_at, Wall.id).all()
    wall_ids = [w.id for w in walls]
    elements = db.query(Element).filter(Element.wall_id.in_(wall_ids)).all() if wall_ids else []
    result = walls_and_elements_from_room(room, walls, elements)
    return {
        "project_id": project_id,
        "room_id": room.id,
        "plan_svg": result.svg_plan,
        "elevations": result.elevations,
        "area_mm2": result.area_mm2,
        "perimeter_mm": result.perimeter_mm,
        "errors": [{"code": e.code, "message": e.message, "entity_ids": e.entity_ids} for e in result.errors],
        "warnings": [{"code": e.code, "message": e.message, "entity_ids": e.entity_ids} for e in result.warnings],
        "dimension_annotations": result.dimension_annotations,
        "metadata": result.metadata,
    }

@router.get("/{project_id}/elevations")
def get_elevations(project_id: str, room_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project_and_check(project_id, db, user)
    if room_id:
        room = db.get(Room, room_id)
        if not room or room.project_id != project_id:
            raise HTTPException(status_code=404, detail="Room not found")
    else:
        room = db.query(Room).filter(Room.project_id == project_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="No rooms in project")
    walls = db.query(Wall).filter(Wall.room_id == room.id).order_by(Wall.created_at, Wall.id).all()
    elements = db.query(Element).filter(Element.wall_id.in_([w.id for w in walls])).all() if walls else []
    result = walls_and_elements_from_room(room, walls, elements)
    return {"project_id": project_id, "room_id": room.id, "elevations": result.elevations}

@router.get("/{project_id}/plan.svg", response_class=PlainTextResponse)
def get_plan_svg(project_id: str, room_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project_and_check(project_id, db, user)
    room = db.get(Room, room_id) if room_id else db.query(Room).filter(Room.project_id == project_id).first()
    if not room or room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")
    walls = db.query(Wall).filter(Wall.room_id == room.id).order_by(Wall.created_at, Wall.id).all()
    elements = db.query(Element).filter(Element.wall_id.in_([w.id for w in walls])).all() if walls else []
    result = walls_and_elements_from_room(room, walls, elements)
    return PlainTextResponse(result.svg_plan, media_type="image/svg+xml")

@router.post("/{project_id}/versions", status_code=201)
def create_drawing_version(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project_and_check(project_id, db, user)
    room = db.query(Room).filter(Room.project_id == project_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="No rooms")
    walls = db.query(Wall).filter(Wall.room_id == room.id).order_by(Wall.created_at, Wall.id).all()
    elements = db.query(Element).filter(Element.wall_id.in_([w.id for w in walls])).all() if walls else []
    result = walls_and_elements_from_room(room, walls, elements)
    if result.errors:
        raise HTTPException(status_code=400, detail={"message": "Cannot version with geometry errors", "errors": [{"code": e.code, "message": e.message} for e in result.errors]})
    if any(e.review_status != "approved" for e in [*walls, *elements]):
        raise HTTPException(status_code=409, detail="Explicit approval is required before versioning")
    # Determine next version
    last = db.query(DrawingVersion).filter(DrawingVersion.project_id == project_id).order_by(DrawingVersion.version.desc()).first()
    next_ver = (last.version + 1) if last else 1
    dv = DrawingVersion(project_id=project_id, version=next_ver, plan_svg=result.svg_plan, metadata_json=result.metadata, created_by=user.id)
    db.add(dv)
    db.commit()
    db.refresh(dv)
    log_audit(db, user_id=user.id, project_id=project_id, action="drawing.version_create", entity_type="drawing_version", entity_id=dv.id, detail=f"v{next_ver}")
    return {"id": dv.id, "version": dv.version, "created_at": dv.created_at}

@router.get("/{project_id}/versions")
def list_versions(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project_and_check(project_id, db, user)
    versions = db.query(DrawingVersion).filter(DrawingVersion.project_id == project_id).order_by(DrawingVersion.version.desc()).all()
    return [{"id": v.id, "version": v.version, "created_at": v.created_at, "created_by": v.created_by} for v in versions]
