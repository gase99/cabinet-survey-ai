from fastapi import FastAPI
from app.api.routes import router as api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0", description="Cabinet Survey AI API scaffold")
app.include_router(api_router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "scaffold", "docs": "/docs"}
