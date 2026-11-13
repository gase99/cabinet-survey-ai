"""Bounded upload validation, independent of untrusted filename and MIME claims."""
import io
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException, UploadFile
from app.core.config import settings

TYPES={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','application/pdf':'.pdf'}


async def validated_upload(file: UploadFile, *, images_only=False):
    content_type=file.content_type or ''
    if content_type not in TYPES or (images_only and not content_type.startswith('image/')):
        raise HTTPException(415,'Unsupported file type')
    # One bounded read, even when a malicious client omits Content-Length.
    data=await file.read(settings.upload_max_bytes+1)
    if not data or len(data)>settings.upload_max_bytes:
        raise HTTPException(413,'Empty upload or file exceeds size limit')
    if content_type=='application/pdf':
        if not data.startswith(b'%PDF-'):
            raise HTTPException(422,'Invalid PDF signature')
    else:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width*image.height>40_000_000:
                    raise ValueError('Image too large')
                actual=Image.MIME.get(image.format)
                if actual!=content_type:
                    raise ValueError('MIME mismatch')
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(422,'Invalid image or MIME mismatch')
    return data, TYPES[content_type]
