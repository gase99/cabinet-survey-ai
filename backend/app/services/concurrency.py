"""Optimistic concurrency enforcement (version / base_version / If-Match) for REST PUT endpoints."""
from typing import TypeVar
from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

T = TypeVar("T")


def parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    token = if_match.strip()
    if not token:
        raise HTTPException(
            status_code=422,
            detail="Invalid If-Match header; expected positive integer version",
        )
    if token.startswith("W/"):
        token = token[2:].strip()
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        token = token[1:-1].strip()
    if not token.isdigit():
        raise HTTPException(
            status_code=422,
            detail="Invalid If-Match header; expected positive integer version",
        )
    value = int(token)
    if value < 1:
        raise HTTPException(
            status_code=422,
            detail="Invalid If-Match header; version must be >= 1",
        )
    return value


def resolve_expected_version(
    *,
    if_match: str | None = None,
    version: int | None = None,
    base_version: int | None = None,
) -> int:
    header_ver = parse_if_match(if_match)
    if version is not None and base_version is not None and version != base_version:
        raise HTTPException(
            status_code=422,
            detail="Conflicting version and base_version values",
        )
    body_ver = version if version is not None else base_version
    if header_ver is not None and body_ver is not None and header_ver != body_ver:
        raise HTTPException(
            status_code=422,
            detail="Conflicting version and If-Match values",
        )
    expected = header_ver if header_ver is not None else body_ver
    if expected is None:
        raise HTTPException(
            status_code=422,
            detail="Optimistic concurrency requires version (or base_version) or If-Match header",
        )
    return expected


def lock_and_verify_version(
    db: Session,
    model: type[T],
    entity_id: str,
    expected_version: int,
) -> T:
    entity = (
        db.query(model)
        .filter(model.id == entity_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    if getattr(entity, "is_deleted", False):
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    if entity.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Version conflict",
                "expected_version": expected_version,
                "current_version": entity.version,
            },
        )
    return entity


def set_etag(response: Response | None, version: int) -> None:
    if response is not None:
        response.headers["ETag"] = f'"{version}"'
