"""Idempotency-Key persistence and payload verification for export and Telegram delivery."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.db_models import IdempotencyRecord, now_utc


def validate_idempotency_key(key: str | None) -> str | None:
    if key is None:
        return None
    cleaned = key.strip()
    if not cleaned or len(cleaned) > 255 or any(ord(c) < 32 for c in cleaned):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be a non-empty printable string up to 255 characters",
        )
    return cleaned


def compute_request_hash(canonical_payload: dict[str, Any]) -> str:
    encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def check_idempotency(
    db: Session,
    *,
    owner_id: str,
    scope: str,
    key: str | None,
    canonical_payload: dict[str, Any],
) -> tuple[JSONResponse | None, str | None, IdempotencyRecord | None]:
    cleaned_key = validate_idempotency_key(key)
    if cleaned_key is None:
        return None, None, None

    req_hash = compute_request_hash(canonical_payload)
    record = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.owner_id == owner_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == cleaned_key,
        )
        .with_for_update()
        .populate_existing()
        .first()
    )
    if record is None:
        return None, req_hash, None

    if _as_utc(record.expires_at) <= now_utc():
        # Expired key: allow fresh execution and overwrite record in place on success.
        return None, req_hash, record

    if record.request_hash != req_hash:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key was already used with a different request body",
        )

    return JSONResponse(status_code=record.status_code, content=record.response_body), req_hash, record


def store_idempotency_result(
    db: Session,
    *,
    owner_id: str,
    scope: str,
    key: str | None,
    request_hash: str | None,
    status_code: int,
    response_body: dict[str, Any],
    existing_expired: IdempotencyRecord | None = None,
) -> IdempotencyRecord | None:
    cleaned_key = validate_idempotency_key(key)
    if cleaned_key is None or request_hash is None:
        return None

    now = now_utc()
    ttl = max(1, int(settings.idempotency_ttl_seconds))
    expires_at = now + timedelta(seconds=ttl)

    if existing_expired is not None:
        existing_expired.request_hash = request_hash
        existing_expired.status_code = status_code
        existing_expired.response_body = response_body
        existing_expired.created_at = now
        existing_expired.expires_at = expires_at
        db.flush()
        return existing_expired

    record = IdempotencyRecord(
        owner_id=owner_id,
        scope=scope,
        idempotency_key=cleaned_key,
        request_hash=request_hash,
        status_code=status_code,
        response_body=response_body,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    return record
