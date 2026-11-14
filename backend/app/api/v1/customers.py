from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerOut
from app.services.audit import log_audit

router = APIRouter(prefix="/customers", tags=["customers"])

@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = Customer(owner_id=user.id, name=payload.name, phone=payload.phone, address=payload.address, notes=payload.notes)
    db.add(c)
    db.commit()
    db.refresh(c)
    log_audit(db, user_id=user.id, project_id=None, action="customer.create", entity_type="customer", entity_id=c.id)
    return c

@router.get("", response_model=list[CustomerOut])
def list_customers(q: str | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Customer).filter(Customer.owner_id == user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.address.ilike(like)))
    query = query.order_by(Customer.updated_at.desc()).offset((page-1)*page_size).limit(page_size)
    return query.all()

@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Customer, customer_id)
    if not c or c.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Customer not found")
    return c

@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, payload: CustomerUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Customer, customer_id)
    if not c or c.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Customer not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.version += 1
    db.commit()
    db.refresh(c)
    log_audit(db, user_id=user.id, project_id=None, action="customer.update", entity_type="customer", entity_id=c.id)
    return c

@router.delete("/{customer_id}")
def delete_customer(customer_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Customer, customer_id)
    if not c or c.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Customer not found")
    db.delete(c)
    db.commit()
    log_audit(db, user_id=user.id, project_id=None, action="customer.delete", entity_type="customer", entity_id=c.id)
    return {"status": "deleted"}
