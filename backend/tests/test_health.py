from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.database import get_db
from app.main import app


def test_root() -> None:
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert r.json()["name"] == "Cabinet Survey AI"


def test_health_stays_cheap_even_when_db_fails() -> None:
    class _BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise OperationalError("SELECT 1", {}, RuntimeError("db offline"))

    def broken_db():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    try:
        with TestClient(app) as c:
            r = c.get("/health")
            assert r.status_code == 200
            assert r.json() == {"status": "ok", "service": "cabinet-survey-api"}

            ready_resp = c.get("/ready")
            assert ready_resp.status_code == 503
            assert ready_resp.json()["detail"] == "Database unavailable"
    finally:
        app.dependency_overrides.clear()


def test_ready_verifies_database_connection(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ready",
        "service": "cabinet-survey-api",
        "database": "ok",
    }
