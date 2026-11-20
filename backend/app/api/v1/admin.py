from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.ai.provider import AIUnavailableError
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_admin
from app.models.db_models import AIConfig, AIUsageLog, AuditEvent, User
from app.services.audit import log_audit, serialize_audit_event
from app.services.concurrency import lock_and_verify_version, parse_if_match, resolve_expected_version, set_etag
from app.services.provider_config import encrypt_key

router = APIRouter(prefix="/admin", tags=["admin"])


class UserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    version: int | None = Field(strict=True, default=None, ge=1)
    base_version: int | None = Field(strict=True, default=None, ge=1)


@router.get("/users")
def admin_list_users(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    users = db.query(User).order_by(desc(User.created_at)).limit(100).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "is_active": u.is_active,
            "version": u.version,
            "created_at": u.created_at,
            "telegram_chat_id": u.telegram_chat_id,
        }
        for u in users
    ]


@router.put("/users/{user_id}/role")
def set_role(
    user_id: str,
    payload: UserRoleUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    expected = resolve_expected_version(
        if_match=if_match,
        version=payload.version,
        base_version=payload.base_version,
    )
    u = lock_and_verify_version(db, User, user_id, expected)
    u.role = payload.role
    u.version += 1
    db.commit()
    db.refresh(u)
    set_etag(response, u.version)
    return {"status": "updated", "role": u.role, "version": u.version}


@router.get("/ai-config")
def get_ai_config(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    configs = db.query(AIConfig).all()
    return [
        {
            "id": c.id,
            "provider": c.provider,
            "model": c.model,
            "enabled": c.enabled,
            "usage_limit_per_day": c.usage_limit_per_day,
            "has_key": bool(c.api_key_encrypted),
            "version": c.version,
        }
        for c in configs
    ]


class ProviderConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["disabled", "local", "deterministic", "openai_compatible"]
    model: str | None = Field(default=None, max_length=100)
    enabled: bool = True
    usage_limit_per_day: int | None = Field(default=None, ge=1)
    api_key: str | None = Field(default=None, min_length=1, max_length=256)
    version: int | None = Field(strict=True, default=None, ge=1)
    base_version: int | None = Field(strict=True, default=None, ge=1)


@router.put("/ai-config")
def upsert_ai_config(
    payload: ProviderConfigInput,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    encrypted = None
    if payload.api_key:
        try:
            encrypted = encrypt_key(payload.api_key)
        except AIUnavailableError:
            raise HTTPException(
                503,
                "Provider credential storage requires valid encryption configuration",
            )
    cfg = db.query(AIConfig).filter_by(provider=payload.provider).first()
    if not cfg:
        header_ver = parse_if_match(if_match)
        body_ver = payload.version if payload.version is not None else payload.base_version
        supplied = header_ver if header_ver is not None else body_ver
        if supplied is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Version conflict",
                    "expected_version": supplied,
                    "current_version": 0,
                },
            )
        cfg = AIConfig(provider=payload.provider, version=1)
        db.add(cfg)
    else:
        expected = resolve_expected_version(
            if_match=if_match,
            version=payload.version,
            base_version=payload.base_version,
        )
        cfg = lock_and_verify_version(db, AIConfig, cfg.id, expected)
        cfg.version += 1

    cfg.model = payload.model
    cfg.enabled = payload.enabled
    cfg.usage_limit_per_day = payload.usage_limit_per_day
    if encrypted:
        cfg.api_key_encrypted = encrypted
    db.commit()
    db.refresh(cfg)
    log_audit(
        db,
        user_id=admin.id,
        project_id=None,
        action="admin.ai_config_update",
        entity_type="ai_config",
        entity_id=cfg.id,
    )
    set_etag(response, cfg.version)
    return {"status": "saved", "provider": payload.provider, "version": cfg.version}


@router.get("/ai-usage")
def ai_usage(
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    logs = db.query(AIUsageLog).order_by(desc(AIUsageLog.created_at)).limit(limit).all()
    return [
        {
            "id": log_row.id,
            "user_id": log_row.user_id,
            "provider": log_row.provider,
            "model": log_row.model,
            "success": log_row.success,
            "error": log_row.error,
            "created_at": log_row.created_at,
        }
        for log_row in logs
    ]


@router.get("/audit")
@router.get("/audit-events")
def audit(
    limit: int = 100,
    offset: int = 0,
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_id: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    q = db.query(AuditEvent)
    if project_id:
        q = q.filter(AuditEvent.project_id == project_id)
    if entity_type:
        q = q.filter(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditEvent.entity_id == entity_id)
    if action:
        q = q.filter(AuditEvent.action == action)
    if actor_id:
        q = q.filter(AuditEvent.user_id == actor_id)
    events = (
        q.order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
        .offset(max(0, offset))
        .limit(min(max(1, limit), 500))
        .all()
    )
    return [serialize_audit_event(e) for e in events]


@router.get("/health")
def admin_health(admin: User = Depends(require_admin)):
    return {
        "env": settings.app_env,
        "ai_provider": settings.ai_provider,
        "database_url_scheme": settings.database_url.split(":")[0],
        "telegram_configured": bool(settings.telegram_worker_secret),
    }
