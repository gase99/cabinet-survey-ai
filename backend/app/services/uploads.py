"""Bounded upload validation, independent of untrusted filename and MIME claims."""
import io
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException, UploadFile
from app.core.config import settings

TYPES={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','application/pdf':'.pdf'}
AUDIO_TYPES={'audio/mpeg':'.mp3','audio/wav':'.wav','audio/ogg':'.ogg','audio/webm':'.webm','audio/mp4':'.m4a'}


def _audio_signature_matches(data: bytes, content_type: str) -> bool:
    """Content-sniff the audio container; the declared MIME is never trusted."""
    if content_type == 'audio/mpeg':
        return data[:3] == b'ID3' or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
    if content_type == 'audio/wav':
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    if content_type == 'audio/ogg':
        return data[:4] == b'OggS'
    if content_type == 'audio/webm':
        return data[:4] == b'\x1A\x45\xDF\xA3'
    if content_type == 'audio/mp4':
        return len(data) >= 8 and data[4:8] == b'ftyp'
    return False


async def validated_audio_upload(file: UploadFile):
    content_type = file.content_type or ''
    if content_type not in AUDIO_TYPES:
        raise HTTPException(415, 'Unsupported audio type')
    # One bounded read, even when a malicious client omits Content-Length.
    data = await file.read(settings.audio_max_bytes + 1)
    if not data or len(data) > settings.audio_max_bytes:
        raise HTTPException(413, 'Empty audio upload or file exceeds size limit')
    if not _audio_signature_matches(data, content_type):
        raise HTTPException(422, 'Invalid audio signature or MIME mismatch')
    return data, content_type



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
