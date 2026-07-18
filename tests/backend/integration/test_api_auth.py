REFRESH_COOKIE_NAME = "careeros_refresh_token"
LEGACY_REFRESH_COOKIE_NAME = "jh_refresh_token"


def _cookie_was_deleted(response, cookie_name):
    return any(
        header.startswith(f"{cookie_name}=")
        and ("Max-Age=0" in header or "expires=" in header.lower())
        for header in response.headers.get_list("set-cookie")
    )


class TestAdvancedAuthenticationAPI:
    def test_register_user_success(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "new_auth_user", "password": "Securepassword1"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["username"] == "new_auth_user"
        assert "access_token" in data
        assert REFRESH_COOKIE_NAME in response.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies

    def test_register_user_duplicate_fails(self, client, test_user):
        response = client.post(
            "/api/v1/auth/register", json={"username": "globaladmin", "password": "Newpassword123"}
        )
        assert response.status_code == 400
        assert "Registration failed" in response.json()["detail"]

    def test_register_user_validation_error(self, client):
        # Missing password field
        response = client.post("/api/v1/auth/register", json={"username": "invalid_payload"})
        assert response.status_code == 422  # Pydantic Validation error

    def test_login_success_returns_jwt(self, client, test_user):
        response = client.post(
            "/api/v1/auth/login", data={"username": "globaladmin", "password": "Globalpass1"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client, test_user):
        response = client.post(
            "/api/v1/auth/login", data={"username": "globaladmin", "password": "WrongPassword1"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect username or password"

    def test_login_nonexistent_user(self, client):
        response = client.post(
            "/api/v1/auth/login", data={"username": "does_not_exist", "password": "password"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect username or password"

    def test_login_sets_refresh_cookie_and_refresh_works(self, client, test_user):
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, "legacy-session", domain="testserver.local", path="/"
        )
        login_response = client.post(
            "/api/v1/auth/login", data={"username": "globaladmin", "password": "Globalpass1"}
        )

        assert login_response.status_code == 200
        assert REFRESH_COOKIE_NAME in login_response.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(login_response, LEGACY_REFRESH_COOKIE_NAME)

        refresh_response = client.post("/api/v1/auth/refresh")
        assert refresh_response.status_code == 200
        assert "access_token" in refresh_response.json()
        assert REFRESH_COOKIE_NAME in refresh_response.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies

    def test_refresh_migrates_legacy_cookie_without_duplicate_session(self, client, test_user):
        login_response = client.post(
            "/api/v1/auth/login", data={"username": "globaladmin", "password": "Globalpass1"}
        )
        legacy_token = login_response.cookies.get(REFRESH_COOKIE_NAME)
        client.cookies.clear()
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, legacy_token, domain="testserver.local", path="/"
        )

        refresh_response = client.post("/api/v1/auth/refresh")

        assert refresh_response.status_code == 200
        assert REFRESH_COOKIE_NAME in client.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(refresh_response, LEGACY_REFRESH_COOKIE_NAME)

    def test_logout_clears_refresh_cookie(self, client, test_user):
        login_response = client.post(
            "/api/v1/auth/login", data={"username": "globaladmin", "password": "Globalpass1"}
        )
        assert login_response.status_code == 200
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, "legacy-session", domain="testserver.local", path="/"
        )

        logout_response = client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 200
        assert REFRESH_COOKIE_NAME not in client.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(logout_response, REFRESH_COOKIE_NAME)
        assert _cookie_was_deleted(logout_response, LEGACY_REFRESH_COOKIE_NAME)
