import hashlib

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.ai import speech
from app.ai.provider import AIUnavailableError, parse_measurements_any
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.throttle import ai_rate_limit
from app.models.db_models import AIUsageLog, Observation, User
from app.services.audit import entity_snapshot, log_audit
from app.services.provenance import (
    persist_ai_candidates,
    serialize_observation,
    validate_optional_provenance_refs,
)
from app.services.provider_config import configured_provider
from app.services.uploads import validated_audio_upload, validated_upload

router = APIRouter(prefix="/ai", tags=["ai"])

TEXT_PROMPT_ID = "deterministic_text_v1"
SKETCH_PROMPT_ID = "sketch_vision_v1"
VOICE_PROMPT_ID = "stt_transcription_v1"


@router.post("/parse-text")
async def parse_text(
    text: str = Form(...),
    language_hint: str = Form("fa,en"),
    project_id: str | None = Form(None),
    asset_id: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(ai_rate_limit),
):
    project_id, asset_id = validate_optional_provenance_refs(
        db, user_id=user.id, project_id=project_id, asset_id=asset_id
    )
    try:
        result = parse_measurements_any(text)
        result["observations"] = persist_ai_candidates(
            db,
            user_id=user.id,
            project_id=project_id,
            source_type="text_ai",
            source_asset_id=asset_id,
            source_image_sha256=None,
            prompt_id=TEXT_PROMPT_ID,
            provider_name="deterministic_local",
            model_name="deterministic_parser_v1",
            observations=result.get("observations", []),
        )
        db.add(
            AIUsageLog(
                user_id=user.id,
                provider="deterministic_local",
                model="deterministic_parser_v1",
                success=True,
            )
        )
        db.commit()
        return result
    except HTTPException:
        raise
    except (ValueError, RuntimeError, TypeError) as e:
        db.add(
            AIUsageLog(
                user_id=user.id,
                provider="deterministic_local",
                model="deterministic_parser_v1",
                success=False,
                error=str(e),
            )
        )
        db.commit()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/sketch-analysis")
async def sketch_analysis(
    file: UploadFile = File(...),
    language_hint: str = Form("fa,en"),
    notes: str | None = Form(None),
    project_id: str | None = Form(None),
    asset_id: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(ai_rate_limit),
):
    project_id, asset_id = validate_optional_provenance_refs(
        db, user_id=user.id, project_id=project_id, asset_id=asset_id
    )
    data, _ = await validated_upload(file, images_only=True)
    image_digest = hashlib.sha256(data).hexdigest()

    try:
        provider = configured_provider(db)
        provider_name = getattr(provider, "provider_name", None) or settings.ai_provider
        model_name = (
            getattr(provider, "model", None)
            or settings.ai_model
            or provider.__class__.__name__
        )
        result = await provider.analyze_sketch(data, language_hint=language_hint)
        result["observations"] = persist_ai_candidates(
            db,
            user_id=user.id,
            project_id=project_id,
            source_type="sketch_ai",
            source_asset_id=asset_id,
            source_image_sha256=image_digest,
            prompt_id=SKETCH_PROMPT_ID,
            provider_name=str(provider_name),
            model_name=str(model_name),
            observations=result.get("observations", []),
        )
        db.add(
            AIUsageLog(
                user_id=user.id,
                provider=str(provider_name),
                model=str(model_name),
                success=True,
            )
        )
        db.commit()
        # Never return approved data — ensure flag
        result.setdefault("disclaimer", "AI proposals require user approval")
        return result
    except AIUnavailableError as e:
        db.add(
            AIUsageLog(
                user_id=user.id,
                provider=settings.ai_provider,
                model=settings.ai_model,
                success=False,
                error=str(e),
            )
        )
        db.commit()
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except (httpx.HTTPError, OSError, ValueError, RuntimeError, TypeError) as e:
        db.add(
            AIUsageLog(
                user_id=user.id,
                provider=settings.ai_provider,
                model=settings.ai_model,
                success=False,
                error=str(e),
            )
        )
        db.commit()
        raise HTTPException(status_code=500, detail="AI analysis failed") from e


# Transcription proxy (voice -> text). Speech recognition is provider-neutral and
# fail-closed: without configured credentials audio returns 503 and typed text
# remains available. A transcript only ever yields proposals, never approvals.
@router.post("/transcription")
async def transcription(
    file: UploadFile = File(None),
    text: str | None = Form(None),
    language_hint: str = Form("fa,en"),
    project_id: str | None = Form(None),
    asset_id: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(ai_rate_limit),
):
    project_id, asset_id = validate_optional_provenance_refs(
        db, user_id=user.id, project_id=project_id, asset_id=asset_id
    )
    if file is not None:
        data, mime = await validated_audio_upload(file)
        audio_digest = hashlib.sha256(data).hexdigest()
        try:
            provider = speech.get_stt_provider()
            transcript = await provider.transcribe(data, mime, language_hint=language_hint)
        except speech.STTUnavailableError as e:
            db.add(
                AIUsageLog(
                    user_id=user.id,
                    provider=settings.stt_provider,
                    model=settings.stt_model,
                    success=False,
                    error=str(e),
                )
            )
            db.commit()
            raise HTTPException(status_code=503, detail=str(e))
        result = parse_measurements_any(transcript)
        model_name = settings.stt_model or provider.__class__.__name__
        result["observations"] = persist_ai_candidates(
            db,
            user_id=user.id,
            project_id=project_id,
            source_type="voice_ai",
            source_asset_id=asset_id,
            source_image_sha256=audio_digest,
            prompt_id=VOICE_PROMPT_ID,
            provider_name=settings.stt_provider,
            model_name=str(model_name),
            observations=result.get("observations", []),
        )
        db.add(
            AIUsageLog(
                user_id=user.id,
                provider=settings.stt_provider,
                model=str(model_name),
                success=True,
            )
        )
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
        result["observations"] = persist_ai_candidates(
            db,
            user_id=user.id,
            project_id=project_id,
            source_type="voice_ai",
            source_asset_id=asset_id,
            source_image_sha256=None,
            prompt_id=VOICE_PROMPT_ID,
            provider_name="deterministic_local",
            model_name="deterministic_parser_v1",
            observations=result.get("observations", []),
        )
        db.commit()
        return {"transcript": text, "extraction": result, "external_transmission": False}
    raise HTTPException(status_code=400, detail="Provide audio file or text")


@router.get("/candidates")
def list_ai_candidates(
    project_id: str | None = None,
    review_status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Observation).filter(Observation.owner_id == user.id)
    if project_id:
        q = q.filter(Observation.project_id == project_id)
    if review_status:
        q = q.filter(Observation.review_status == review_status)
    rows = (
        q.order_by(Observation.created_at.desc(), Observation.id.desc())
        .limit(min(max(1, limit), 200))
        .all()
    )
    return [serialize_observation(obs) for obs in rows]


@router.get("/candidates/{candidate_id}")
def get_ai_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obs = db.get(Observation, candidate_id)
    if obs is None or obs.owner_id != user.id:
        raise HTTPException(status_code=404, detail="AI candidate not found")
    return serialize_observation(obs)


@router.post("/candidates/{candidate_id}/reject")
def reject_ai_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obs = db.get(Observation, candidate_id)
    if obs is None or obs.owner_id != user.id:
        raise HTTPException(status_code=404, detail="AI candidate not found")
    old_snap = entity_snapshot("observation", obs)
    obs.review_status = "rejected"
    log_audit(
        db,
        user_id=user.id,
        project_id=obs.project_id,
        action="ai_candidate.reject",
        entity_type="observation",
        entity_id=obs.id,
        old_values=old_snap,
        new_values=entity_snapshot("observation", obs),
        commit=False,
    )
    db.commit()
    return serialize_observation(obs)
