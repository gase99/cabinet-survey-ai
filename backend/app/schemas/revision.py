from datetime import datetime
from pydantic import BaseModel


class MeasurementRevisionOut(BaseModel):
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    revision_number: int
    previous_revision_id: str | None = None
    payload: dict
    review_status: str
    change_reason: str
    changed_by: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}
