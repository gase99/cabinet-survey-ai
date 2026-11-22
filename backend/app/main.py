from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.database import engine, init_db
from app.core.request_limits import RequestLimitMiddleware
from app.services.pdf_text import register_fonts


@asynccontextmanager
async def lifespan(app):
    if settings.app_env != "production":
        init_db()
    # Production schema is owned by Alembic. Fail startup if the DB is unavailable.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    # Exports must never fall back to a system font: refuse to start without the bundled one.
    register_fonts()
    yield

app = FastAPI(
    lifespan=lifespan,
    debug=settings.debug,
    title=settings.app_name,
    version=settings.app_version,
    description="Cabinet Survey AI — field measurement, deterministic geometry, and drawing generation",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Native Android does not need browser CORS; internal worker routes stay behind the gateway.
# CORS is off unless explicit origins are configured (production refuses wildcards).
if settings.cors_origins():
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins(), allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])
app.add_middleware(RequestLimitMiddleware)

app.include_router(api_router)

@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok", "docs": "/docs", "version": settings.app_version}

