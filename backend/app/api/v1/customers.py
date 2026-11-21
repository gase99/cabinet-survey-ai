from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import Customer, User
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.services.audit import entity_snapshot, log_audit
from app.services.concurrency import lock_and_verify_version, resolve_expected_version, set_etag
from app.services.tombstones import soft_delete_customer

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = Customer(
        owner_id=user.id,
        name=payload.name,
        phone=payload.phone,
        address=payload.address,
        notes=payload.notes,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="customer.create",
        entity_type="customer",
        entity_id=c.id,
        old_values=None,
        new_values=entity_snapshot("customer", c),
    )
    set_etag(response, c.version)
    return c


@router.get("", response_model=list[CustomerOut])
def list_customers(
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Customer).filter(Customer.owner_id == user.id)
    if not include_deleted:
        query = query.filter(Customer.is_deleted.is_(False))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.address.ilike(like),
            )
        )
    query = (
        query.order_by(Customer.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return query.all()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: str,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = db.get(Customer, customer_id)
    if not c or c.owner_id != user.id or (c.is_deleted and not include_deleted):
        raise HTTPException(status_code=404, detail="Customer not found")
    set_etag(response, c.version)
    return c


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = db.get(Customer, customer_id)
    if not c or c.owner_id != user.id or c.is_deleted:
        raise HTTPException(status_code=404, detail="Customer not found")
    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    c = lock_and_verify_version(db, Customer, customer_id, expected)
    old_snap = entity_snapshot("customer", c)
    data = payload.model_dump(exclude_unset=True, exclude={"version", "base_version"})
    for k, v in data.items():
        setattr(c, k, v)
    c.version += 1
    db.commit()
    db.refresh(c)
    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="customer.update",
        entity_type="customer",
        entity_id=c.id,
        old_values=old_snap,
        new_values=entity_snapshot("customer", c),
    )
    set_etag(response, c.version)
    return c


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = db.get(Customer, customer_id)
    if not c or c.owner_id != user.id or c.is_deleted:
        raise HTTPException(status_code=404, detail="Customer not found")
    soft_delete_customer(db, customer=c, user_id=user.id)
    db.commit()
    return {"status": "deleted", "id": c.id, "is_deleted": True, "version": c.version}
