import pytest

class TestAdvancedAuthenticationAPI:

    def test_register_user_success(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "new_auth_user", "password": "Securepassword1"}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["username"] == "new_auth_user"
        assert "access_token" in data

    def test_register_user_duplicate_fails(self, client, test_user):
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "globaladmin", "password": "Newpassword123"}
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    def test_register_user_validation_error(self, client):
        # Missing password field
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "invalid_payload"}
        )
        assert response.status_code == 422 # Pydantic Validation error

    def test_login_success_returns_jwt(self, client, test_user):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "globaladmin", "password": "Globalpass1"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        
    def test_login_invalid_credentials(self, client, test_user):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "globaladmin", "password": "WrongPassword1"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect username or password"

    def test_login_nonexistent_user(self, client):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "does_not_exist", "password": "password"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect username or password"
