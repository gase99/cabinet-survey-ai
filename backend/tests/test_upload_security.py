import io
from pathlib import Path
from PIL import Image
from app.core.config import settings


def png():
    buffer=io.BytesIO();Image.new('RGB',(10,10),'white').save(buffer,'PNG');return buffer.getvalue()


def test_upload_type_content_validation_and_authorized_download(client,auth_headers,tmp_path):
    bad=client.post('/api/v1/assets',headers=auth_headers,files={'file':('script.svg',b'<svg/>','image/svg+xml')})
    assert bad.status_code==415
    bad=client.post('/api/v1/assets',headers=auth_headers,files={'file':('fake.png',b'not-an-image','image/png')})
    assert bad.status_code==422
    created=client.post('/api/v1/assets',headers=auth_headers,files={'file':('../../escape.png',png(),'image/png')})
    assert created.status_code==201
    asset=created.json()['id']
    info=client.get(f'/api/v1/assets/{asset}',headers=auth_headers)
    assert 'storage_path' not in info.json()
    assert info.json()['filename']=='escape.png'
    assert client.get(f'/api/v1/assets/{asset}/download').status_code==401
    assert client.get(f'/api/v1/assets/{asset}/download',headers=auth_headers).content==png()
    files=list((tmp_path/'assets').iterdir())
    assert len(files)==1 and files[0].suffix=='.png'


def test_upload_size_read_is_bounded(client,auth_headers,monkeypatch):
    monkeypatch.setattr(settings,'upload_max_bytes',4)
    assert client.post('/api/v1/assets',headers=auth_headers,
        files={'file':('large.png',png(),'image/png')}).status_code==413


def test_recovery_does_not_claim_unsent_email(client):
    assert client.post('/api/v1/auth/password-recovery?email=fixture@example.com').status_code==503
