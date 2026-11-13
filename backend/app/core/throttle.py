"""Atomic shared-database quota. Never trust arbitrary X-Forwarded-For headers.
Reverse proxy deployments must explicitly configure trusted proxy addresses.
"""
import hashlib
import time
from fastapi import Depends,HTTPException,Request
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.models.db_models import AuthThrottle


def auth_rate_limit(request: Request, db: Session = Depends(get_db)):
    now=int(time.time());bucket=now//60
    address=request.client.host if request.client else 'unknown'
    key=hashlib.sha256(f'{address}|{request.url.path}|{bucket}'.encode()).hexdigest()
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    query=insert(AuthThrottle).values(key=key,bucket=bucket,attempts=1)
    query=query.on_conflict_do_update(index_elements=['key'],set_={'attempts':AuthThrottle.attempts+1}).returning(AuthThrottle.attempts)
    count=db.execute(query).scalar_one()
    db.execute(delete(AuthThrottle).where(AuthThrottle.bucket<bucket-2))
    db.commit()
    if count>settings.rate_limit_auth_per_minute:
        raise HTTPException(429,'Authentication request limit exceeded',headers={'Retry-After':str(60-now%60)})
