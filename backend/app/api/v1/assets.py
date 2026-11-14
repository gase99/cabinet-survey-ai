from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import User, Asset, Project
from app.core.config import settings
import os, tempfile, uuid
from fastapi.responses import FileResponse
from pathlib import Path
from app.services.uploads import validated_upload

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
    data, ext = await validated_upload(file)
    storage_dir = Path(os.getenv("ASSET_STORAGE_DIR", "./var/data/assets"))
    storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = str(storage_dir / fname)
    filename = Path(file.filename or fname).name
    if len(filename)>200 or any(ord(c)<32 for c in filename):
        raise HTTPException(422,"Invalid filename")
    fd = os.open(fpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
    asset = Asset(owner_id=user.id, project_id=project_id, filename=filename, content_type=file.content_type or "application/octet-stream", size_bytes=len(data), storage_path=fpath)
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
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes, "project_id": a.project_id, "created_at": a.created_at}

@router.get("/{asset_id}/download")
def download_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(Asset, asset_id)
    if not a or a.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not a.storage_path or not os.path.exists(a.storage_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(a.storage_path, media_type=a.content_type, filename=a.filename)
