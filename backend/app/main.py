from contextlib import asynccontextmanager
from sqlalchemy import text
from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import router as api_router
from app.core.database import init_db, engine
from app.core.request_limits import RequestLimitMiddleware

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

# Native Android does not need browser CORS; internal worker routes stay behind the gateway.
app.add_middleware(RequestLimitMiddleware)

app.include_router(api_router)

@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok", "docs": "/docs", "version": settings.app_version}

