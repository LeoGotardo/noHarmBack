"""Route-level tests for /auth endpoints.

Uses FastAPI TestClient with dependency overrides to avoid real DB/JWT.
Patches AuthService at the module level inside the route handler.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from exceptions.baseExceptions import NoHarmException


def _build_app():
    from api.routes.authRoutes import router
    from api.dependencies.database import getDb

    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(router)
    app.dependency_overrides[getDb] = lambda: MagicMock()

    return app


@pytest.fixture
def client():
    return TestClient(_build_app(), raise_server_exceptions=False)


# The body carries the Firebase ID token and nothing else about who the user
# is; AuthService is mocked here, so its contents never have to be valid.
_VALID_LOGIN = {"idToken": "id-token"}
_VALID_REGISTER = {"idToken": "id-token", "username": "newuser"}


class TestLoginRoute:
    def test_login_success_returns_200(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.login.return_value = {
                "accessToken": "acc", "refreshToken": "ref", "tokenType": "Bearer"
            }
            res = client.post("/auth/login", json=_VALID_LOGIN)
        assert res.status_code == 200
        assert res.json()["accessToken"] == "acc"

    def test_login_invalid_credentials_returns_401(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.login.side_effect = NoHarmException(
                statusCode=401, errorCode="INVALID_CREDENTIALS", message="Invalid credentials."
            )
            res = client.post("/auth/login", json=_VALID_LOGIN)
        assert res.status_code == 401

    def test_login_banned_returns_403(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.login.side_effect = NoHarmException(
                statusCode=403, errorCode="ACCOUNT_BANNED", message="Account is banned."
            )
            res = client.post("/auth/login", json=_VALID_LOGIN)
        assert res.status_code == 403

    def test_login_missing_id_token_returns_422(self, client):
        res = client.post("/auth/login", json={})
        assert res.status_code == 422

    def test_login_with_uid_instead_of_token_returns_422(self, client):
        # The shape the API used to accept. Rejecting it is the whole point:
        # a bare UID is not proof of anything.
        res = client.post("/auth/login", json={"uid": "uid-001", "email": "u@t.com"})
        assert res.status_code == 422

    def test_login_rate_limit_returns_429(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.login.side_effect = NoHarmException(
                statusCode=429, errorCode="TOO_MANY_REQUESTS", message="Locked."
            )
            res = client.post("/auth/login", json=_VALID_LOGIN)
        assert res.status_code == 429


class TestRegisterRoute:
    def test_register_success_returns_201(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.register.return_value = {
                "accessToken": "acc", "refreshToken": "ref", "tokenType": "Bearer"
            }
            res = client.post("/auth/register", json=_VALID_REGISTER)
        assert res.status_code == 201

    def test_register_duplicate_returns_409(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.register.side_effect = NoHarmException(
                statusCode=409, errorCode="CONFLICT", message="Already exists."
            )
            res = client.post("/auth/register", json=_VALID_REGISTER)
        assert res.status_code == 409

    def test_register_invalid_username_short_returns_422(self, client):
        payload = {**_VALID_REGISTER, "username": "ab"}
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 422

    def test_register_missing_id_token_returns_422(self, client):
        res = client.post("/auth/register", json={"username": "user"})
        assert res.status_code == 422

    def test_register_with_uid_instead_of_token_returns_422(self, client):
        res = client.post(
            "/auth/register",
            json={"uid": "uid-001", "email": "u@t.com", "username": "newuser",
                  "emailVerified": True},
        )
        assert res.status_code == 422


class TestRefreshRoute:
    def test_refresh_success(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.refresh.return_value = {
                "accessToken": "new-acc", "refreshToken": "new-ref", "tokenType": "Bearer"
            }
            res = client.post("/auth/refresh", json={"refreshToken": "valid-token"})
        assert res.status_code == 200
        assert res.json()["accessToken"] == "new-acc"

    def test_refresh_invalid_token_returns_401(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.refresh.side_effect = NoHarmException(
                statusCode=401, errorCode="INVALID_TOKEN", message="Invalid token."
            )
            res = client.post("/auth/refresh", json={"refreshToken": "bad"})
        assert res.status_code == 401

    def test_refresh_missing_token_returns_422(self, client):
        res = client.post("/auth/refresh", json={})
        assert res.status_code == 422


class TestLogoutRoute:
    def test_logout_success_returns_204(self, client):
        with patch("api.routes.authRoutes.AuthService") as MockService:
            MockService.return_value.logout.return_value = None
            res = client.post(
                "/auth/logout",
                json={"refreshToken": "ref"},
                headers={"Authorization": "Bearer valid-token"},
            )
        assert res.status_code == 204

    def test_logout_missing_auth_header_returns_401(self, client):
        res = client.post("/auth/logout", json={"refreshToken": "ref"})
        assert res.status_code == 401
