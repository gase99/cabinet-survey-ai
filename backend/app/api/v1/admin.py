from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.database import get_db
from app.core.deps import require_admin
from app.models.db_models import User, AIConfig, AIUsageLog, AuditEvent
from app.core.config import settings

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

@router.put("/ai-config")
def upsert_ai_config(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    provider = payload.get("provider")
    if not provider:
        raise HTTPException(status_code=400, detail="provider required")
    cfg = db.query(AIConfig).filter(AIConfig.provider == provider).first()
    if not cfg:
        cfg = AIConfig(provider=provider)
        db.add(cfg)
    cfg.model = payload.get("model")
    cfg.enabled = payload.get("enabled", True)
    cfg.usage_limit_per_day = payload.get("usage_limit_per_day")
    if payload.get("api_key"):
        # In production, encrypt at rest; here store as is but flagged
        cfg.api_key_encrypted = payload["api_key"][:4] + "***"  # don't store raw in demo; real would encrypt
        # We also update settings in memory for demo (restart would reload from DB/env)
    db.commit()
    return {"status": "saved", "provider": provider}

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
