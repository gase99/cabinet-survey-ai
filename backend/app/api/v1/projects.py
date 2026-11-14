from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Project, Customer
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut
from app.services.audit import log_audit

router = APIRouter(prefix="/projects", tags=["projects"])

def assert_ownership(project: Project, user: User):
    if project.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized for this project")

@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.customer_id:
        cust = db.get(Customer, payload.customer_id)
        if not cust or cust.owner_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid customer_id")
    p = Project(owner_id=user.id, title=payload.title, customer_id=payload.customer_id, site_notes=payload.site_notes, status=payload.status)
    db.add(p)
    db.commit()
    db.refresh(p)
    log_audit(db, user_id=user.id, project_id=p.id, action="project.create", entity_type="project", entity_id=p.id)
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
        query = query.filter(Project.is_deleted == False)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Project.title.ilike(like), Project.site_notes.ilike(like)))
    if status:
        query = query.filter(Project.status == status)
    query = query.order_by(desc(Project.updated_at)).offset((page-1)*page_size).limit(page_size)
    return query.all()

@router.get("/recent", response_model=list[ProjectOut])
def recent_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.owner_id == user.id, Project.is_deleted == False).order_by(desc(Project.updated_at)).limit(5).all()  # noqa: E712

@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    return p

@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    data = payload.model_dump(exclude_unset=True)
    if data.get("customer_id"):
        customer = db.get(Customer,data["customer_id"])
        if customer is None or customer.owner_id != p.owner_id:
            raise HTTPException(400,"Invalid customer_id")
    # Handle status transitions: deleted via status field not allowed here; use delete endpoint
    # Allow archive/restore via status
    for k, v in data.items():
        if k == "status" and v == "deleted":
            # mark deleted
            p.is_deleted = True
            p.status = "archived"
        else:
            setattr(p, k, v)
    p.version += 1
    db.commit()
    db.refresh(p)
    log_audit(db, user_id=user.id, project_id=p.id, action="project.update", entity_type="project", entity_id=p.id, detail=str(data))
    return p

@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    p.is_deleted = True
    p.status = "archived"
    p.version += 1
    db.commit()
    log_audit(db, user_id=user.id, project_id=p.id, action="project.soft_delete", entity_type="project", entity_id=p.id)
    return {"status": "deleted", "id": p.id}

@router.post("/{project_id}/restore")
def restore_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    if not p.is_deleted:
        raise HTTPException(status_code=400, detail="Project is not deleted")
    p.is_deleted = False
    p.status = "draft"
    p.version += 1
    db.commit()
    log_audit(db, user_id=user.id, project_id=p.id, action="project.restore", entity_type="project", entity_id=p.id)
    return {"status": "restored"}

@router.post("/{project_id}/archive")
def archive_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    p.status = "archived"
    p.version += 1
    db.commit()
    return {"status": "archived"}

# Project history/audit
@router.get("/{project_id}/history")
def project_history(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    assert_ownership(p, user)
    from app.models.db_models import AuditEvent
    events = db.query(AuditEvent).filter(AuditEvent.project_id == project_id).order_by(desc(AuditEvent.created_at)).limit(100).all()
    return [{"id": e.id, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id, "detail": e.detail, "created_at": e.created_at, "user_id": e.user_id} for e in events]
