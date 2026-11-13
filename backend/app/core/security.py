from datetime import datetime, timedelta, timezone
from typing import Optional
import re
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")

# Prehash new passwords safely; raw bcrypt silently truncates after 72 UTF-8 bytes.
# Keep legacy verification for existing development records, never rewrite hashes blindly.
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        return False

def create_access_token(subject: str, expires_minutes: int | None = None, *, session_id: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "type": "access", "exp": expire, "iat": datetime.now(timezone.utc)}
    payload.update(sid=session_id, jti=secrets.token_hex(16))
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def create_refresh_token(subject: str, *, session_id: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {"sub": subject, "type": "refresh", "exp": expire, "iat": datetime.now(timezone.utc)}
    payload.update(sid=session_id, jti=secrets.token_hex(16))
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
