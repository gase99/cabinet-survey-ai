import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.main import app

# Use in-memory SQLite for tests
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return eng

@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client):
    # Register and login a test user
    email = "test@example.com"
    password = "TestPass123!"
    name = "Test User"
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": name})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def isolated_export_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPORT_STORAGE_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("ASSET_STORAGE_DIR", str(tmp_path / "assets"))
