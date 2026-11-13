import pytest
from app.core.config import settings

@pytest.fixture(autouse=True)
def worker_secret(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-only-worker-secret")

WORKER_HEADERS = {"X-Webhook-Secret": "test-only-worker-secret"}

def test_sync_conflict_detection(client, auth_headers):
    # Create project normally
    p = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Sync Project"})
    pid = p.json()["id"]
    # Simulate offline queue: push create with same id (idempotent)
    push = client.post("/api/v1/sync/push", headers=auth_headers, json={
        "operations": [
            {"id": "op1", "entity_type":"project","entity_id": pid, "operation":"update","payload":{"title":"Sync Project Updated"},"base_version":1}
        ]
    })
    assert push.status_code == 200
    assert push.json()["results"][0]["status"] == "applied"
    # Try with stale base_version -> conflict
    push2 = client.post("/api/v1/sync/push", headers=auth_headers, json={
        "operations": [
            {"id": "op2", "entity_type":"project","entity_id": pid, "operation":"update","payload":{"title":"Stale Update"},"base_version":1}
        ]
    })
    assert push2.json()["results"][0]["status"] == "conflict"
    # Verify not overwritten
    g = client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert g.json()["title"] == "Sync Project Updated"

def test_sync_pull(client, auth_headers):
    r = client.get("/api/v1/sync/pull", headers=auth_headers)
    assert r.status_code == 200
    assert "server_time" in r.json()

def test_telegram_pairing_code(client, auth_headers):
    pc = client.post("/api/v1/telegram/pairing-code", headers=auth_headers)
    assert pc.status_code == 200
    code = pc.json()["code"]
    assert len(code) == 8
    status = client.get("/api/v1/telegram/link-status", headers=auth_headers)
    assert status.json()["linked"] == False
    # Verify pairing via internal endpoint (simulate bot)
    # Worker authentication is required even in development.
    v = client.post("/api/v1/telegram/verify-pairing", headers=WORKER_HEADERS, json={"code": code, "telegram_chat_id":"12345678", "telegram_username":"testuser"})
    assert v.status_code == 200
    status2 = client.get("/api/v1/telegram/link-status", headers=auth_headers)
    assert status2.json()["telegram_chat_id"] == "12345678"
    # Unlink
    u = client.delete("/api/v1/telegram/unlink", headers=auth_headers)
    assert u.status_code == 200

def test_telegram_delivery_queued(client, auth_headers):
    # Create project+room for export
    p = client.post("/api/v1/projects", headers=auth_headers, json={"title": "Telegram Export Project"})
    pid = p.json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/rooms", headers=auth_headers, json={"label":"R","room_type":"rectangular"})
    rid = r.json()["id"]
    for wd in [
        {"label":"A","length_mm":3000,"height_mm":2700,"start_x_mm":0,"start_y_mm":0,"end_x_mm":3000,"end_y_mm":0},
        {"label":"B","length_mm":2000,"height_mm":2700,"start_x_mm":3000,"start_y_mm":0,"end_x_mm":3000,"end_y_mm":2000},
        {"label":"C","length_mm":3000,"height_mm":2700,"start_x_mm":3000,"start_y_mm":2000,"end_x_mm":0,"end_y_mm":2000},
        {"label":"D","length_mm":2000,"height_mm":2700,"start_x_mm":0,"start_y_mm":2000,"end_x_mm":0,"end_y_mm":0},
    ]:
        client.post(f"/api/v1/rooms/{rid}/walls", headers=auth_headers, json=wd)
    exp = client.post(f"/api/v1/exports/{pid}", headers=auth_headers, json={"format":"pdf","layout":"A4"})
    exp_id = exp.json()["id"]
    # Link telegram first
    pc = client.post("/api/v1/telegram/pairing-code", headers=auth_headers).json()["code"]
    client.post("/api/v1/telegram/verify-pairing", headers=WORKER_HEADERS, json={"code": pc, "telegram_chat_id":"987654321"})
    # Send
    send = client.post("/api/v1/telegram/send", headers=auth_headers, json={"export_job_id": exp_id})
    # Without bot token, it should queue
    assert send.status_code == 200
    assert send.json()["status"] in ("queued", "sent")
    # List deliveries
    lst = client.get("/api/v1/telegram/deliveries", headers=auth_headers)
    assert len(lst.json()) >= 1

@pytest.mark.parametrize("endpoint", ["verify-pairing", "webhook", "internal/delivery-result", "internal/pending-deliveries"])
def test_worker_endpoints_fail_closed(client, monkeypatch, endpoint):
    def invoke():
        url = f"/api/v1/telegram/{endpoint}"
        return client.get(url) if endpoint.endswith("pending-deliveries") else client.post(url, json={})
    assert invoke().status_code == 401
    monkeypatch.setattr(settings, "telegram_webhook_secret", None)
    assert invoke().status_code == 503


def test_pairing_replacement_and_single_use(client, auth_headers):
    first = client.post("/api/v1/telegram/pairing-code", headers=auth_headers).json()["code"]
    second = client.post("/api/v1/telegram/pairing-code", headers=auth_headers).json()["code"]
    def pair(code):
        return client.post("/api/v1/telegram/verify-pairing", headers=WORKER_HEADERS,
                           json={"code": code, "telegram_chat_id": "12345"})
    assert pair(first).status_code == 400
    assert pair(second).status_code == 200
    assert pair(second).status_code == 400


def test_pairing_expiration(client, auth_headers, db_session):
    from datetime import datetime, timedelta, timezone
    from app.models.db_models import PairingCode
    code = client.post("/api/v1/telegram/pairing-code", headers=auth_headers).json()["code"]
    record = db_session.query(PairingCode).filter_by(code=code).one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    response = client.post("/api/v1/telegram/verify-pairing", headers=WORKER_HEADERS,
                           json={"code": code, "telegram_chat_id": "12345"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Pairing code expired"
