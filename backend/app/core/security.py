from datetime import datetime, timedelta, timezone
from typing import Optional
import re

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 4.0.1 needs passlib fix: truncate to 72 bytes handled by passlib
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "type": "access", "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": subject, "type": "refresh", "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

PASSWORD_RE = re.compile(r"^.{8,128}$")

def validate_password_strength(pw: str) -> str | None:
    if len(pw) < 8:
        return "Password must be at least 8 characters"
    if len(pw) > 128:
        return "Password too long"
    return None
