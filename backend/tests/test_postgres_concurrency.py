"""Real PostgreSQL locking tests; refuse all non-disposable databases."""
import concurrent.futures
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.main import app
from app.core.config import settings
from app.core.database import engine
from app.models.db_models import AuthThrottle

url=make_url(settings.database_url)
pytestmark=pytest.mark.skipif(not(os.getenv('ACCEPTANCE_DISPOSABLE_DATABASE')=='1' and url.database=='cabinet_test' and url.username=='fixture' and url.host in {'127.0.0.1','localhost'}),reason='Requires isolated PostgreSQL fixture database')


def account(client):
    email=f'locking-{uuid.uuid4()}@example.com'
    assert client.post('/api/v1/auth/register',json={'email':email,'password':'FixturePassword123','display_name':'Lock fixture'}).status_code==201
    token=client.post('/api/v1/auth/login',json={'email':email,'password':'FixturePassword123'}).json()['access_token']
    return {'Authorization':'Bearer '+token}


def test_postgres_concurrent_measurements_never_silently_overwrite():
    with TestClient(app) as client:
        headers=account(client)
        project=client.post('/api/v1/projects',headers=headers,json={'title':'Lock fixture'}).json()['id']
        def update(index):
            with TestClient(app) as worker:
                return worker.post('/api/v1/sync/push',headers=headers,json={'operations':[{'id':str(uuid.uuid4()),
                    'entity_type':'project','entity_id':project,'operation':'update','base_version':1,
                    'payload':{'title':f'Concurrent fixture {index}'}}]}).json()['results'][0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(update,[1,2]))
        assert sorted(r['status'] for r in results)==['applied','conflict']
        assert client.get(f'/api/v1/projects/{project}',headers=headers).json()['version']==2


def test_postgres_pairing_code_consumption_is_atomic(monkeypatch):
    monkeypatch.setattr(settings,'telegram_webhook_secret','fixture-worker-secret-not-real')
    with TestClient(app) as client:
        headers=account(client)
        code=client.post('/api/v1/telegram/pairing-code',headers=headers).json()['code']
        def verify(chat):
            with TestClient(app) as worker:
                return worker.post('/api/v1/telegram/verify-pairing',headers={'X-Webhook-Secret':settings.telegram_webhook_secret},
                    json={'code':code,'telegram_chat_id':chat}).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(verify,['123','456']))
        assert sorted(statuses)==[200,400]


def test_postgres_quota_is_shared_and_atomic(monkeypatch):
    monkeypatch.setattr(settings,'rate_limit_auth_per_minute',2)
    with Session(engine) as db:
        db.execute(delete(AuthThrottle));db.commit()
    def attempt(index):
        with TestClient(app) as worker:
            return worker.post('/api/v1/auth/login',json={'email':'not-present@example.com','password':'FixtureWrong'}).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        statuses=list(pool.map(attempt,range(8)))
    assert statuses.count(401)==2 and statuses.count(429)==6
