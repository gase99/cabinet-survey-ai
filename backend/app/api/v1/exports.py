from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room, Wall, Element, ExportJob
from app.schemas.drawing import ExportRequest
from app.services.geometry_service import walls_and_elements_from_room
from app.services.export_service import render_views_pdf, render_views_png
from app.services.audit import log_audit
import os

router = APIRouter(prefix="/exports", tags=["exports"])

def get_project_and_check(project_id: str, db, user):
    p = db.get(Project, project_id)
    if not p or p.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return p

@router.post("/{project_id}", response_model=dict, status_code=201)
def create_export(project_id: str, payload: ExportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project_and_check(project_id, db, user)
    if payload.format not in ("pdf","png"):
        raise HTTPException(status_code=400, detail="Invalid format")
    if payload.layout not in ("A3","A4"):
        raise HTTPException(status_code=400, detail="Invalid layout")

    rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.created_at, Room.id).all()
    if not rooms:
        raise HTTPException(status_code=400, detail="Project has no rooms to export")

    # Every room is exported, not just the first one. A geometry error or an
    # unapproved measurement in ANY included room fails the whole export.
    plan_parts: list[tuple[str, str]] = []
    elevation_parts: list[tuple[str, str]] = []
    for room in rooms:
        walls = db.query(Wall).filter(Wall.room_id == room.id).order_by(Wall.created_at, Wall.id).all()
        elements = db.query(Element).filter(Element.wall_id.in_([w.id for w in walls])).all() if walls else []
        geom = walls_and_elements_from_room(room, walls, elements)
        if geom.errors:
            raise HTTPException(status_code=400, detail={"message": "Invalid geometry",
                "errors": [e.code for e in geom.errors], "room": room.label})
        unapproved = [entity.label for entity in [*walls, *elements]
                      if entity.review_status != "approved"]
        if unapproved:
            raise HTTPException(status_code=409,
                detail=f"Explicit approval is required for every wall and element (room '{room.label}')")
        if payload.include_plan and geom.svg_plan:
            plan_parts.append((f"Plan — {room.label}", geom.svg_plan))
        if payload.include_elevations:
            for wall_id, svg in geom.elevations.items():
                elevation_parts.append((f"{room.label} · Wall elevation {wall_id}", svg))

    views = plan_parts + elevation_parts
    if not views:
        raise HTTPException(status_code=422, detail="Select at least one drawing view")

    job = ExportJob(project_id=project_id, owner_id=user.id, format=payload.format, layout=payload.layout, status="processing")
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        customer_name = project.customer_id  # we could join but keep id
        # Resolve customer name
        if project.customer_id:
            from app.models.db_models import Customer
            cust = db.get(Customer, project.customer_id)
            customer_name = cust.name if cust else project.customer_id
        else:
            customer_name = None

        if payload.format == "pdf":
            path = render_views_pdf(
                project_title=project.title,
                customer_name=customer_name,
                views=views,
                layout=payload.layout,
            )
        else:
            path = render_views_png(
                project_title=project.title,
                views=views,
                layout=payload.layout,
            )
        job.file_path = path
        job.status = "done"
        db.commit()
        log_audit(db, user_id=user.id, project_id=project_id, action="export.create", entity_type="export_job", entity_id=job.id, detail=f"{payload.format} {payload.layout}")
        return {"id": job.id, "status": job.status, "format": job.format, "layout": job.layout, "download_url": f"/api/v1/exports/{job.id}/download"}
    except Exception as e:
        job.status = "failed"
        job.error_message = "Drawing rendering failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Drawing rendering failed")

@router.get("", response_model=list[dict])
def list_exports(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(ExportJob).filter(ExportJob.owner_id == user.id)
    if project_id:
        q = q.filter(ExportJob.project_id == project_id)
    q = q.order_by(ExportJob.created_at.desc()).limit(50)
    jobs = q.all()
    return [{"id": j.id, "project_id": j.project_id, "format": j.format, "layout": j.layout, "status": j.status, "download_url": f"/api/v1/exports/{j.id}/download", "error_message": j.error_message, "created_at": j.created_at} for j in jobs]

@router.get("/{export_id}/download")
def download_export(export_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(ExportJob, export_id)
    if not job or job.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Export not found")
    if job.status != "done" or not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="File not ready")
    media = "application/pdf" if job.format == "pdf" else "image/png"
    filename = f"{job.project_id}_{job.layout}.{job.format}"
    return FileResponse(job.file_path, media_type=media, filename=filename)

@router.get("/{export_id}")
def get_export(export_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(ExportJob, export_id)
    if not job or job.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Export not found")
    return {"id": job.id, "project_id": job.project_id, "format": job.format, "layout": job.layout, "status": job.status, "download_url": f"/api/v1/exports/{job.id}/download", "error_message": job.error_message, "created_at": job.created_at}
