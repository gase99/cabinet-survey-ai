from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.customers import router as customers_router
from app.api.v1.projects import router as projects_router
from app.api.v1.rooms import router as rooms_router
from app.api.v1.walls import router as walls_router
from app.api.v1.elements import router as elements_router
from app.api.v1.ai import router as ai_router
from app.api.v1.drawings import router as drawings_router
from app.api.v1.exports import router as exports_router
from app.api.v1.assets import router as assets_router
from app.api.v1.sync import router as sync_router
from app.api.v1.telegram import router as telegram_router
from app.api.v1.admin import router as admin_router

router = APIRouter()

@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cabinet-survey-api"}

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
