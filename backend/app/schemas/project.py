from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    customer_id: str | None = None
    site_notes: str | None = None
    status: str = Field(default="draft", pattern="^(draft|in_progress|completed|archived)$")

class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    customer_id: str | None = None
    site_notes: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|in_progress|completed|archived|deleted)$")

class ProjectOut(BaseModel):
    id: str
    owner_id: str
    customer_id: str | None
    title: str
    status: str
    site_notes: str | None
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class ProjectSearchParams(BaseModel):
    q: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
