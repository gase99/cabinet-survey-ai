from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, AIUsageLog
from app.core.config import settings
from app.ai.provider import get_ai_provider, AIUnavailableError, parse_text_measurements_deterministic
from datetime import datetime, timezone
import time

router = APIRouter(prefix="/ai", tags=["ai"])

@router.post("/parse-text")
async def parse_text(
    text: str = Form(...),
    language_hint: str = Form("fa,en"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start = time.time()
    try:
        result = parse_text_measurements_deterministic(text)
        # log usage
        db.add(AIUsageLog(user_id=user.id, provider="deterministic_local", success=True))
        db.commit()
        return result
    except Exception as e:
        db.add(AIUsageLog(user_id=user.id, provider="deterministic_local", success=False, error=str(e)))
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sketch-analysis")
async def sketch_analysis(
    file: UploadFile = File(...),
    language_hint: str = Form("fa,en"),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Validate file
    if file.content_type not in ["image/jpeg", "image/png", "image/webp", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPEG, PNG, or WebP.")
    data = await file.read()
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status_code=400, detail="File too large")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    provider = get_ai_provider(settings.ai_provider)
    try:
        result = await provider.analyze_sketch(data, language_hint=language_hint)
        db.add(AIUsageLog(user_id=user.id, provider=settings.ai_provider, success=True))
        db.commit()
        # Never return approved data — ensure flag
        result.setdefault("disclaimer", "AI proposals require user approval")
        return result
    except AIUnavailableError as e:
        db.add(AIUsageLog(user_id=user.id, provider=settings.ai_provider, success=False, error=str(e)))
        db.commit()
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        db.add(AIUsageLog(user_id=user.id, provider=settings.ai_provider, success=False, error=str(e)))
        db.commit()
        raise HTTPException(status_code=500, detail="AI analysis failed")

# Transcription proxy (voice -> text) — uses same deterministic if no provider
@router.post("/transcription")
async def transcription(
    file: UploadFile = File(None),
    text: str | None = Form(None),
    language_hint: str = Form("fa,en"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # If file provided, would transcribe via AI provider; for now return placeholder
    if file:
        data = await file.read()
        if len(data) > 10*1024*1024:
            raise HTTPException(status_code=400, detail="Audio file too large")
        # Mock transcription
        return {"transcript": "", "note": "Voice transcription requires configured AI provider with audio support.", "language_hint": language_hint}
    if text:
        result = parse_text_measurements_deterministic(text)
        return {"transcript": text, "extraction": result}
    raise HTTPException(status_code=400, detail="Provide audio file or text")
