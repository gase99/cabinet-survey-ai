"""Shared-database request quotas (survive multi-worker deploys without Redis)."""

import hashlib
import time
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import AuthThrottle, User

AI_WINDOW_SECONDS = 60


def _increment_bucket(db: Session, raw_key: str, bucket: int) -> int:
    key = hashlib.sha256(raw_key.encode()).hexdigest()
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        pg_query = (
            pg_insert(AuthThrottle)
            .values(key=key, bucket=bucket, attempts=1)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"attempts": AuthThrottle.attempts + 1},
            )
            .returning(AuthThrottle.attempts)
        )
        count = db.execute(pg_query).scalar_one()
    else:
        sq_query = (
            sqlite_insert(AuthThrottle)
            .values(key=key, bucket=bucket, attempts=1)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"attempts": AuthThrottle.attempts + 1},
            )
            .returning(AuthThrottle.attempts)
        )
        count = db.execute(sq_query).scalar_one()
    db.execute(
        delete(AuthThrottle).where(
            ~AuthThrottle.key.like("aie:%"),
            AuthThrottle.bucket < bucket - 2,
        )
    )
    db.commit()
    return int(count)


def auth_rate_limit(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
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
    """Enforce per-user rate_limit_ai_per_minute over a true 60-second sliding window."""
    now = int(time.time())
    if settings.rate_limit_ai_per_minute <= 0:
        raise HTTPException(
            status_code=429,
            detail="AI request limit exceeded",
            headers={"Retry-After": str(AI_WINDOW_SECONDS)},
        )

    # Per-user row lock prevents concurrent AI requests for the same user from racing.
    db.query(User).filter(User.id == user.id).with_for_update().one()

    prefix = f"aie:{hashlib.sha256(user.id.encode()).hexdigest()[:24]}:"
    cutoff = now - AI_WINDOW_SECONDS
    db.execute(
        delete(AuthThrottle).where(
            AuthThrottle.key.like(f"{prefix}%"),
            AuthThrottle.bucket <= cutoff,
        )
    )
    active_buckets = [
        row.bucket
        for row in db.query(AuthThrottle)
        .filter(
            AuthThrottle.key.like(f"{prefix}%"),
            AuthThrottle.bucket > cutoff,
        )
        .all()
    ]
    if len(active_buckets) >= settings.rate_limit_ai_per_minute:
        oldest = min(active_buckets)
        retry_after = max(1, (oldest + AI_WINDOW_SECONDS) - now)
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="AI request limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    db.add(AuthThrottle(key=f"{prefix}{uuid.uuid4().hex}", bucket=now, attempts=1))
    db.commit()
    return user
