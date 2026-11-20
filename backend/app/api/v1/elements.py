from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import Element, Project, Room, User, Wall
from app.schemas.element import ElementCreate, ElementOut, ElementUpdate
from app.schemas.revision import MeasurementRevisionOut
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
from app.services.tombstones import soft_delete_element

router = APIRouter(tags=["elements"])


def get_wall_and_project(wall_id: str, db: Session, user: User, *, allow_deleted: bool = False):
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


def get_element_and_project(
    element_id: str,
    db: Session,
    user: User,
    *,
    allow_deleted: bool = False,
):
    elem = db.get(Element, element_id)
    if not elem or (elem.is_deleted and not allow_deleted):
        raise HTTPException(status_code=404, detail="Element not found")
    wall = db.get(Wall, elem.wall_id)
    room = db.get(Room, wall.room_id)
    project = db.get(Project, room.project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if (wall.is_deleted or room.is_deleted or project.is_deleted) and not allow_deleted:
        raise HTTPException(status_code=404, detail="Element not found")
    return elem, wall, room, project


@router.post("/walls/{wall_id}/elements", response_model=ElementOut, status_code=201)
def create_element(
    wall_id: str,
    payload: ElementCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wall, _, project = get_wall_and_project(wall_id, db, user)
    from app.api.v1.sync import check_element

    values = payload.model_dump(mode="json")
    try:
        check_element(values, wall, db)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    initial_status = derive_initial_review_status("element", values)
    elem = Element(
        wall_id=wall_id,
        label=payload.label,
        kind=str(payload.kind),
        offset_mm=payload.offset_mm,
        width_mm=payload.width_mm,
        height_mm=payload.height_mm,
        sill_mm=payload.sill_mm,
        depth_mm=payload.depth_mm,
        source=payload.source,
        confidence=payload.confidence,
        source_observation_id=payload.source_observation_id,
        review_status=initial_status,
        approved_by=None,
        approved_at=None,
    )
    db.add(elem)
    db.flush()
    if payload.source_observation_id:
        bind_observation_to_measurement(
            db,
            observation_id=payload.source_observation_id,
            user_id=user.id,
            project_id=project.id,
            entity_type="element",
            entity_id=elem.id,
        )
    append_revision(
        db,
        project_id=project.id,
        entity_type="element",
        entity=elem,
        change_reason="create",
        user_id=user.id,
    )
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.create",
        entity_type="element",
        entity_id=elem.id,
        old_values=None,
        new_values=entity_snapshot("element", elem),
        commit=False,
    )
    db.commit()
    db.refresh(elem)
    set_etag(response, elem.version)
    return elem


@router.get("/walls/{wall_id}/elements", response_model=list[ElementOut])
def list_elements(
    wall_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_wall_and_project(wall_id, db, user, allow_deleted=include_deleted)
    q = db.query(Element).filter(Element.wall_id == wall_id)
    if not include_deleted:
        q = q.filter(Element.is_deleted.is_(False))
    return q.order_by(Element.offset_mm).all()


@router.get("/elements/{element_id}", response_model=ElementOut)
def get_element(
    element_id: str,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, _ = get_element_and_project(element_id, db, user, allow_deleted=include_deleted)
    set_etag(response, elem.version)
    return elem


@router.get("/elements/{element_id}/revisions", response_model=list[MeasurementRevisionOut])
def get_element_revisions(
    element_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, _ = get_element_and_project(element_id, db, user, allow_deleted=True)
    return list_revisions(db, "element", elem.id)


@router.put("/elements/{element_id}", response_model=ElementOut)
def update_element(
    element_id: str,
    payload: ElementUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, wall, _, project = get_element_and_project(element_id, db, user)
    data = payload.model_dump(
        mode="json",
        exclude_unset=True,
        exclude={"version", "base_version"},
    )
    if "review_status" in data and data["review_status"] is None:
        raise HTTPException(status_code=422, detail="review_status cannot be null")

    merged_preview = {c.name: getattr(elem, c.name) for c in elem.__table__.columns}
    merged_preview.update(data)
    try:
        ElementCreate.model_validate(merged_preview)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid element dimensions")

    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    elem = lock_and_verify_version(db, Element, element_id, expected)

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
    old_snap = entity_snapshot("element", elem)
    was_approved = elem.review_status == "approved"
    if data.get("source_observation_id"):
        bind_observation_to_measurement(
            db,
            observation_id=data["source_observation_id"],
            user_id=user.id,
            project_id=project.id,
            entity_type="element",
            entity_id=elem.id,
        )
    for k, v in data.items():
        if k != "review_status":
            setattr(elem, k, str(v) if k == "kind" and v is not None else v)
    elem.review_status = derive_updated_review_status(
        "element", merged, data.get("review_status")
    )
    elem.approved_by = None
    elem.approved_at = None
    elem.version += 1
    sync_linked_observation_approval(
        db, observation_id=elem.source_observation_id, approved=False
    )
    append_revision(
        db,
        project_id=project.id,
        entity_type="element",
        entity=elem,
        change_reason="update",
        user_id=user.id,
    )
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.edit_after_approval" if was_approved else "element.update",
        entity_type="element",
        entity_id=elem.id,
        old_values=old_snap,
        new_values=entity_snapshot("element", elem),
        detail=str(data),
        commit=False,
    )
    db.commit()
    db.refresh(elem)
    set_etag(response, elem.version)
    return elem


@router.delete("/elements/{element_id}")
def delete_element(
    element_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, project = get_element_and_project(element_id, db, user)
    soft_delete_element(db, elem=elem, project_id=project.id, user_id=user.id)
    db.commit()
    return {"status": "deleted", "id": elem.id, "is_deleted": True, "version": elem.version}


@router.post("/elements/{element_id}/approve", response_model=ElementOut)
def approve_element(
    element_id: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    elem, _, _, project = get_element_and_project(element_id, db, user)
    old_snap = entity_snapshot("element", elem)
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
    sync_linked_observation_approval(
        db, observation_id=elem.source_observation_id, approved=True
    )
    log_audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="element.approve",
        entity_type="element",
        entity_id=elem.id,
        old_values=old_snap,
        new_values=entity_snapshot("element", elem),
        detail=f"approved_by={user.id} approved_at={elem.approved_at.isoformat()}",
        commit=False,
    )
    db.commit()
    db.refresh(elem)
    set_etag(response, elem.version)
    return elem
