"""Bounded upload validation, independent of untrusted filename and MIME claims.

Images are decoded and re-encoded server-side; only the re-encoded copy is ever stored
or forwarded. This is input hardening, not malware scanning."""
import io
import os
import re
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

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



# Images only (JPEG, PNG, WebP). The type is decided by magic bytes; the declared
# Content-Type and filename extension must agree with it but are never trusted alone.
TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
_PIL_FORMATS = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
_EXTENSIONS = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}


def sniff_image_type(data: bytes) -> str | None:
    """Return the allowlisted MIME type identified by magic bytes, else None."""
    if data[:3] == b'\xFF\xD8\xFF':
        return 'image/jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def safe_display_name(raw: str | None, ext: str) -> str:
    """Display-only label derived from the client filename; never used as a path.

    Both separators are treated as path separators, control characters and leading dots
    are removed, and the extension is replaced with the server-determined one."""
    base = re.split(r'[\\/]', raw or '')[-1]
    base = ''.join(c for c in base if ord(c) >= 32 and c not in '<>:"|?*').strip().lstrip('.')
    stem = os.path.splitext(base)[0].strip()[:120]
    return f"{stem or 'image'}{ext}"


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    content_type: str
    ext: str
    width: int
    height: int


def _reject(status: int, detail: str) -> HTTPException:
    return HTTPException(status, detail)


def reencode_image(data: bytes, declared_type: str, filename: str | None = None) -> CleanImage:
    """Validate an untrusted image and return a freshly encoded copy without metadata."""
    sniffed = sniff_image_type(data)
    if sniffed is None:
        raise _reject(422, 'File content is not a JPEG, PNG or WebP image (magic bytes)')
    if declared_type != sniffed:
        raise _reject(422, f'Declared type {declared_type or "none"} does not match file content {sniffed}')
    ext = os.path.splitext(re.split(r'[\\/]', filename or '')[-1])[1].lower()
    if ext and _EXTENSIONS.get(ext) != sniffed:
        raise _reject(422, f'Filename extension {ext} does not match file content {sniffed}')
    max_side, max_pixels = settings.upload_max_dimension, settings.upload_max_pixels
    try:
        with Image.open(io.BytesIO(data)) as image:
            # Dimensions come from the header; reject before any pixel data is decoded.
            width, height = image.size
            if width < 1 or height < 1 or width > max_side or height > max_side or width * height > max_pixels:
                raise _reject(413, f'Image dimensions {width}x{height} exceed the limit of '
                                   f'{max_side} px per side and {max_pixels} pixels in total')
            if _PIL_FORMATS.get(image.format or '') != sniffed:
                raise _reject(422, 'Image decoder format does not match file content')
            if getattr(image, 'n_frames', 1) != 1:
                raise _reject(422, 'Animated or multi-frame images are not accepted')
            image.load()
            # Apply camera orientation to the pixels, then drop every metadata block
            # (EXIF incl. GPS, XMP, ICC, text chunks, comments, trailing payloads).
            oriented = ImageOps.exif_transpose(image)
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        # Pillow refuses absurd header dimensions while opening, before any decoding.
        raise _reject(413, f'Image dimensions exceed the limit of {max_side} px per side and '
                           f'{max_pixels} pixels in total (decompression bomb)')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise _reject(422, 'Image could not be decoded')
    if sniffed == 'image/jpeg':
        mode = 'L' if oriented.mode in ('1', 'L') else 'RGB'
    else:
        has_alpha = 'A' in oriented.mode or 'transparency' in oriented.info
        mode = 'RGBA' if has_alpha else ('L' if oriented.mode in ('1', 'L') else 'RGB')
    clean = oriented.convert(mode) if oriented.mode != mode else oriented.copy()
    clean.info = {}
    out = io.BytesIO()
    if sniffed == 'image/jpeg':
        clean.save(out, 'JPEG', quality=90, optimize=True)
    elif sniffed == 'image/png':
        clean.save(out, 'PNG', optimize=True)
    else:
        clean.save(out, 'WEBP', quality=90, method=4)
    return CleanImage(out.getvalue(), sniffed, TYPES[sniffed], clean.width, clean.height)


async def validated_image_upload(file: UploadFile) -> CleanImage:
    declared = (file.content_type or '').split(';')[0].strip().lower()
    if declared not in TYPES:
        raise HTTPException(415, 'Unsupported file type; only JPEG, PNG and WebP images are accepted')
    # One bounded read, even when a malicious client omits Content-Length.
    data = await file.read(settings.upload_max_bytes + 1)
    if not data:
        raise HTTPException(422, 'Empty upload')
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(413, f'File exceeds the size limit of {settings.upload_max_bytes} bytes')
    return reencode_image(data, declared, file.filename)
