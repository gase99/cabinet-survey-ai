from pydantic import BaseModel
from datetime import datetime

class PairingCodeCreateResponse(BaseModel):
    code: str
    expires_at: datetime

class PairingVerifyRequest(BaseModel):
    code: str
    telegram_chat_id: str
    telegram_username: str | None = None

class TelegramLinkOut(BaseModel):
    telegram_chat_id: str
    telegram_username: str | None
    linked_at: datetime | None = None

class TelegramSendRequest(BaseModel):
    project_id: str | None = None
    export_job_id: str
    caption: str | None = None

class DeliveryOut(BaseModel):
    id: str
    status: str
    chat_id: str
    message_id: str | None = None
    error: str | None = None
    model_config = {"from_attributes": True}
