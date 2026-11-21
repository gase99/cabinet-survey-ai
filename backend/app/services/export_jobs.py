"""Background rendering for export jobs (queued -> running -> done | failed).

Approval checks and deterministic geometry run synchronously in the request, so 409/400
responses stay immediate and the rendered content is exactly the state that was
validated. Only the expensive PDF/PNG rendering runs after the response is sent. The
render specification lives in process memory: if the API process dies, the job can never
finish, so stale queued/running jobs are reported as failed (see `expire_stale_jobs`).
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.db_models import ExportJob, IdempotencyRecord, now_utc
from app.services import export_service
from app.services.audit import entity_snapshot, log_audit

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
ACTIVE_STATUSES = (QUEUED, RUNNING)
RENDER_FAILED = "Drawing rendering failed"
INTERRUPTED = "Export was interrupted (server restart or crash); request a new export"

SessionScope = Callable[[], AbstractContextManager[Session]]

_slots_lock = threading.Lock()
_slots: threading.BoundedSemaphore | None = None
_slots_size = 0


def _render_slots() -> threading.BoundedSemaphore:
    """Bound concurrent renders so large exports cannot exhaust CPU/memory."""
    global _slots, _slots_size
    size = max(1, int(settings.export_max_concurrent_jobs))
    with _slots_lock:
        if _slots is None or _slots_size != size:
            _slots, _slots_size = threading.BoundedSemaphore(size), size
        return _slots


@contextmanager
def default_session_scope() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_export_session_scope() -> SessionScope:
    """FastAPI dependency: how background jobs obtain their own database session."""
    return default_session_scope


@dataclass(frozen=True)
class RenderSpec:
    project_title: str
    customer_name: str | None
    views: list[tuple[str, str]]
    layout: str
    format: str
    notices: list[str] = field(default_factory=list)


def render(spec: RenderSpec) -> str:
    if spec.format == "pdf":
        return export_service.render_views_pdf(
            project_title=spec.project_title,
            customer_name=spec.customer_name,
            views=spec.views,
            layout=spec.layout,
            notices=spec.notices or None,
        )
    return export_service.render_views_png(
        project_title=spec.project_title,
        views=spec.views,
        layout=spec.layout,
        notices=spec.notices or None,
    )


def _audit(db: Session, job: ExportJob, action: str, detail: str) -> None:
    log_audit(
        db,
        user_id=job.owner_id,
        project_id=job.project_id,
        action=action,
        entity_type="export_job",
        entity_id=job.id,
        old_values=None,
        new_values={**entity_snapshot("export_job", job), "error_message": job.error_message},
        detail=detail,
        commit=False,
    )


def _release_idempotency(db: Session, record_id: str | None, job_id: str) -> None:
    """After a failed render the same Idempotency-Key may enqueue a fresh attempt."""
    if not record_id:
        return
    record = db.get(IdempotencyRecord, record_id)
    if record is not None and isinstance(record.response_body, dict) and record.response_body.get("id") == job_id:
        db.delete(record)


def run_export_job(job_id: str, spec: RenderSpec, idempotency_record_id: str | None, session_scope: SessionScope) -> None:
    with _render_slots(), session_scope() as db:
        job = db.get(ExportJob, job_id)
        if job is None or job.status != QUEUED:
            return
        job.status = RUNNING
        db.commit()
        try:
            path = render(spec)
        except Exception:  # noqa: BLE001 - any renderer failure is reported as job failure
            # Nothing is pending in the session here (RUNNING was committed above).
            job.status = FAILED
            job.error_message = RENDER_FAILED
            _release_idempotency(db, idempotency_record_id, job_id)
            _audit(db, job, "export.fail", f"{spec.format} {spec.layout}: {RENDER_FAILED}")
            db.commit()
            return
        job.file_path = path
        job.status = DONE
        job.error_message = None
        _audit(db, job, "export.complete", f"{spec.format} {spec.layout}")
        db.commit()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def expire_stale_jobs(db: Session, owner_id: str) -> None:
    """Mark jobs that can no longer finish (their in-memory spec is gone) as failed."""
    cutoff = now_utc() - timedelta(seconds=max(1, int(settings.export_job_stale_seconds)))
    stale = [
        job
        for job in db.query(ExportJob)
        .filter(ExportJob.owner_id == owner_id, ExportJob.status.in_(ACTIVE_STATUSES))
        .all()
        if _as_utc(job.updated_at or job.created_at) < cutoff
    ]
    for job in stale:
        job.status = FAILED
        job.error_message = INTERRUPTED
        _audit(db, job, "export.fail", INTERRUPTED)
    if stale:
        db.commit()
