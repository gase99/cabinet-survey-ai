"""Versioned local outbox writes. Never trust parent IDs or arbitrary ORM fields."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Customer, Project, Room, Wall, Element, SyncOperation
from app.schemas.sync import SyncPushRequest
from app.schemas.customer import CustomerCreate
from app.schemas.project import ProjectCreate
from app.schemas.room import RoomCreate
from app.schemas.wall import WallCreate
from app.schemas.element import ElementCreate

router = APIRouter(prefix="/sync", tags=["sync"])
MODELS = {"customer": Customer, "project": Project, "room": Room, "wall": Wall, "element": Element}
SCHEMAS = {"customer": CustomerCreate, "project": ProjectCreate, "room": RoomCreate, "wall": WallCreate, "element": ElementCreate}
PARENTS = {"room": ("project_id", Project), "wall": ("room_id", Room), "element": ("wall_id", Wall)}


def owned(entity, db, user):
    if isinstance(entity, (Customer, Project)):
        return entity.owner_id == user.id
    if isinstance(entity, Room):
        parent = db.get(Project, entity.project_id)
    elif isinstance(entity, Wall):
        parent = db.get(Room, entity.room_id)
    elif isinstance(entity, Element):
        parent = db.get(Wall, entity.wall_id)
    else:
        return False
    return parent is not None and owned(parent, db, user)


def snapshot(entity):
    return jsonable_encoder({c.name: getattr(entity, c.name) for c in entity.__table__.columns})


def check_element(values, wall, db, exclude=None):
    if values['offset_mm'] + values['width_mm'] > wall.length_mm:
        raise ValueError("Element exceeds wall length")
    bottom = values.get('sill_mm') or 0
    height = values.get('height_mm')
    if height is not None and bottom + height > wall.height_mm:
        raise ValueError("Element exceeds wall height")
    for e in db.query(Element).filter(Element.wall_id == wall.id).all():
        if e.id == exclude:
            continue
        horizontal = values['offset_mm'] < e.offset_mm + e.width_mm and e.offset_mm < values['offset_mm'] + values['width_mm']
        vertical = bottom < (e.sill_mm or 0) + (e.height_mm or wall.height_mm) and (e.sill_mm or 0) < bottom + (height or wall.height_mm)
        if horizontal and vertical:
            raise ValueError("Element overlaps another element")


@router.post("/push")
def sync_push(payload: SyncPushRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    results = []
    for op in payload.operations:
        try:
            # Atomic receipt + mutation. A lost response can safely retry the same ID.
            with db.begin_nested():
                receipt = db.get(SyncOperation, op.id)
                if receipt:
                    if receipt.owner_id != user.id or receipt.entity_id != op.entity_id or receipt.entity_type != op.entity_type or receipt.operation != op.operation or receipt.payload != op.payload or receipt.base_version != op.base_version:
                        raise ValueError("Operation ID already used")
                    result = {"id": op.id, "status": receipt.status}
                    existing = db.get(MODELS.get(op.entity_type), op.entity_id) if op.entity_type in MODELS else None
                    if existing and owned(existing, db, user):
                        result.update(server_version=existing.version, server_payload=snapshot(existing))
                    results.append(result)
                    continue
                model = MODELS.get(op.entity_type)
                if not model or op.operation not in {"create", "update"}:
                    raise ValueError("Unsupported entity or operation; archive projects rather than deleting offline")
                schema = SCHEMAS[op.entity_type]
                parent_key = PARENTS.get(op.entity_type, (None, None))[0]
                allowed = set(schema.model_fields)
                if op.operation == 'create' and parent_key:
                    allowed.add(parent_key)
                if op.operation == 'update':
                    allowed.discard('source')
                    allowed.discard('confidence')
                    if op.entity_type in {'wall','element'}:
                        allowed.add('review_status')
                if set(op.payload) - allowed:
                    raise ValueError("Protected or unknown fields in payload")
                entity = db.get(model, op.entity_id)
                if op.operation == 'create':
                    if entity:
                        # An existing ID without a matching receipt is NOT an idempotent create.
                        raise ValueError("Entity ID already exists")
                    values = schema.model_validate(op.payload).model_dump()
                    if parent_key:
                        parent_id = op.payload.get(parent_key)
                        parent = db.get(PARENTS[op.entity_type][1], parent_id) if parent_id else None
                        if parent is None or not owned(parent, db, user):
                            raise ValueError("Parent not found or forbidden")
                        values[parent_key] = parent_id
                    else:
                        values['owner_id'] = user.id
                    if op.entity_type in {'wall','element'}:
                        values['review_status'] = 'approved' if values.get('source') == 'manual' else 'needs_review'
                    entity = model(id=op.entity_id, **values)
                    db.add(entity)
                    entity.version = 1
                else:
                    if entity is None or not owned(entity, db, user):
                        raise ValueError("Entity not found or forbidden")
                    if op.base_version is None:
                        raise ValueError("base_version is required for updates")
                    # Lock the row before checking its version (PostgreSQL).
                    entity = db.query(model).filter(model.id == op.entity_id).with_for_update().one()
                    if op.base_version != entity.version:
                        db.add(SyncOperation(id=op.id, owner_id=user.id, entity_type=op.entity_type, entity_id=op.entity_id,
                            operation=op.operation, payload=op.payload, base_version=op.base_version, status='conflict'))
                        results.append({'id':op.id, 'status':'conflict', 'server_version':entity.version, 'server_payload':snapshot(entity)})
                        continue
                    # Validate the complete resulting model, not just changed fields.
                    merged = {**snapshot(entity), **op.payload}
                    schema.model_validate(merged)
                    approval = op.payload.get('review_status')
                    if approval not in {None,'approved','needs_review','incomplete'}:
                        raise ValueError("Invalid review status")
                    if approval == 'approved' and set(op.payload) != {'review_status'}:
                        raise ValueError("Approval must be a separate explicit operation")
                    for key, value in op.payload.items():
                        setattr(entity, key, value)
                    if op.entity_type in {'wall','element'} and set(op.payload) - {'review_status'}:
                        entity.review_status = 'needs_review'
                    entity.version += 1
                if op.entity_type == 'project' and entity.customer_id:
                    customer = db.get(Customer, entity.customer_id)
                    if customer is None or customer.owner_id != user.id:
                        raise ValueError("Customer not found or forbidden")
                if op.entity_type == 'element':
                    with db.no_autoflush:
                        check_element(snapshot(entity), db.get(Wall, entity.wall_id), db, exclude=entity.id)
                if op.entity_type == 'wall':
                    with db.no_autoflush:
                        for element in db.query(Element).filter(Element.wall_id == entity.id).all():
                            if element.offset_mm + element.width_mm > entity.length_mm or (element.sill_mm or 0) + (element.height_mm or 0) > entity.height_mm:
                                raise ValueError("Wall resize would place an element out of bounds")
                db.add(SyncOperation(id=op.id, owner_id=user.id, entity_type=op.entity_type, entity_id=op.entity_id,
                    operation=op.operation, payload=op.payload, base_version=op.base_version, status='applied'))
                db.flush()
                results.append({'id':op.id, 'status':'applied', 'new_version':entity.version})
            db.commit()
        except (ValueError, ValidationError, IntegrityError) as exc:
            # Savepoint rollback leaves subsequent independent operations usable.
            results.append({'id':op.id, 'status':'failed', 'error': 'Invalid operation or conflicting identifier' if isinstance(exc, IntegrityError) else str(exc)})
    db.commit()
    return {'results':results}


@router.get('/pull')
def sync_pull(since: str | None = None, entity_type: str | None = None,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # This is a receipt feed, NOT a complete change feed for REST writes.
    q = db.query(SyncOperation).filter(SyncOperation.owner_id == user.id)
    if since:
        try:
            q = q.filter(SyncOperation.created_at > datetime.fromisoformat(since.replace('Z','+00:00')))
        except ValueError:
            raise HTTPException(status_code=422, detail='Invalid timestamp')
    if entity_type:
        q = q.filter(SyncOperation.entity_type == entity_type)
    operations = q.order_by(SyncOperation.created_at, SyncOperation.id).limit(100).all()
    return {'operations':[snapshot(o) for o in operations], 'server_time':datetime.now(timezone.utc).isoformat()}


@router.get('/conflicts')
def list_conflicts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [snapshot(o) for o in db.query(SyncOperation).filter_by(owner_id=user.id, status='conflict').limit(100).all()]
