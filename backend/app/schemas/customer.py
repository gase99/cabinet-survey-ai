from datetime import datetime
from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    notes: str | None = None
    version: int | None = Field(strict=True, default=None, ge=1)
    base_version: int | None = Field(strict=True, default=None, ge=1)


class CustomerOut(BaseModel):
    version: int
    id: str
    owner_id: str
    name: str
    phone: str | None
    address: str | None
    notes: str | None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
