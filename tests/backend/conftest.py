import ipaddress
import os
import socket

# Pytest's best-effort ``*-current`` links are not part of the test contract.  On some Windows
# hosts they can be created but not followed (WinError 1463), turning a green suite into a teardown
# crash.  Disable only those private convenience links; real product symlink tests remain intact.
if os.name == "nt":
    import _pytest.pathlib as _pytest_pathlib

    def _skip_pytest_current_link(_root, _target, _link_to) -> None:
        return None

    _pytest_pathlib._force_symlink = _skip_pytest_current_link

os.environ["TESTING"] = "1"
os.environ.setdefault("SECRET_KEY", "test-only-local-secret-key-at-least-32-bytes")
import pytest
from fastapi.testclient import TestClient

import backend.services.search_status as search_status
from backend.api.deps import require_local_analysis_ready
from backend.db.base import Base, SessionLocal, engine, get_db
from backend.main import app
from backend.models import User
from backend.services.auth import get_password_hash

# Use the centralized Testing session from backend.db.base (triggered by TESTING=1)
TestingSessionLocal = SessionLocal


def _is_loopback_host(host: object) -> bool:
    value = str(host).strip().lower().strip("[]")
    if value in {"localhost", "testserver", "ollama"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def deny_public_network(request, monkeypatch):
    """Fail fast on accidental egress; only explicit ``live`` tests may use it."""
    if request.node.get_closest_marker("live"):
        yield
        return

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(sock, address):
        if sock.family == getattr(socket, "AF_UNIX", None):
            return original_connect(sock, address)
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_loopback_host(host):
            raise AssertionError(f"Public network access is disabled in tests: {host}")
        return original_connect(sock, address)

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_loopback_host(host):
            raise AssertionError(f"Public network access is disabled in tests: {host}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


async def override_local_analysis_ready() -> None:
    return None


@pytest.fixture(autouse=True)
def allow_local_analysis_by_default():
    """Keep unrelated API tests independent from the installed model/runtime state."""
    app.dependency_overrides[require_local_analysis_ready] = override_local_analysis_ready
    yield
    app.dependency_overrides.pop(require_local_analysis_ready, None)


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
