import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.db_models import Asset, Project, User
from app.services.uploads import safe_display_name, validated_image_upload

router = APIRouter(prefix="/assets", tags=["assets"])


def _storage_dir() -> Path:
    return Path(os.getenv("ASSET_STORAGE_DIR", "./var/data/assets"))


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
    image = await validated_image_upload(file)
    storage_dir = _storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Server-generated random name; nothing from the client influences the path.
    target = storage_dir / f"{uuid.uuid4().hex}{image.ext}"
    if target.resolve().parent != storage_dir.resolve():
        raise HTTPException(500, "Asset storage misconfigured")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(image.data)
    asset = Asset(owner_id=user.id, project_id=project_id, filename=safe_display_name(file.filename, image.ext),
                  content_type=image.content_type, size_bytes=len(image.data), storage_path=str(target))
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
    path = Path(a.storage_path or "")
    # Defense in depth: only serve files that live directly inside the asset directory.
    if not a.storage_path or path.resolve().parent != _storage_dir().resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(a.storage_path, media_type=a.content_type, filename=a.filename)
