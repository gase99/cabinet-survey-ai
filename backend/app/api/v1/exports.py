import os
from types import SimpleNamespace
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
from app.services.revisions import missing_element_dimensions, missing_wall_dimensions

router = APIRouter(prefix="/exports", tags=["exports"])


def get_project_and_check(project_id: str, db, user):
    p = db.get(Project, project_id)
    if not p or p.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _wall_issues(wall: Wall) -> list[str]:
    issues: list[str] = []
    if wall.review_status != "approved":
        issues.append(wall.review_status)
    missing = missing_wall_dimensions(wall)
    if missing:
        issues.append(f"unknown {', '.join(missing)}")
    return issues


def _element_issues(elem: Element) -> list[str]:
    issues: list[str] = []
    if elem.review_status != "approved":
        issues.append(elem.review_status)
    missing = missing_element_dimensions(elem)
    if missing and "incomplete" not in issues:
        issues.append("incomplete")
    if missing:
        issues.append(f"unknown {', '.join(missing)}")
    return issues


def _flagged_wall_proxy(wall: Wall, issues: list[str]):
    label = (
        f"{wall.label} [UNAPPROVED: {', '.join(issues)}]"
        if issues
        else wall.label
    )
    return SimpleNamespace(
        id=wall.id,
        label=label,
        length_mm=wall.length_mm,
        height_mm=wall.height_mm,
        start_x_mm=wall.start_x_mm,
        start_y_mm=wall.start_y_mm,
        end_x_mm=wall.end_x_mm,
        end_y_mm=wall.end_y_mm,
    )


def _flagged_element_proxy(elem: Element, issues: list[str]):
    tag = "INCOMPLETE" if any("unknown" in r or r == "incomplete" for r in issues) else "UNAPPROVED"
    label = (
        f"{elem.label} [{tag}: {', '.join(issues)}]"
        if issues
        else elem.label
    )
    return SimpleNamespace(
        id=elem.id,
        wall_id=elem.wall_id,
        label=label,
        kind=elem.kind,
        offset_mm=elem.offset_mm,
        width_mm=elem.width_mm,
        height_mm=elem.height_mm,
        sill_mm=elem.sill_mm,
        depth_mm=elem.depth_mm,
    )


@router.post("/{project_id}", response_model=dict, status_code=201)
def create_export(
    project_id: str,
    payload: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project_and_check(project_id, db, user)
    if payload.format not in ("pdf", "png"):
        raise HTTPException(status_code=400, detail="Invalid format")
    if payload.layout not in ("A3", "A4"):
        raise HTTPException(status_code=400, detail="Invalid layout")
    if payload.exclude_unapproved and payload.flag_unapproved:
        raise HTTPException(
            status_code=422,
            detail="Choose either exclude_unapproved or flag_unapproved, not both",
        )

    rooms = (
        db.query(Room)
        .filter(Room.project_id == project_id)
        .order_by(Room.created_at, Room.id)
        .all()
    )
    if not rooms:
        raise HTTPException(status_code=400, detail="Project has no rooms to export")

    plan_parts: list[tuple[str, str]] = []
    elevation_parts: list[tuple[str, str]] = []
    excluded_items: list[dict] = []
    flagged_items: list[dict] = []

    for room in rooms:
        walls = (
            db.query(Wall)
            .filter(Wall.room_id == room.id)
            .order_by(Wall.created_at, Wall.id)
            .all()
        )
        elements = (
            db.query(Element).filter(Element.wall_id.in_([w.id for w in walls])).all()
            if walls
            else []
        )

        wall_problems = [(w, _wall_issues(w)) for w in walls]
        elem_problems = [(e, _element_issues(e)) for e in elements]

        if payload.exclude_unapproved:
            bad_walls = [
                f"{w.label} ({', '.join(issues)})"
                for w, issues in wall_problems
                if issues
            ]
            if bad_walls:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Explicit approval is required for every wall before export "
                        f"(room '{room.label}'): {', '.join(bad_walls)}"
                    ),
                )
            render_elements = []
            for elem, issues in elem_problems:
                if issues:
                    excluded_items.append(
                        {
                            "room": room.label,
                            "entity_type": "element",
                            "id": elem.id,
                            "label": elem.label,
                            "review_status": elem.review_status,
                            "reasons": issues,
                        }
                    )
                else:
                    render_elements.append(elem)
            geom = walls_and_elements_from_room(room, walls, render_elements)
            if geom.errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Invalid geometry",
                        "errors": [e.code for e in geom.errors],
                        "room": room.label,
                    },
                )
        elif payload.flag_unapproved:
            render_walls = []
            for wall, issues in wall_problems:
                if issues:
                    flagged_items.append(
                        {
                            "room": room.label,
                            "entity_type": "wall",
                            "id": wall.id,
                            "label": wall.label,
                            "review_status": wall.review_status,
                            "reasons": issues,
                        }
                    )
                render_walls.append(_flagged_wall_proxy(wall, issues))
            render_elements = []
            for elem, issues in elem_problems:
                if issues:
                    flagged_items.append(
                        {
                            "room": room.label,
                            "entity_type": "element",
                            "id": elem.id,
                            "label": elem.label,
                            "review_status": elem.review_status,
                            "reasons": issues,
                        }
                    )
                render_elements.append(_flagged_element_proxy(elem, issues))
            geom = walls_and_elements_from_room(room, render_walls, render_elements)
            if geom.errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Invalid geometry",
                        "errors": [e.code for e in geom.errors],
                        "room": room.label,
                    },
                )
        else:
            geom = walls_and_elements_from_room(room, walls, elements)
            if geom.errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Invalid geometry",
                        "errors": [e.code for e in geom.errors],
                        "room": room.label,
                    },
                )
            unapproved_or_incomplete = [
                f"{w.label} ({', '.join(issues)})"
                for w, issues in wall_problems
                if issues
            ] + [
                f"{e.label} ({', '.join(issues)})"
                for e, issues in elem_problems
                if issues
            ]
            if unapproved_or_incomplete:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Explicit approval is required for every wall and element "
                        f"(room '{room.label}'): {', '.join(unapproved_or_incomplete)}"
                    ),
                )

        if payload.include_plan and geom.svg_plan:
            plan_parts.append((f"Plan — {room.label}", geom.svg_plan))
        if payload.include_elevations:
            for wall_id, svg in geom.elevations.items():
                elevation_parts.append((f"{room.label} · Wall elevation {wall_id}", svg))

    views = plan_parts + elevation_parts
    if not views:
        raise HTTPException(status_code=422, detail="Select at least one drawing view")

    notices: list[str] = []
    if flagged_items:
        notices.append(
            "WARNING — PRELIMINARY UNAPPROVED/INCOMPLETE MEASUREMENTS (DO NOT FABRICATE)"
        )
        summary = ", ".join(
            f"{item['label']} [{'/'.join(item['reasons'])}]" for item in flagged_items
        )
        notices.append(f"Flagged items: {summary}")
    if excluded_items:
        summary = ", ".join(
            f"{item['label']} [{'/'.join(item['reasons'])}]" for item in excluded_items
        )
        notices.append(
            f"NOTE — Excluded unapproved/incomplete elements: {summary}"
        )

    job = ExportJob(
        project_id=project_id,
        owner_id=user.id,
        format=payload.format,
        layout=payload.layout,
        status="processing",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
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
                notices=notices or None,
            )
        else:
            path = render_views_png(
                project_title=project.title,
                views=views,
                layout=payload.layout,
                notices=notices or None,
            )
        job.file_path = path
        job.status = "done"
        db.commit()
        log_audit(
            db,
            user_id=user.id,
            project_id=project_id,
            action="export.create",
            entity_type="export_job",
            entity_id=job.id,
            detail=f"{payload.format} {payload.layout}",
        )
        return {
            "id": job.id,
            "status": job.status,
            "format": job.format,
            "layout": job.layout,
            "download_url": f"/api/v1/exports/{job.id}/download",
            "excluded_items": excluded_items,
            "flagged_items": flagged_items,
        }
    except Exception:
        job.status = "failed"
        job.error_message = "Drawing rendering failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Drawing rendering failed")


@router.get("", response_model=list[dict])
def list_exports(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ExportJob).filter(ExportJob.owner_id == user.id)
    if project_id:
        q = q.filter(ExportJob.project_id == project_id)
    q = q.order_by(ExportJob.created_at.desc()).limit(50)
    jobs = q.all()
    return [
        {
            "id": j.id,
            "project_id": j.project_id,
            "format": j.format,
            "layout": j.layout,
            "status": j.status,
            "download_url": f"/api/v1/exports/{j.id}/download",
            "error_message": j.error_message,
            "created_at": j.created_at,
        }
        for j in jobs
    ]


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(ExportJob, export_id)
    if not job or job.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Export not found")
    if job.status != "done" or not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="File not ready")
    media = "application/pdf" if job.format == "pdf" else "image/png"
    filename = f"{job.project_id}_{job.layout}.{job.format}"
    return FileResponse(job.file_path, media_type=media, filename=filename)


@router.get("/{export_id}")
def get_export(
    export_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(ExportJob, export_id)
    if not job or job.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Export not found")
    return {
        "id": job.id,
        "project_id": job.project_id,
        "format": job.format,
        "layout": job.layout,
        "status": job.status,
        "download_url": f"/api/v1/exports/{job.id}/download",
        "error_message": job.error_message,
        "created_at": job.created_at,
    }
