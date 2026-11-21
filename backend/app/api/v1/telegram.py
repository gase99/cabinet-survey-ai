import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import ExportJob, PairingCode, TelegramDelivery, User
from app.services.audit import entity_snapshot, log_audit
from app.services.idempotency import (
    claim_idempotency,
    complete_idempotency,
    idempotency_guard,
    release_uncommitted_idempotency,
)
from app.services.tombstones import soft_delete_telegram_unlink

router = APIRouter(prefix="/telegram", tags=["telegram"])

def require_worker_secret(provided: str | None) -> None:
    configured = settings.telegram_worker_secret
    if not configured:
        raise HTTPException(status_code=503, detail="Telegram worker authentication is not configured")
    if not provided or not secrets.compare_digest(configured, provided):
        raise HTTPException(status_code=401, detail="Invalid worker secret")


def gen_code() -> str:
    # 8-char alphanumeric pairing code
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I,O,0,1
    return "".join(secrets.choice(alphabet) for _ in range(8))

@router.post("/pairing-code")
def create_pairing_code(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(PairingCode).filter(PairingCode.user_id == user.id, PairingCode.used.is_(False)).update({"used": True})
    # Generate new code with 10 min expiry
    code = gen_code()
    while db.query(PairingCode).filter(PairingCode.code == code).first():
        code = gen_code()
    pc = PairingCode(user_id=user.id, code=code, expires_at=datetime.now(UTC)+timedelta(minutes=10))
    db.add(pc)
    db.commit()
    log_audit(db, user_id=user.id, project_id=None, action="telegram.pairing_code_created", entity_type="pairing_code", entity_id=pc.id)
    return {"code": code, "expires_at": pc.expires_at, "note": "Share this code with the Telegram bot via /pair CODE"}

@router.post("/verify-pairing")
def verify_pairing(payload: dict, db: Session = Depends(get_db), x_webhook_secret: str | None = Header(default=None)):
    """
    Called by Telegram bot worker after user sends /pair CODE in Telegram.
    Secured via the independent worker credential.
    Payload: {code, telegram_chat_id, telegram_username}
    """
    require_worker_secret(x_webhook_secret)
    code = payload.get("code")
    chat_id = payload.get("telegram_chat_id")
    username = payload.get("telegram_username")
    if not code or not chat_id:
        raise HTTPException(status_code=400, detail="code and telegram_chat_id required")
    pc = db.query(PairingCode).filter(PairingCode.code == code.upper()).with_for_update().populate_existing().first()
    if not pc:
        raise HTTPException(status_code=404, detail="Invalid pairing code")
    if pc.used:
        raise HTTPException(status_code=400, detail="Pairing code already used")
    # SQLite returns naive timestamps; canonical storage is UTC.
    expiry = pc.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Pairing code expired")
    user = db.get(User, pc.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.telegram_chat_id = str(chat_id)
    user.telegram_username = username
    user.version += 1
    pc.telegram_chat_id = str(chat_id)
    pc.used = True
    pc.version += 1
    db.commit()
    log_audit(
        db,
        user_id=user.id,
        project_id=None,
        action="telegram.linked",
        entity_type="telegram_link",
        entity_id=pc.id,
        old_values={"linked": False},
        new_values=entity_snapshot("telegram_link", pc),
    )
    return {"status": "linked", "user_id": user.id, "telegram_chat_id": chat_id}

@router.get("/link-status")
def link_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"telegram_chat_id": user.telegram_chat_id, "telegram_username": user.telegram_username, "linked": bool(user.telegram_chat_id)}

@router.delete("/unlink")
def unlink(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = soft_delete_telegram_unlink(db, user=user)
    db.commit()
    return result

@router.post("/send")
def send_via_telegram(
    payload: dict,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Queue delivery of an approved export job to the user's linked Telegram chat.
    The independent single-replica worker (`services/telegram-bot`) owns the bot
    token and sends documents asynchronously; this API only queues delivery.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Invalid JSON payload")
    with idempotency_guard(owner_id=user.id, scope="telegram.send", key=idempotency_key):
        replay, claimed_record = claim_idempotency(
            db,
            owner_id=user.id,
            scope="telegram.send",
            key=idempotency_key,
            canonical_payload=payload,
        )
        if replay is not None:
            return replay

        try:
            if not user.telegram_chat_id:
                raise HTTPException(
                    status_code=400,
                    detail="Telegram not linked. Create pairing code first.",
                )
            export_id = payload.get("export_job_id")
            if not export_id:
                raise HTTPException(status_code=400, detail="export_job_id required")
            job = db.get(ExportJob, export_id)
            if not job or job.owner_id != user.id:
                raise HTTPException(status_code=404, detail="Export not found")
            if job.status != "done":
                raise HTTPException(status_code=400, detail="Export not ready")
            delivery = TelegramDelivery(
                owner_id=user.id,
                project_id=job.project_id,
                export_job_id=job.id,
                chat_id=user.telegram_chat_id,
                status="pending",
            )
            db.add(delivery)
            db.flush()

            response_body = {"status": "queued", "delivery_id": delivery.id}
            complete_idempotency(
                db,
                record=claimed_record,
                status_code=200,
                response_body=response_body,
            )
            log_audit(
                db,
                user_id=user.id,
                project_id=job.project_id,
                action="telegram.deliver_queued",
                entity_type="telegram_delivery",
                entity_id=delivery.id,
                old_values=None,
                new_values=entity_snapshot("telegram_delivery", delivery),
                commit=False,
            )
            db.commit()
            db.refresh(delivery)
            return response_body
        except BaseException:
            release_uncommitted_idempotency(db, claimed_record)
            raise

@router.get("/deliveries")
def list_deliveries(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(TelegramDelivery).filter(TelegramDelivery.owner_id == user.id)
    if not include_deleted:
        q = q.filter(TelegramDelivery.is_deleted.is_(False))
    deliveries = q.order_by(TelegramDelivery.created_at.desc()).limit(50).all()
    return [
        {
            "id": d.id,
            "status": d.status,
            "chat_id": d.chat_id,
            "message_id": d.message_id,
            "error": d.error,
            "version": d.version,
            "is_deleted": d.is_deleted,
            "deleted_at": d.deleted_at,
            "created_at": d.created_at,
            "export_job_id": d.export_job_id,
            "project_id": d.project_id,
        }
        for d in deliveries
    ]

# Inactive legacy route: Telegram Bot API webhooks must target services/telegram-bot (/telegram/webhook)
@router.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db), x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    """
    Intentionally disabled (`501`, blocked with `404` at the gateway).
    Telegram webhook ingress is handled exclusively by `services/telegram-bot`.
    """
    require_worker_secret(x_telegram_bot_api_secret_token)
    raise HTTPException(status_code=501, detail="Configure Telegram webhook on the independent worker service")

# Internal worker polling endpoint: pending deliveries
@router.get("/internal/pending-deliveries")
def pending_deliveries(x_webhook_secret: str | None = Header(default=None), db: Session = Depends(get_db)):
    # Secured by the API/worker shared credential
    require_worker_secret(x_webhook_secret)
    pendings = db.query(TelegramDelivery).filter(TelegramDelivery.status == "pending").limit(20).all()
    result = []
    for d in pendings:
        job = db.get(ExportJob, d.export_job_id) if d.export_job_id else None
        result.append({
            "delivery_id": d.id,
            "chat_id": d.chat_id,
            "file_path": job.file_path if job else None,
            "format": job.format if job else None,
            "project_id": d.project_id,
        })
    return result

@router.post("/internal/delivery-result")
def delivery_result(payload: dict, db: Session = Depends(get_db), x_webhook_secret: str | None = Header(default=None)):
    require_worker_secret(x_webhook_secret)
    delivery_id = payload.get("delivery_id")
    status = payload.get("status")  # sent | failed
    if status not in {"sent", "failed"}:
        raise HTTPException(status_code=422, detail="status must be sent or failed")
    message_id = payload.get("message_id")
    error = payload.get("error")
    d = db.get(TelegramDelivery, delivery_id)
    if not d:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if d.status in {"sent", "failed", "cancelled"}:
        if d.status == status and d.message_id == (str(message_id) if message_id else None):
            return {"status": "updated"}
        raise HTTPException(409, "Terminal delivery status cannot be overwritten")
    d.status = status
    d.message_id = str(message_id) if message_id else None
    d.error = error
    db.commit()
    return {"status": "updated"}


@router.get("/internal/deliveries/{delivery_id}")
def internal_delivery_status(delivery_id: str, db: Session = Depends(get_db),
                             x_webhook_secret: str | None = Header(default=None)):
    require_worker_secret(x_webhook_secret)
    delivery=db.get(TelegramDelivery,delivery_id)
    if delivery is None:
        raise HTTPException(404,"Delivery not found")
    return {"delivery_id":delivery.id,"status":delivery.status}
