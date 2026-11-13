from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800

class RefreshRequest(BaseModel):
    refresh_token: str

class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    telegram_chat_id: str | None = None
    telegram_username: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
