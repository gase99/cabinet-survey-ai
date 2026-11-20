from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Room, Wall, Element
from app.schemas.element import ElementCreate, ElementUpdate, ElementOut
from app.schemas.revision import MeasurementRevisionOut
from app.services.audit import log_audit
from app.services.revisions import (
    append_revision,
    approve_entity,
    derive_initial_review_status,
    derive_updated_review_status,
    ensure_baseline_revision,
    list_revisions,
)

router = APIRouter(tags=["elements"])


def get_wall_and_project(wall_id: str, db: Session, user: User):
    wall = db.get(Wall, wall_id)
    if not wall:
        raise HTTPException(status_code=404, detail="Wall not found")
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return wall, room, project


def get_element_and_project(element_id: str, db: Session, user: User):
    elem = db.get(Element, element_id)
    if not elem:
        raise HTTPException(status_code=404, detail="Element not found")
    wall = db.get(Wall, elem.wall_id)
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return elem, wall, room, project


@router.post("/walls/{wall_id}/elements", response_model=ElementOut, status_code=201)
def create_element(
    wall_id: str,
    payload: ElementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, room, project = get_wall_and_project(wall_id, db, user)
    from app.api.v1.sync import check_element

    values = payload.model_dump()
    try:
        check_element(values, wall, db)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    initial_status = derive_initial_review_status("element", values)
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
        review_status=initial_status,
        approved_by=None,
        approved_at=None,
    )
    db.add(elem)
    db.flush()
    append_revision(
        db,
        project_id=project.id,
        entity_type="element",
        entity=elem,
        change_reason="create",
        user_id=user.id,
    )
    project.version += 1
    room.version += 1
    wall.version += 1
    db.commit()
    db.refresh(elem)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.create",
        entity_type="element",
        entity_id=elem.id,
    )
    return elem


@router.get("/walls/{wall_id}/elements", response_model=list[ElementOut])
def list_elements(
    wall_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_wall_and_project(wall_id, db, user)
    return db.query(Element).filter(Element.wall_id == wall_id).order_by(Element.offset_mm).all()


@router.get("/elements/{element_id}", response_model=ElementOut)
def get_element(
    element_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, _ = get_element_and_project(element_id, db, user)
    return elem


@router.get("/elements/{element_id}/revisions", response_model=list[MeasurementRevisionOut])
def get_element_revisions(
    element_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, _ = get_element_and_project(element_id, db, user)
    return list_revisions(db, "element", elem.id)


@router.put("/elements/{element_id}", response_model=ElementOut)
def update_element(
    element_id: str,
    payload: ElementUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, wall, room, project = get_element_and_project(element_id, db, user)
    data = payload.model_dump(exclude_unset=True)
    if "review_status" in data and data["review_status"] is None:
        raise HTTPException(status_code=422, detail="review_status cannot be null")

    from app.api.v1.sync import check_element

    merged = {c.name: getattr(elem, c.name) for c in elem.__table__.columns}
    merged.update(data)
    try:
        ElementCreate.model_validate(merged)
        check_element(merged, wall, db, exclude=elem.id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid element dimensions or overlapping placement",
        )

    ensure_baseline_revision(
        db,
        project_id=project.id,
        entity_type="element",
        entity=elem,
        fallback_user_id=user.id,
    )
    for k, v in data.items():
        if k != "review_status":
            setattr(elem, k, v)
    elem.review_status = derive_updated_review_status(
        "element", merged, data.get("review_status")
    )
    elem.approved_by = None
    elem.approved_at = None
    elem.version += 1
    project.version += 1
    room.version += 1
    wall.version += 1
    append_revision(
        db,
        project_id=project.id,
        entity_type="element",
        entity=elem,
        change_reason="update",
        user_id=user.id,
    )
    db.commit()
    db.refresh(elem)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.update",
        entity_type="element",
        entity_id=elem.id,
        detail=str(data),
    )
    return elem


@router.delete("/elements/{element_id}")
def delete_element(
    element_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, project = get_element_and_project(element_id, db, user)
    db.delete(elem)
    project.version += 1
    db.commit()
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.delete",
        entity_type="element",
        entity_id=elem.id,
    )
    return {"status": "deleted"}


@router.post("/elements/{element_id}/approve", response_model=ElementOut)
def approve_element(
    element_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, wall, room, project = get_element_and_project(element_id, db, user)
    try:
        approve_entity(
            db,
            project_id=project.id,
            entity_type="element",
            entity=elem,
            user_id=user.id,
        )
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err))
    project.version += 1
    room.version += 1
    wall.version += 1
    db.commit()
    db.refresh(elem)
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.approve",
        entity_type="element",
        entity_id=elem.id,
        detail=f"approved_by={user.id} approved_at={elem.approved_at.isoformat()}",
    )
    return elem
