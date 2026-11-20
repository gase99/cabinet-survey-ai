"""Shared-database request quotas (survive multi-worker deploys without Redis)."""
import hashlib
import time
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import AuthThrottle, User


def _increment_bucket(db: Session, raw_key: str, bucket: int) -> int:
    key = hashlib.sha256(raw_key.encode()).hexdigest()
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    query = insert(AuthThrottle).values(key=key, bucket=bucket, attempts=1)
    query = query.on_conflict_do_update(
        index_elements=["key"],
        set_={"attempts": AuthThrottle.attempts + 1},
    ).returning(AuthThrottle.attempts)
    count = db.execute(query).scalar_one()
    db.execute(delete(AuthThrottle).where(AuthThrottle.bucket < bucket - 2))
    db.commit()
    return int(count)


def auth_rate_limit(request: Request, db: Session = Depends(get_db)):
    """Keep authentication attempts bounded across processes via the primary DB."""
    now = int(time.time())
    bucket = now // 60
    address = request.client.host if request.client else "unknown"
    count = _increment_bucket(db, f"{address}|{request.url.path}|{bucket}", bucket)
    if count > settings.rate_limit_auth_per_minute:
        retry_after = max(1, 60 - (now % 60))
        raise HTTPException(
            status_code=429,
            detail="Authentication request limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def ai_rate_limit(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Enforce per-user rate_limit_ai_per_minute across all AI endpoints."""
    now = int(time.time())
    bucket = now // 60
    retry_after = max(1, 60 - (now % 60))
    if settings.rate_limit_ai_per_minute <= 0:
        raise HTTPException(
            status_code=429,
            detail="AI request limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    count = _increment_bucket(db, f"ai|{user.id}|{bucket}", bucket)
    if count > settings.rate_limit_ai_per_minute:
        raise HTTPException(
            status_code=429,
            detail="AI request limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    return user
