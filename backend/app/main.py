from contextlib import asynccontextmanager
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import router as api_router
from app.core.database import init_db, engine

@asynccontextmanager
async def lifespan(app):
    if settings.app_env != "production":
        init_db()
    # Production schema is owned by Alembic. Fail startup if the DB is unavailable.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield

app = FastAPI(
    lifespan=lifespan,
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
    allow_credentials=settings.app_env != "development",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok", "docs": "/docs", "version": settings.app_version}

