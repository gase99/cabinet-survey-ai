from pydantic import BaseModel, Field
from datetime import datetime

class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    notes: str | None = None

class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = None
    address: str | None = None
    notes: str | None = None

class CustomerOut(BaseModel):
    version: int
    id: str
    owner_id: str
    name: str
    phone: str | None
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
