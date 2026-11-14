from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.database import get_db
from app.core.deps import require_admin
from app.models.db_models import User, AIConfig, AIUsageLog, AuditEvent
from app.core.config import settings
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from app.services.provider_config import encrypt_key
from app.ai.provider import AIUnavailableError
from app.services.audit import log_audit

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/users")
def admin_list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    users = db.query(User).order_by(desc(User.created_at)).limit(100).all()
    return [{"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role, "is_active": u.is_active, "created_at": u.created_at, "telegram_chat_id": u.telegram_chat_id} for u in users]

@router.put("/users/{user_id}/role")
def set_role(user_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    role = payload.get("role")
    if role not in ("user","admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.role = role
    db.commit()
    return {"status": "updated", "role": role}

@router.get("/ai-config")
def get_ai_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    configs = db.query(AIConfig).all()
    # Do not return raw key
    return [{"id": c.id, "provider": c.provider, "model": c.model, "enabled": c.enabled, "usage_limit_per_day": c.usage_limit_per_day, "has_key": bool(c.api_key_encrypted)} for c in configs]

class ProviderConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["disabled", "local", "deterministic", "openai_compatible"]
    model: str | None = Field(default=None,max_length=100)
    enabled: bool = True
    usage_limit_per_day: int | None = Field(default=None,ge=1)
    api_key: str | None = Field(default=None,min_length=1,max_length=256)


@router.put("/ai-config")
def upsert_ai_config(payload: ProviderConfigInput, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    # Validate/encrypt before changing the ORM object. No successful fake key save.
    encrypted = None
    if payload.api_key:
        try:
            encrypted = encrypt_key(payload.api_key)
        except AIUnavailableError:
            raise HTTPException(503, "Provider credential storage requires valid encryption configuration")
    cfg = db.query(AIConfig).filter_by(provider=payload.provider).first()
    if not cfg:
        cfg = AIConfig(provider=payload.provider)
        db.add(cfg)
    cfg.model = payload.model
    cfg.enabled = payload.enabled
    cfg.usage_limit_per_day = payload.usage_limit_per_day
    if encrypted:
        cfg.api_key_encrypted = encrypted
    db.commit()
    log_audit(db,user_id=admin.id,project_id=None,action="admin.ai_config_update",entity_type="ai_config",entity_id=cfg.id)
    return {"status":"saved","provider":payload.provider}

@router.get("/ai-usage")
def ai_usage(limit: int = 50, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    logs = db.query(AIUsageLog).order_by(desc(AIUsageLog.created_at)).limit(limit).all()
    return [{"id": l.id, "user_id": l.user_id, "provider": l.provider, "model": l.model, "success": l.success, "error": l.error, "created_at": l.created_at} for l in logs]

@router.get("/audit")
def audit(limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    events = db.query(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(limit).all()
    return [{"id": e.id, "action": e.action, "user_id": e.user_id, "project_id": e.project_id, "entity_type": e.entity_type, "entity_id": e.entity_id, "detail": e.detail, "created_at": e.created_at} for e in events]

@router.get("/health")
def admin_health(admin: User = Depends(require_admin)):
    return {
        "env": settings.app_env,
        "ai_provider": settings.ai_provider,
        "database_url_scheme": settings.database_url.split(":")[0],
        "telegram_configured": bool(settings.telegram_bot_token),
    }
