import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

from exceptions.baseExceptions import NoHarmException


_USER_ID = str(uuid4())


def _make_user_mock():
    u = MagicMock()
    u.id = _USER_ID
    u.username = "testuser"
    u.email = "test@example.com"
    u.status = 1
    u.profile_picture = None
    u.created_at = datetime.now(timezone.utc)
    u.updated_at = datetime.now(timezone.utc)
    return u


def _build_app():
    from api.routes.userRoutes import router
    from api.dependencies.database import getDbWithRLS
    from api.dependencies.auth import getCurrentUser

    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(router)
    app.dependency_overrides[getDbWithRLS] = lambda: MagicMock()
    app.dependency_overrides[getCurrentUser] = lambda: _USER_ID
    return app


@pytest.fixture
def client():
    return TestClient(_build_app(), raise_server_exceptions=False)


class TestGetMyProfileRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.getProfile.return_value = _make_user_mock()
            res = client.get("/users/me")
        assert res.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.getProfile.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="User not found."
            )
            res = client.get("/users/me")
        assert res.status_code == 404

    def test_response_contains_username(self, client):
        mock_user = _make_user_mock()
        mock_user.username = "specificuser"
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.getProfile.return_value = mock_user
            res = client.get("/users/me")
        assert res.json()["username"] == "specificuser"


class TestUpdateMyProfileRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.updateProfile.return_value = _make_user_mock()
            res = client.put("/users/me", json={"username": "newname"})
        assert res.status_code == 200

    def test_conflict_returns_409(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.updateProfile.side_effect = NoHarmException(
                statusCode=409, errorCode="CONFLICT", message="Username taken."
            )
            res = client.put("/users/me", json={"username": "taken"})
        assert res.status_code == 409

    def test_empty_body_is_valid(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.updateProfile.return_value = _make_user_mock()
            res = client.put("/users/me", json={})
        assert res.status_code == 200


class TestGetPublicProfileRoute:
    def test_success_returns_200(self, client):
        target = str(uuid4())
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.getPublicProfile.return_value = _make_user_mock()
            res = client.get(f"/users/{target}")
        assert res.status_code == 200

    def test_blocked_returns_403(self, client):
        target = str(uuid4())
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.getPublicProfile.side_effect = NoHarmException(
                statusCode=403, errorCode="ACCESS_DENIED", message="Profile not accessible."
            )
            res = client.get(f"/users/{target}")
        assert res.status_code == 403

    def test_not_found_returns_404(self, client):
        target = str(uuid4())
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.getPublicProfile.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="User not found."
            )
            res = client.get(f"/users/{target}")
        assert res.status_code == 404


class TestGetAllUsersRoute:
    def test_returns_200_with_list(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.findAll.return_value = []
            res = client.get("/users")
        assert res.status_code == 200


class TestUpdateUserStatusRoute:
    def test_success_returns_200(self, client):
        uid = str(uuid4())
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.updateStatus.return_value = _make_user_mock()
            res = client.put(f"/users/{uid}/status/2")
        assert res.status_code == 200

    def test_not_found_returns_404(self, client):
        uid = str(uuid4())
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.updateStatus.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="User not found."
            )
            res = client.put(f"/users/{uid}/status/2")
        assert res.status_code == 404


class TestDeleteUserRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.userRoutes.UserService") as MockService:
            MockService.return_value.delete.return_value = True
            res = client.delete("/users/me")
        assert res.status_code == 200
