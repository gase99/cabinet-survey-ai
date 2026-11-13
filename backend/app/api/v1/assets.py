from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Asset, Project
from app.core.config import settings
import os, tempfile, uuid
from fastapi.responses import FileResponse

router = APIRouter(prefix="/assets", tags=["assets"])

@router.post("", status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if project_id:
        proj = db.get(Project, project_id)
        if not proj or proj.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")
    if file.content_type not in settings.upload_allowed_types.split(",") and "image/" not in file.content_type:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    data = await file.read()
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status_code=400, detail="File too large")
    # Store to temp dir (production would use S3/volume)
    storage_dir = os.getenv("ASSET_STORAGE_DIR", tempfile.gettempdir())
    os.makedirs(storage_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(storage_dir, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    asset = Asset(owner_id=user.id, project_id=project_id, filename=file.filename or fname, content_type=file.content_type or "application/octet-stream", size_bytes=len(data), storage_path=fpath)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {"id": asset.id, "filename": asset.filename, "content_type": asset.content_type, "size_bytes": asset.size_bytes, "project_id": asset.project_id, "created_at": asset.created_at}

@router.get("")
def list_assets(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Asset).filter(Asset.owner_id == user.id)
    if project_id:
        q = q.filter(Asset.project_id == project_id)
    assets = q.order_by(Asset.created_at.desc()).limit(100).all()
    return [{"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes, "project_id": a.project_id, "created_at": a.created_at} for a in assets]

@router.get("/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(Asset, asset_id)
    if not a or a.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes, "project_id": a.project_id, "storage_path": a.storage_path, "created_at": a.created_at}

@router.get("/{asset_id}/download")
def download_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(Asset, asset_id)
    if not a or a.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not a.storage_path or not os.path.exists(a.storage_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(a.storage_path, media_type=a.content_type, filename=a.filename)
