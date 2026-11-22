import io
import re
import struct
import zlib

from PIL import Image

from app.core.config import settings

ASSET_NAME = re.compile(r'^[0-9a-f]{32}\.(png|jpg|webp)$')


def png(size=(10, 10)):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'white').save(buffer, 'PNG')
    return buffer.getvalue()


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF)


def bomb_png(width: int, height: int) -> bytes:
    """A tiny but structurally valid PNG header declaring huge dimensions."""
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    idat = zlib.compress(b'\x00' * 64)
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', idat) + _chunk(b'IEND', b'')


def jpeg_with_gps_exif(size=(20, 10)) -> bytes:
    image = Image.new('RGB', size, (200, 10, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW for display
    exif[0x010F] = 'FixtureCam'  # Make
    exif[0x8825] = {1: 'N', 2: (50.0, 6.0, 0.0), 3: 'E', 4: (8.0, 41.0, 0.0)}  # GPS IFD
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', exif=exif.tobytes())
    return buffer.getvalue()


def upload(client, headers, name, data, mime):
    return client.post('/api/v1/assets', headers=headers, files={'file': (name, data, mime)})


def stored_files(tmp_path):
    root = tmp_path / 'assets'
    return sorted(root.iterdir()) if root.exists() else []


def test_upload_type_content_validation_and_authorized_download(client, auth_headers, tmp_path):
    bad = upload(client, auth_headers, 'script.svg', b'<svg/>', 'image/svg+xml')
    assert bad.status_code == 415
    bad = upload(client, auth_headers, 'fake.png', b'not-an-image', 'image/png')
    assert bad.status_code == 422
    created = upload(client, auth_headers, '../../escape.png', png(), 'image/png')
    assert created.status_code == 201
    asset = created.json()['id']
    info = client.get(f'/api/v1/assets/{asset}', headers=auth_headers)
    assert 'storage_path' not in info.json()
    assert info.json()['filename'] == 'escape.png'
    assert client.get(f'/api/v1/assets/{asset}/download').status_code == 401
    downloaded = client.get(f'/api/v1/assets/{asset}/download', headers=auth_headers).content
    with Image.open(io.BytesIO(downloaded)) as image:
        assert image.format == 'PNG' and image.size == (10, 10)
    files = stored_files(tmp_path)
    assert len(files) == 1 and files[0].suffix == '.png'
    assert files[0].read_bytes() == downloaded


def test_pdf_and_other_non_image_types_are_rejected(client, auth_headers, tmp_path):
    assert upload(client, auth_headers, 'doc.pdf', b'%PDF-1.7\n', 'application/pdf').status_code == 415
    assert upload(client, auth_headers, 'a.gif', b'GIF89a' + b'\x00' * 20, 'image/gif').status_code == 415
    assert stored_files(tmp_path) == []


def test_wrong_magic_bytes_with_image_extension_rejected(client, auth_headers, tmp_path):
    html = b'<html><script>alert(1)</script></html>'
    gif = b'GIF89a\x01\x00\x01\x00\x00\x00\x00;'
    for name, data, mime in [('photo.jpg', html, 'image/jpeg'), ('photo.png', gif, 'image/png'),
                             ('photo.webp', b'RIFF\x00\x00\x00\x00AVI LIST', 'image/webp')]:
        response = upload(client, auth_headers, name, data, mime)
        assert response.status_code == 422, name
        assert 'magic bytes' in response.json()['detail']
    # Real PNG bytes but declared/extension as JPEG are also rejected (no type confusion).
    mismatch = upload(client, auth_headers, 'photo.png', png(), 'image/jpeg')
    assert mismatch.status_code == 422 and 'does not match' in mismatch.json()['detail']
    extension = upload(client, auth_headers, 'photo.jpg', png(), 'image/png')
    assert extension.status_code == 422 and 'extension' in extension.json()['detail']
    # Valid header followed by garbage cannot be decoded.
    truncated = upload(client, auth_headers, 'cut.png', png()[:40], 'image/png')
    assert truncated.status_code == 422
    assert stored_files(tmp_path) == []


def test_oversize_file_rejected_with_clear_error(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'upload_max_bytes', 64)
    response = upload(client, auth_headers, 'large.png', png((50, 50)), 'image/png')
    assert response.status_code == 413
    assert 'size limit of 64 bytes' in response.json()['detail']
    assert stored_files(tmp_path) == []


def test_empty_upload_rejected(client, auth_headers):
    assert upload(client, auth_headers, 'empty.png', b'', 'image/png').status_code == 422


def test_decompression_bomb_dimensions_rejected_before_decoding(client, auth_headers, tmp_path):
    bomb = bomb_png(60_000, 60_000)  # 3.6 gigapixels declared in a ~100-byte file
    assert len(bomb) < 200
    response = upload(client, auth_headers, 'bomb.png', bomb, 'image/png')
    assert response.status_code == 413
    assert 'decompression bomb' in response.json()['detail']
    # Below Pillow's own bomb threshold, our stricter limit reports the exact dimensions.
    medium = upload(client, auth_headers, 'medium.png', bomb_png(8000, 8000), 'image/png')
    assert medium.status_code == 413
    assert '8000x8000' in medium.json()['detail']
    # Per-side limit applies even when the total pixel count is small.
    wide = upload(client, auth_headers, 'wide.png', bomb_png(settings.upload_max_dimension + 1, 1), 'image/png')
    assert wide.status_code == 413
    assert stored_files(tmp_path) == []


def test_pixel_limit_is_enforced(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, 'upload_max_pixels', 99)
    response = upload(client, auth_headers, 'ten.png', png((10, 10)), 'image/png')
    assert response.status_code == 413 and '99 pixels' in response.json()['detail']


def test_path_traversal_filenames_never_reach_the_filesystem(client, auth_headers, tmp_path):
    names = ['../../etc/passwd.png', '..\\..\\windows\\evil.png', '/abs/olute.png', '....//x.png',
             'a\x00b.png', '..', '.hidden.png']
    display = []
    for name in names:
        response = upload(client, auth_headers, name, png(), 'image/png')
        assert response.status_code in (201, 422), name
        if response.status_code == 201:
            label = response.json()['filename']
            assert '/' not in label and '\\' not in label and '..' not in label and '\x00' not in label
            assert label.endswith('.png') and not label.startswith('.')
            display.append(label)
    assert 'passwd.png' in display and 'evil.png' in display
    files = stored_files(tmp_path)
    assert files and all(ASSET_NAME.match(path.name) for path in files)
    # Nothing was written outside the asset directory.
    assert sorted(p.name for p in tmp_path.iterdir()) == ['assets']


def test_exif_gps_and_trailing_payloads_are_stripped(client, auth_headers, tmp_path):
    original = jpeg_with_gps_exif()
    with Image.open(io.BytesIO(original)) as image:
        assert image.getexif().get_ifd(0x8825)  # fixture really contains GPS
    payload = b'<?php echo "polyglot"; ?>'
    response = upload(client, auth_headers, 'site.jpg', original + payload, 'image/jpeg')
    assert response.status_code == 201
    asset = response.json()['id']
    data = client.get(f'/api/v1/assets/{asset}/download', headers=auth_headers).content
    assert payload not in data and b'FixtureCam' not in data and b'Exif' not in data
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == 'JPEG'
        assert len(image.getexif()) == 0
        assert 'exif' not in image.info
        # Orientation was applied to the pixels before metadata removal.
        assert image.size == (10, 20)
    assert stored_files(tmp_path)[0].read_bytes() == data
    assert response.json()['size_bytes'] == len(data)


def test_png_text_chunks_and_icc_profile_are_stripped(client, auth_headers):
    from PIL import PngImagePlugin
    info = PngImagePlugin.PngInfo()
    info.add_text('Comment', 'secret-location-note')
    buffer = io.BytesIO()
    Image.new('RGBA', (8, 8), (0, 0, 0, 0)).save(buffer, 'PNG', pnginfo=info, icc_profile=b'fake-icc')
    response = upload(client, auth_headers, 'note.png', buffer.getvalue(), 'image/png')
    assert response.status_code == 201
    data = client.get(f"/api/v1/assets/{response.json()['id']}/download", headers=auth_headers).content
    assert b'secret-location-note' not in data and b'iCCP' not in data
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == 'RGBA'


def test_webp_is_accepted_and_reencoded(client, auth_headers):
    buffer = io.BytesIO()
    Image.new('RGB', (12, 6), 'blue').save(buffer, 'WEBP')
    response = upload(client, auth_headers, 'w.webp', buffer.getvalue(), 'image/webp')
    assert response.status_code == 201 and response.json()['content_type'] == 'image/webp'


def test_sketch_analysis_uses_same_validation_and_only_forwards_reencoded_image(client, auth_headers, monkeypatch):
    seen: list[bytes] = []

    class Capture:
        provider_name = 'fixture'
        model = 'fixture'

        async def analyze_sketch(self, data: bytes, *, language_hint: str = 'fa,en') -> dict:
            seen.append(data)
            return {'observations': [], 'ambiguities': [], 'clarification_questions': []}

    monkeypatch.setattr('app.api.v1.ai.configured_provider', lambda db: Capture())
    bad = client.post('/api/v1/ai/sketch-analysis', headers=auth_headers,
                      files={'file': ('s.jpg', b'<html/>', 'image/jpeg')})
    assert bad.status_code == 422 and seen == []
    bomb = client.post('/api/v1/ai/sketch-analysis', headers=auth_headers,
                       files={'file': ('s.png', bomb_png(50_000, 50_000), 'image/png')})
    assert bomb.status_code == 413 and seen == []
    ok = client.post('/api/v1/ai/sketch-analysis', headers=auth_headers,
                     files={'file': ('s.jpg', jpeg_with_gps_exif(), 'image/jpeg')})
    assert ok.status_code == 200
    assert len(seen) == 1 and b'Exif' not in seen[0] and b'FixtureCam' not in seen[0]


def test_recovery_does_not_claim_unsent_email(client):
    assert client.post('/api/v1/auth/password-recovery?email=fixture@example.com').status_code == 503


def test_request_ingress_rejects_oversized_json_before_parsing(client):
    response = client.post('/api/v1/auth/login', content=b'x' * (1024 * 1024 + 1),
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
