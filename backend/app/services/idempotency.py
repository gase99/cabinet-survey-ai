"""Atomic Idempotency-Key reservation, locking, and payload verification."""

import hashlib
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.db_models import IdempotencyRecord, gen_id, now_utc

_GUARD_REGISTRY_LOCK = threading.Lock()
_KEY_LOCKS: dict[tuple[str, str, str], threading.RLock] = {}


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
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def _key_lock(owner_id: str, scope: str, cleaned_key: str) -> threading.RLock:
    slot = (owner_id, scope, cleaned_key)
    with _GUARD_REGISTRY_LOCK:
        lock = _KEY_LOCKS.get(slot)
        if lock is None:
            if len(_KEY_LOCKS) > 4096:
                _KEY_LOCKS.clear()
            lock = threading.RLock()
            _KEY_LOCKS[slot] = lock
        return lock


@contextmanager
def idempotency_guard(
    *,
    owner_id: str,
    scope: str,
    key: str | None,
) -> Iterator[str | None]:
    cleaned_key = validate_idempotency_key(key)
    if cleaned_key is None:
        yield None
        return
    lock = _key_lock(owner_id, scope, cleaned_key)
    with lock:
        yield cleaned_key


def _insert_reservation(
    db: Session,
    *,
    owner_id: str,
    scope: str,
    cleaned_key: str,
    request_hash: str,
    now: datetime,
    expires_at: datetime,
) -> str | None:
    candidate_id = gen_id()
    values = {
        "id": candidate_id,
        "owner_id": owner_id,
        "scope": scope,
        "idempotency_key": cleaned_key,
        "request_hash": request_hash,
        "status_code": 0,
        "response_body": {"_pending": True},
        "created_at": now,
        "expires_at": expires_at,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        pg_stmt = (
            pg_insert(IdempotencyRecord)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["owner_id", "scope", "idempotency_key"],
            )
            .returning(IdempotencyRecord.id)
        )
        inserted = db.execute(pg_stmt).scalar_one_or_none()
    else:
        sq_stmt = (
            sqlite_insert(IdempotencyRecord)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["owner_id", "scope", "idempotency_key"],
            )
            .returning(IdempotencyRecord.id)
        )
        inserted = db.execute(sq_stmt).scalar_one_or_none()
    return str(inserted) if inserted is not None else None


def claim_idempotency(
    db: Session,
    *,
    owner_id: str,
    scope: str,
    key: str | None,
    canonical_payload: dict[str, Any],
) -> tuple[JSONResponse | None, IdempotencyRecord | None]:
    """Atomically reserve `(owner_id, scope, key)` or replay an existing result.

    Across PostgreSQL workers, `INSERT ... ON CONFLICT DO NOTHING` acquires an
    exclusive transaction lock on the `(owner_id, scope, idempotency_key)` unique
    index entry so concurrent requests block until the winner commits and then
    replay the single committed result without creating duplicate jobs.
    """
    cleaned_key = validate_idempotency_key(key)
    if cleaned_key is None:
        return None, None

    req_hash = compute_request_hash(canonical_payload)
    ttl = max(1, int(settings.idempotency_ttl_seconds))

    for _ in range(3):
        now = now_utc()
        expires_at = now + timedelta(seconds=ttl)
        inserted_id = _insert_reservation(
            db,
            owner_id=owner_id,
            scope=scope,
            cleaned_key=cleaned_key,
            request_hash=req_hash,
            now=now,
            expires_at=expires_at,
        )
        if inserted_id is not None:
            claimed = db.get(IdempotencyRecord, inserted_id)
            return None, claimed

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
            # Winner rolled back between conflict check and row fetch; retry reservation.
            continue

        current_now = now_utc()
        if _as_utc(record.expires_at) <= current_now:
            record.request_hash = req_hash
            record.status_code = 0
            record.response_body = {"_pending": True}
            record.created_at = current_now
            record.expires_at = current_now + timedelta(seconds=ttl)
            db.flush()
            return None, record

        if record.request_hash != req_hash:
            raise HTTPException(
                status_code=422,
                detail="Idempotency-Key was already used with a different request body",
            )

        return JSONResponse(status_code=record.status_code, content=record.response_body), record

    raise HTTPException(status_code=409, detail="Concurrent idempotent request conflict; retry")


def complete_idempotency(
    db: Session,
    *,
    record: IdempotencyRecord | None,
    status_code: int,
    response_body: dict[str, Any],
) -> IdempotencyRecord | None:
    if record is None:
        return None
    now = now_utc()
    ttl = max(1, int(settings.idempotency_ttl_seconds))
    record.status_code = status_code
    record.response_body = response_body
    record.created_at = now
    record.expires_at = now + timedelta(seconds=ttl)
    db.flush()
    return record


def release_uncommitted_idempotency(
    db: Session,
    record: IdempotencyRecord | None,
) -> None:
    if record is not None and record.status_code == 0:
        db.delete(record)
        db.flush()
