import os

os.environ["TESTING"] = "1"
import pytest
from fastapi.testclient import TestClient

import backend.services.search_status as search_status
from backend.db.base import Base, SessionLocal, engine, get_db
from backend.main import app
from backend.models import User
from backend.services.auth import get_password_hash

# Use the centralized Testing session from backend.db.base (triggered by TESTING=1)
TestingSessionLocal = SessionLocal


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def reset_search_status_registry():
    with search_status._lock:
        search_status._statuses.clear()
        search_status._active_tasks.clear()
        search_status._reserved_tasks.clear()
    yield
    with search_status._lock:
        search_status._statuses.clear()
        search_status._active_tasks.clear()
        search_status._reserved_tasks.clear()


@pytest.fixture(scope="function")
def client(setup_database):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db_session(setup_database):
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def test_user(db_session):
    user = User(username="globaladmin", hashed_password=get_password_hash("Globalpass1"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user


@pytest.fixture(scope="function")
def auth_headers(client, test_user):
    response = client.post(
        "/api/v1/auth/login", data={"username": "globaladmin", "password": "Globalpass1"}
    )
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}
