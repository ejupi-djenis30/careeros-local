from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.db.base import get_db
from backend.api.deps import limiter
from backend.models import User

client = TestClient(app, raise_server_exceptions=False)

def test_register_success():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[limiter] = lambda: None # Assuming limiter bypass if possible, though slowapi usually ignores testclient
    
    with patch("backend.api.routes.auth.create_access_token", return_value="access"), \
         patch("backend.api.routes.auth.create_refresh_token", return_value="refresh"), \
         patch("backend.api.routes.auth.get_password_hash", return_value="hash"):
        
        response = client.post("/api/v1/auth/register", json={"username": "newuser", "password": "NewPassword1!"})
        assert response.status_code == 200
        assert response.json() == {"access_token": "access", "token_type": "bearer", "username": "newuser"}
        assert "jh_refresh_token=refresh" in response.headers.get("set-cookie", "")

    app.dependency_overrides.clear()

def test_register_existing_user():
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.post("/api/v1/auth/register", json={"username": "exist", "password": "ExistUserPwd1!"})
    assert response.status_code == 400
    assert "Registration failed" in response.json()["detail"]
    app.dependency_overrides.clear()

def test_login_success():
    mock_db = MagicMock()
    mock_user = MagicMock(username="user", hashed_password="pwd")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    
    with patch("backend.api.routes.auth.verify_password", return_value=True), \
         patch("backend.api.routes.auth.create_access_token", return_value="acc"), \
         patch("backend.api.routes.auth.create_refresh_token", return_value="ref"):
         
        response = client.post("/api/v1/auth/login", data={"username": "user", "password": "pwd"})
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc"
        assert "jh_refresh_token=ref" in response.headers.get("set-cookie", "")
    
    app.dependency_overrides.clear()

def test_login_failure():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.post("/api/v1/auth/login", data={"username": "user", "password": "pwd"})
    assert response.status_code == 401
    
    app.dependency_overrides.clear()

def test_refresh_success():
    mock_db = MagicMock()
    mock_user = MagicMock(username="user")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    
    with patch("backend.api.routes.auth.decode_refresh_token", return_value={"sub": "user"}), \
         patch("backend.api.routes.auth.create_access_token", return_value="acc2"), \
         patch("backend.api.routes.auth.create_refresh_token", return_value="ref2"):
         
        client.cookies.set("jh_refresh_token", "old_ref")
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc2"
        assert "jh_refresh_token=ref2" in response.headers.get("set-cookie", "")
        
    app.dependency_overrides.clear()
    client.cookies.clear()

def test_refresh_vanished_user():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    
    with patch("backend.api.routes.auth.decode_refresh_token", return_value={"sub": "user"}):
        client.cookies.set("jh_refresh_token", "old_ref")
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401
        assert response.json()["detail"] == "User vanished"
        
    app.dependency_overrides.clear()
    client.cookies.clear()

def test_logout():
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers.get("set-cookie", "")

from backend.services.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token
)

def test_password_hashing():
    pwd = "my_secure_password"
    hashed = get_password_hash(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong", hashed) is False
    
def test_password_verify_value_error():
    assert verify_password("plain", "not_a_valid_hash") is False # triggers ValueError from bcrypt
    
def test_create_and_decode_access_token():
    token = create_access_token({"sub": "user"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user"
    assert decoded["type"] == "access"
    
def test_create_and_decode_refresh_token():
    token = create_refresh_token({"sub": "user"})
    decoded = decode_refresh_token(token)
    assert decoded["sub"] == "user"
    assert decoded["type"] == "refresh"
    
def test_decode_invalid_token():
    assert decode_access_token("invalid.token.here") is None
    assert decode_refresh_token("invalid.token.here") is None
    
def test_decode_wrong_type_token():
    access_token = create_access_token({"sub": "user"})
    refresh_token = create_refresh_token({"sub": "user"})
    
    assert decode_access_token(refresh_token) is None
    assert decode_refresh_token(access_token) is None
