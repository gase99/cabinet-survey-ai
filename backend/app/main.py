from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import router as api_router
from app.core.database import init_db

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Cabinet Survey AI — field measurement, deterministic geometry, and drawing generation",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"] if settings.app_env == "development" else settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok", "docs": "/docs", "version": settings.app_version}

@app.on_event("startup")
def startup():
    # Ensure tables exist (alembic for production, create_all for dev/test convenience)
    try:
        init_db()
    except Exception as e:
        # Log but don't crash startup; health should still respond
        print(f"DB init warning: {e}")
