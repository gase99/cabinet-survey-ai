"""Per-device sessions: hashed rotating refresh credentials and server-side revocation."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from fastapi import HTTPException
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.db_models import AuthSession


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def active_session(db, payload):
    sid = payload.get('sid')
    if not isinstance(sid, str):
        raise HTTPException(401, 'Session is no longer valid; sign in again')
    session = db.get(AuthSession, sid)
    if not session or session.user_id != payload.get('sub') or session.revoked or utc(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired or revoked')
    return session


def issue(db, user_id, session=None):
    if session is None:
        session = AuthSession(id=secrets.token_hex(16), user_id=user_id,
            expires_at=datetime.now(timezone.utc)+timedelta(days=settings.jwt_refresh_token_expire_days),
            refresh_digest='', revoked=False)
        db.add(session)
    access = create_access_token(user_id, session_id=session.id)
    refresh = create_refresh_token(user_id, session_id=session.id)
    session.refresh_digest = digest(refresh)
    db.commit()
    return {'access_token':access, 'refresh_token':refresh,
            'token_type':'bearer', 'expires_in':settings.jwt_access_token_expire_minutes*60}
