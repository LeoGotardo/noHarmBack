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


def _make_streak_mock():
    now = datetime.now(timezone.utc)
    s = MagicMock()
    s.id = uuid4()
    s.owner_id = _USER_ID
    s.start_at = now
    s.end_at = None
    s.last_checkin = None
    s.status = 1
    s.is_record = False
    s.created_at = now
    s.updated_at = now
    return s


def _build_app():
    from api.routes.streakRoutes import router
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


class TestGetCurrentStreakRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.getCurrentByUserId.return_value = _make_streak_mock()
            res = client.get("/streaks/current")
        assert res.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.getCurrentByUserId.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="No active streak."
            )
            res = client.get("/streaks/current")
        assert res.status_code == 404


class TestGetRecordStreakRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.getRecordByUserId.return_value = _make_streak_mock()
            res = client.get("/streaks/record")
        assert res.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.getRecordByUserId.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="No record streak."
            )
            res = client.get("/streaks/record")
        assert res.status_code == 404


class TestGetStreakHistoryRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.getAllByUserId.return_value = []
            res = client.get("/streaks/history")
        assert res.status_code == 200


class TestStartStreakRoute:
    def test_success_returns_201(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.startStreak.return_value = _make_streak_mock()
            res = client.post("/streaks/start")
        assert res.status_code == 201

    def test_already_active_returns_409(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.startStreak.side_effect = NoHarmException(
                statusCode=409, errorCode="CONFLICT", message="Active streak already exists."
            )
            res = client.post("/streaks/start")
        assert res.status_code == 409


class TestEndStreakRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.endStreak.return_value = _make_streak_mock()
            res = client.post("/streaks/end")
        assert res.status_code == 200

    def test_no_active_streak_returns_404(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.endStreak.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="No active streak to end."
            )
            res = client.post("/streaks/end")
        assert res.status_code == 404


class TestCheckinRoute:
    def test_success_returns_200(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.checkin.return_value = _make_streak_mock()
            res = client.post("/streaks/checkin")
        assert res.status_code == 200

    def test_no_active_streak_returns_404(self, client):
        with patch("api.routes.streakRoutes.StreakService") as MockService:
            MockService.return_value.checkin.side_effect = NoHarmException(
                statusCode=404, errorCode="NOT_FOUND", message="No active streak."
            )
            res = client.post("/streaks/checkin")
        assert res.status_code == 404
