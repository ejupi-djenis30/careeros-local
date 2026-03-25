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

    def test_login_sets_refresh_cookie_and_refresh_works(self, client, test_user):
        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": "globaladmin", "password": "Globalpass1"}
        )

        assert login_response.status_code == 200
        assert "jh_refresh_token" in login_response.cookies
        assert "jh_refresh_token=" in login_response.headers.get("set-cookie", "")

        refresh_response = client.post("/api/v1/auth/refresh")
        assert refresh_response.status_code == 200
        assert "access_token" in refresh_response.json()
        assert "jh_refresh_token=" in refresh_response.headers.get("set-cookie", "")

    def test_logout_clears_refresh_cookie(self, client, test_user):
        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": "globaladmin", "password": "Globalpass1"}
        )
        assert login_response.status_code == 200

        logout_response = client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 200
        set_cookie = logout_response.headers.get("set-cookie", "")
        assert "jh_refresh_token=" in set_cookie
        assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()
