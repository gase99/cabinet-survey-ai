"""AI candidate provenance persistence and strict separation from approved measurements."""
from typing import Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.db_models import Asset, Observation, Project


def validate_optional_provenance_refs(
    db: Session,
    *,
    user_id: str,
    project_id: str | None = None,
    asset_id: str | None = None,
) -> tuple[str | None, str | None]:
    if project_id:
        project = db.get(Project, project_id)
        if not project or project.owner_id != user_id or project.is_deleted:
            raise HTTPException(status_code=404, detail="Project not found")
    if asset_id:
        asset = db.get(Asset, asset_id)
        if not asset or asset.owner_id != user_id:
            raise HTTPException(status_code=404, detail="Asset not found")
        if project_id and asset.project_id and asset.project_id != project_id:
            raise HTTPException(status_code=400, detail="Asset belongs to a different project")
        if not project_id and asset.project_id:
            project_id = asset.project_id
    return project_id, asset_id


def persist_ai_candidates(
    db: Session,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_asset_id: str | None,
    source_image_sha256: str | None,
    prompt_id: str,
    provider_name: str,
    model_name: str,
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist each AI candidate in observations with review_status='needs_review'.

    Confidence never approves an AI candidate or any measurement.
    """
    enriched: list[dict[str, Any]] = []
    for raw in observations:
        bbox = raw.get("source_bbox")
        span = raw.get("span")
        region: dict[str, Any] = {}
        if bbox is not None:
            region["bbox"] = bbox
        if span is not None:
            region["span"] = span
        if raw.get("source_text") is not None:
            region["source_text"] = raw.get("source_text")
        if raw.get("kind") is not None:
            region["kind"] = raw.get("kind")
        if raw.get("intent") is not None:
            region["intent"] = raw.get("intent")

        conf = raw.get("confidence")
        obs_row = Observation(
            owner_id=user_id,
            project_id=project_id,
            source_type=source_type,
            raw_value=raw.get("source_text"),
            normalized_value_mm=raw.get("value_mm"),
            label=raw.get("label") or raw.get("kind"),
            confidence=float(conf) if conf is not None else None,
            source_asset_id=source_asset_id,
            source_image_sha256=source_image_sha256,
            source_region=region or None,
            prompt_id=prompt_id,
            provider=provider_name,
            model_name=model_name,
            # Hard safety rule: AI output never enters approved state regardless of confidence.
            review_status="needs_review",
            clarification=raw.get("uncertainty"),
        )
        db.add(obs_row)
        db.flush()

        item = dict(raw)
        item["candidate_id"] = obs_row.id
        item["source_type"] = source_type
        item["source_asset_id"] = source_asset_id
        item["source_image_sha256"] = source_image_sha256
        item["prompt_id"] = prompt_id
        item["provider"] = provider_name
        item["model_name"] = model_name
        item["review_status"] = "needs_review"
        item["needs_review"] = True
        item.pop("approved", None)
        enriched.append(item)
    return enriched


def bind_observation_to_measurement(
    db: Session,
    *,
    observation_id: str | None,
    user_id: str,
    project_id: str,
    entity_type: str,
    entity_id: str,
) -> Observation | None:
    if not observation_id:
        return None
    obs = db.get(Observation, observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="AI candidate observation not found")
    if obs.owner_id is not None and obs.owner_id != user_id:
        raise HTTPException(status_code=404, detail="AI candidate observation not found")
    if obs.project_id is not None and obs.project_id != project_id:
        raise HTTPException(status_code=400, detail="AI candidate belongs to a different project")
    if (
        obs.linked_entity_id is not None
        and (obs.linked_entity_type != entity_type or obs.linked_entity_id != entity_id)
    ):
        raise HTTPException(
            status_code=409,
            detail="AI candidate observation is already linked to another measurement",
        )
    obs.owner_id = obs.owner_id or user_id
    obs.project_id = project_id
    obs.linked_entity_type = entity_type
    obs.linked_entity_id = entity_id
    # Linking an AI candidate to a wall/element never approves either record.
    if obs.review_status == "approved":
        obs.review_status = "needs_review"
    db.flush()
    return obs


def sync_linked_observation_approval(
    db: Session,
    *,
    observation_id: str | None,
    approved: bool,
) -> None:
    if not observation_id:
        return
    obs = db.get(Observation, observation_id)
    if obs is None:
        return
    obs.review_status = "approved" if approved else "needs_review"
    db.flush()


def serialize_observation(obs: Observation) -> dict[str, Any]:
    return {
        "id": obs.id,
        "candidate_id": obs.id,
        "owner_id": obs.owner_id,
        "project_id": obs.project_id,
        "source_type": obs.source_type,
        "raw_value": obs.raw_value,
        "normalized_value_mm": obs.normalized_value_mm,
        "label": obs.label,
        "confidence": obs.confidence,
        "source_asset_id": obs.source_asset_id,
        "source_image_sha256": obs.source_image_sha256,
        "source_region": obs.source_region,
        "prompt_id": obs.prompt_id,
        "provider": obs.provider,
        "model_name": obs.model_name,
        "review_status": obs.review_status,
        "linked_entity_type": obs.linked_entity_type,
        "linked_entity_id": obs.linked_entity_id,
        "clarification": obs.clarification,
        "created_at": obs.created_at.isoformat() if obs.created_at else None,
    }
