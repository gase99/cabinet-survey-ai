from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "Cabinet Survey AI"

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_api_health():
    # also mounted under /api/v1? No, health at /health
    r = client.get("/health")
    assert r.json()["service"] == "cabinet-survey-api"
