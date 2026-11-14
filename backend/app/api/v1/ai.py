from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, AIUsageLog
from app.core.config import settings
from app.ai.provider import get_ai_provider, AIUnavailableError, parse_measurements_any
from app.ai import speech
from datetime import datetime, timezone
import time
from app.services.uploads import validated_upload, validated_audio_upload
from app.services.provider_config import configured_provider

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
        result = parse_measurements_any(text)
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
    data, _ = await validated_upload(file, images_only=True)

    try:
        provider = configured_provider(db)
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

# Transcription proxy (voice -> text). Speech recognition is provider-neutral and
# fail-closed: without configured credentials audio returns 503 and typed text
# remains available. A transcript only ever yields proposals, never approvals.
@router.post("/transcription")
async def transcription(
    file: UploadFile = File(None),
    text: str | None = Form(None),
    language_hint: str = Form("fa,en"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file is not None:
        data, mime = await validated_audio_upload(file)
        try:
            provider = speech.get_stt_provider()
            transcript = await provider.transcribe(data, mime, language_hint=language_hint)
        except speech.STTUnavailableError as e:
            db.add(AIUsageLog(user_id=user.id, provider=settings.stt_provider, success=False, error=str(e)))
            db.commit()
            raise HTTPException(status_code=503, detail=str(e))
        result = parse_measurements_any(transcript)
        db.add(AIUsageLog(user_id=user.id, provider=settings.stt_provider, success=True))
        db.commit()
        return {
            "transcript": transcript,
            "extraction": result,
            "external_transmission": True,
            "notice": "Audio was transmitted to the configured external speech recognition service. "
                      "Every extracted value below is a proposal and requires your explicit approval.",
        }
    if text:
        result = parse_measurements_any(text)
        return {"transcript": text, "extraction": result, "external_transmission": False}
    raise HTTPException(status_code=400, detail="Provide audio file or text")
