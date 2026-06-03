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


def _make_friendship_dict():
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "sender": uuid4(),
        "reciver": uuid4(),
        "send_at": now,
        "recived_at": now,
        "status": 4,
        "created_at": now,
        "updated_at": now,
    }


def _build_app():
    from api.routes.friendshipRoutes import router
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


class TestGetMyFriendshipsRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.getAll.return_value = []
            res = client.get("/friendships")
        assert res.status_code == 200

    def test_response_has_friendships_key(self, client):
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.getAll.return_value = []
            res = client.get("/friendships")
        assert "friendships" in res.json()


class TestGetPendingReceivedRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.getPendingReceived.return_value = []
            res = client.get("/friendships/pending")
        assert res.status_code == 200


class TestGetPendingSentRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.getPendingSent.return_value = []
            res = client.get("/friendships/sent")
        assert res.status_code == 200


class TestSendFriendRequestRoute:
    def test_success_returns_201(self, client):
        receiver = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.sendRequest.return_value = _make_friendship_dict()
            res = client.post(f"/friendships/{receiver}")
        assert res.status_code == 201

    def test_already_friends_returns_409(self, client):
        receiver = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.sendRequest.side_effect = NoHarmException(
                statusCode=409, errorCode="CONFLICT", message="Friendship already exists."
            )
            res = client.post(f"/friendships/{receiver}")
        assert res.status_code == 409

    def test_blocked_returns_403(self, client):
        receiver = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.sendRequest.side_effect = NoHarmException(
                statusCode=403, errorCode="BLOCKED", message="Cannot send request."
            )
            res = client.post(f"/friendships/{receiver}")
        assert res.status_code == 403

    def test_self_request_returns_400(self, client):
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.sendRequest.side_effect = NoHarmException(
                statusCode=400, errorCode="BAD_REQUEST", message="Cannot befriend yourself."
            )
            res = client.post(f"/friendships/{_USER_ID}")
        assert res.status_code == 400


class TestAcceptFriendRequestRoute:
    def test_success_returns_200(self, client):
        fid = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.accept.return_value = _make_friendship_dict()
            res = client.post(f"/friendships/{fid}/accept")
        assert res.status_code == 200

    def test_not_participant_returns_403(self, client):
        fid = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.accept.side_effect = NoHarmException(
                statusCode=403, errorCode="ACCESS_DENIED", message="Not a participant."
            )
            res = client.post(f"/friendships/{fid}/accept")
        assert res.status_code == 403


class TestRejectFriendRequestRoute:
    def test_success_returns_200(self, client):
        fid = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.reject.return_value = _make_friendship_dict()
            res = client.post(f"/friendships/{fid}/reject")
        assert res.status_code == 200


class TestBlockUserRoute:
    def test_success_returns_200(self, client):
        fid = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.block.return_value = _make_friendship_dict()
            res = client.post(f"/friendships/{fid}/block")
        assert res.status_code == 200


class TestDeleteFriendshipRoute:
    def test_success_returns_200(self, client):
        fid = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.delete.return_value = True
            res = client.delete(f"/friendships/{fid}")
        assert res.status_code == 200

    def test_not_found_returns_404(self, client):
        fid = str(uuid4())
        with patch("api.routes.friendshipRoutes.FriendshipService") as MockService:
            MockService.return_value.delete.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="Friendship not found."
            )
            res = client.delete(f"/friendships/{fid}")
        assert res.status_code == 404
