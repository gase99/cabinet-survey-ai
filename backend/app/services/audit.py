from sqlalchemy.orm import Session
from app.models.db_models import AuditEvent

def log_audit(db: Session, *, user_id: str | None, project_id: str | None, action: str, entity_type: str | None = None, entity_id: str | None = None, detail: str | None = None):
    ev = AuditEvent(
        user_id=user_id,
        project_id=project_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )
    db.add(ev)
    db.commit()
