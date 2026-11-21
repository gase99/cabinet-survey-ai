"""Real PostgreSQL locking tests; refuse all non-disposable databases."""
import concurrent.futures
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.main import app
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
    monkeypatch.setattr(settings,'telegram_worker_secret','fixture-worker-secret-not-real')
    with TestClient(app) as client:
        headers=account(client)
        code=client.post('/api/v1/telegram/pairing-code',headers=headers).json()['code']
        def verify(chat):
            with TestClient(app) as worker:
                return worker.post('/api/v1/telegram/verify-pairing',headers={'X-Webhook-Secret':settings.telegram_worker_secret},
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


def test_postgres_concurrent_rest_put_returns_409_on_stale_version():
    with TestClient(app) as client:
        headers=account(client)
        project=client.post('/api/v1/projects',headers=headers,json={'title':'REST Lock fixture'}).json()['id']
        room=client.post(f'/api/v1/projects/{project}/rooms',headers=headers,json={'label':'Kitchen'}).json()['id']
        wall=client.post(f'/api/v1/rooms/{room}/walls',headers=headers,json={'label':'W1','length_mm':3000,'height_mm':2700}).json()['id']
        def put_wall(index):
            with TestClient(app) as worker:
                return worker.put(f'/api/v1/walls/{wall}',headers=headers,json={'length_mm':3000+index*100,'version':1}).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(put_wall,[1,2]))
        assert sorted(statuses)==[200,409]
        assert client.get(f'/api/v1/walls/{wall}',headers=headers).json()['version']==2


def test_postgres_audit_triggers_block_raw_sql_mutation():
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    from app.models.db_models import AuditEvent

    with TestClient(app) as client:
        headers=account(client)
        cust=client.post('/api/v1/customers',headers=headers,json={'name':'PG Trigger Check'}).json()
    with Session(engine) as db:
        ev=db.query(AuditEvent).filter(AuditEvent.entity_id==cust['id']).first()
        assert ev is not None
        with pytest.raises(DatabaseError):
            db.execute(text("UPDATE audit_events SET action='tampered' WHERE id=:id"),{'id':ev.id})
        db.rollback()
        with pytest.raises(DatabaseError):
            db.execute(text("DELETE FROM audit_events WHERE id=:id"),{'id':ev.id})
        db.rollback()


def test_postgres_concurrent_idempotency_creates_single_export_and_delivery(monkeypatch):
    import threading

    from app.models.db_models import ExportJob, TelegramDelivery

    monkeypatch.setattr(settings, "telegram_worker_secret", "pg-idem-worker-secret-012345")
    with TestClient(app) as client:
        headers = account(client)
        project = client.post(
            "/api/v1/projects", headers=headers, json={"title": "PG Idempotency Lock"}
        ).json()["id"]
        room = client.post(
            f"/api/v1/projects/{project}/rooms", headers=headers, json={"label": "Kitchen"}
        ).json()["id"]
        coords = [
            ("North", 4000, 0, 0, 4000, 0),
            ("East", 3000, 4000, 0, 4000, 3000),
            ("South", 4000, 4000, 3000, 0, 3000),
            ("West", 3000, 0, 3000, 0, 0),
        ]
        for label, length, sx, sy, ex, ey in coords:
            wid = client.post(
                f"/api/v1/rooms/{room}/walls",
                headers=headers,
                json={
                    "label": label,
                    "length_mm": length,
                    "height_mm": 2700,
                    "start_x_mm": sx,
                    "start_y_mm": sy,
                    "end_x_mm": ex,
                    "end_y_mm": ey,
                },
            ).json()["id"]
            assert client.post(f"/api/v1/walls/{wid}/approve", headers=headers).status_code == 200

        code = client.post("/api/v1/telegram/pairing-code", headers=headers).json()["code"]
        assert (
            client.post(
                "/api/v1/telegram/verify-pairing",
                headers={"X-Webhook-Secret": settings.telegram_worker_secret},
                json={"code": code, "telegram_chat_id": "888001"},
            ).status_code
            == 200
        )

    workers = 4
    exp_barrier = threading.Barrier(workers)

    def run_export(_idx: int):
        with TestClient(app) as worker:
            exp_barrier.wait(timeout=10)
            resp = worker.post(
                f"/api/v1/exports/{project}",
                headers={**headers, "Idempotency-Key": "pg-export-race-key"},
                json={"format": "pdf", "layout": "A4"},
            )
            return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        exp_results = list(pool.map(run_export, range(workers)))
    assert [s for s, _ in exp_results] == [201] * workers
    export_ids = {b["id"] for _, b in exp_results}
    assert len(export_ids) == 1
    export_id = next(iter(export_ids))

    tg_barrier = threading.Barrier(workers)

    def run_send(_idx: int):
        with TestClient(app) as worker:
            tg_barrier.wait(timeout=10)
            resp = worker.post(
                "/api/v1/telegram/send",
                headers={**headers, "Idempotency-Key": "pg-tg-race-key"},
                json={"export_job_id": export_id},
            )
            return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        tg_results = list(pool.map(run_send, range(workers)))
    assert [s for s, _ in tg_results] == [200] * workers
    assert len({b["delivery_id"] for _, b in tg_results}) == 1

    with Session(engine) as db:
        assert db.query(ExportJob).filter(ExportJob.project_id == project).count() == 1
        assert (
            db.query(TelegramDelivery)
            .filter(TelegramDelivery.export_job_id == export_id)
            .count()
            == 1
        )


