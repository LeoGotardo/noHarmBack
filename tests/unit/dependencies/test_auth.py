import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


def _build_app():
    from api.dependencies.auth import getCurrentUser
    app = FastAPI()

    @app.get("/protected")
    def protected(userId: str = Depends(getCurrentUser)):
        return {"userId": userId}

    return app


class TestGetCurrentUser:
    def test_valid_token_returns_user_id(self):
        with patch("api.dependencies.auth.jwtHandler") as mock_jwt:
            mock_jwt.verifyToken.return_value = {"sub": "user-123"}
            client = TestClient(_build_app(), raise_server_exceptions=False)
            res = client.get(
                "/protected",
                headers={"Authorization": "Bearer valid.token.here"}
            )
        assert res.status_code == 200
        assert res.json()["userId"] == "user-123"

    def test_invalid_token_returns_401(self):
        with patch("api.dependencies.auth.jwtHandler") as mock_jwt:
            mock_jwt.verifyToken.return_value = None
            client = TestClient(_build_app(), raise_server_exceptions=False)
            res = client.get(
                "/protected",
                headers={"Authorization": "Bearer bad.token.value"}
            )
        assert res.status_code == 401

    def test_missing_auth_header_returns_4xx(self):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        res = client.get("/protected")
        assert res.status_code in (401, 403)

    def test_verifyToken_called_with_correct_type(self):
        with patch("api.dependencies.auth.jwtHandler") as mock_jwt:
            mock_jwt.verifyToken.return_value = {"sub": "uid"}
            client = TestClient(_build_app(), raise_server_exceptions=False)
            client.get("/protected", headers={"Authorization": "Bearer tok"})
            mock_jwt.verifyToken.assert_called_once_with("tok", "access")

    def test_returns_sub_claim_from_payload(self):
        with patch("api.dependencies.auth.jwtHandler") as mock_jwt:
            mock_jwt.verifyToken.return_value = {"sub": "specific-uid-xyz", "jti": "irrelevant"}
            client = TestClient(_build_app(), raise_server_exceptions=False)
            res = client.get("/protected", headers={"Authorization": "Bearer t"})
        assert res.json()["userId"] == "specific-uid-xyz"
