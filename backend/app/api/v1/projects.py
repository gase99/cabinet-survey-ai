from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import Customer, Project, User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.audit import entity_snapshot, log_audit, serialize_audit_event
from app.services.concurrency import lock_and_verify_version, resolve_expected_version, set_etag
from app.services.tombstones import soft_delete_project

router = APIRouter(prefix="/projects", tags=["projects"])


def assert_ownership(project: Project, user: User):
    if project.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized for this project")


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.customer_id:
        cust = db.get(Customer, payload.customer_id)
        if not cust or cust.owner_id != user.id or cust.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid customer_id")
    p = Project(
        owner_id=user.id,
        title=payload.title,
        customer_id=payload.customer_id,
        site_notes=payload.site_notes,
        status=payload.status,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_audit(
        db,
        user_id=user.id,
        project_id=p.id,
        action="project.create",
        entity_type="project",
        entity_id=p.id,
        old_values=None,
        new_values=entity_snapshot("project", p),
    )
    set_etag(response, p.version)
    return p


@router.get("", response_model=list[ProjectOut])
def list_projects(
    q: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Project).filter(Project.owner_id == user.id)
    if not include_deleted:
        query = query.filter(Project.is_deleted.is_(False))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Project.title.ilike(like), Project.site_notes.ilike(like))
        )
    if status:
        query = query.filter(Project.status == status)
    query = (
        query.order_by(desc(Project.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return query.all()


@router.get("/recent", response_model=list[ProjectOut])
def recent_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return (
        db.query(Project)
        .filter(Project.owner_id == user.id, Project.is_deleted.is_(False))
        .order_by(desc(Project.updated_at))
        .limit(5)
        .all()
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    set_etag(response, p.version)
    return p


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Project, project_id)
    if not p or p.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    p = lock_and_verify_version(db, Project, project_id, expected)
    old_snap = entity_snapshot("project", p)
    data = payload.model_dump(exclude_unset=True, exclude={"version", "base_version"})
    if data.get("customer_id"):
        customer = db.get(Customer, data["customer_id"])
        if customer is None or customer.owner_id != p.owner_id or customer.is_deleted:
            raise HTTPException(status_code=400, detail="Invalid customer_id")
    if data.get("status") == "deleted":
        soft_delete_project(db, project=p, user_id=user.id)
        for k, v in data.items():
            if k != "status":
                setattr(p, k, v)
        db.commit()
        db.refresh(p)
    else:
        for k, v in data.items():
            setattr(p, k, v)
        p.version += 1
        db.commit()
        db.refresh(p)
        log_audit(
            db,
            user_id=user.id,
            project_id=p.id,
            action="project.update",
            entity_type="project",
            entity_id=p.id,
            old_values=old_snap,
            new_values=entity_snapshot("project", p),
            detail=str(data),
        )
    set_etag(response, p.version)
    return p


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    if not p.is_deleted:
        soft_delete_project(db, project=p, user_id=user.id)
        db.commit()
    return {"status": "deleted", "id": p.id, "is_deleted": True, "version": p.version}


@router.post("/{project_id}/restore")
def restore_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    if not p.is_deleted:
        raise HTTPException(status_code=400, detail="Project is not deleted")
    old_snap = entity_snapshot("project", p)
    p.is_deleted = False
    p.deleted_at = None
    p.status = "draft"
    p.version += 1
    db.commit()
    db.refresh(p)
    log_audit(
        db,
        user_id=user.id,
        project_id=p.id,
        action="project.restore",
        entity_type="project",
        entity_id=p.id,
        old_values=old_snap,
        new_values=entity_snapshot("project", p),
    )
    return {"status": "restored"}


@router.post("/{project_id}/archive")
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    old_snap = entity_snapshot("project", p)
    p.status = "archived"
    p.version += 1
    db.commit()
    db.refresh(p)
    log_audit(
        db,
        user_id=user.id,
        project_id=p.id,
        action="project.archive",
        entity_type="project",
        entity_id=p.id,
        old_values=old_snap,
        new_values=entity_snapshot("project", p),
    )
    return {"status": "archived"}


@router.get("/{project_id}/history")
def project_history(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    from app.models.db_models import AuditEvent

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.project_id == project_id)
        .order_by(desc(AuditEvent.created_at))
        .limit(100)
        .all()
    )
    return [serialize_audit_event(e) for e in events]
