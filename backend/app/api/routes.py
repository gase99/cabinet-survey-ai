from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.admin import router as admin_router
from app.api.v1.ai import router as ai_router
from app.api.v1.assets import router as assets_router
from app.api.v1.auth import router as auth_router
from app.api.v1.customers import router as customers_router
from app.api.v1.drawings import router as drawings_router
from app.api.v1.elements import router as elements_router
from app.api.v1.exports import router as exports_router
from app.api.v1.projects import router as projects_router
from app.api.v1.rooms import router as rooms_router
from app.api.v1.sync import router as sync_router
from app.api.v1.telegram import router as telegram_router
from app.api.v1.walls import router as walls_router
from app.core.database import get_db

router = APIRouter()


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cabinet-survey-api"}


@router.get("/ready", tags=["system"])
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        probe = db.execute(text("SELECT 1")).scalar()
    except SQLAlchemyError as err:
        raise HTTPException(status_code=503, detail="Database unavailable") from err
    if probe != 1:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ready", "service": "cabinet-survey-api", "database": "ok"}


# Mount all v1 under /api/v1
v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth_router)
v1.include_router(customers_router)
v1.include_router(projects_router)
v1.include_router(rooms_router)
v1.include_router(walls_router)
v1.include_router(elements_router)
v1.include_router(ai_router)
v1.include_router(drawings_router)
v1.include_router(exports_router)
v1.include_router(assets_router)
v1.include_router(sync_router)
v1.include_router(telegram_router)
v1.include_router(admin_router)

router.include_router(v1)
