"""Unit tests for the getCurrentUser dependency.

Two things are being verified here, and the second one used to be untestable:

  1. Token handling — signature/expiry rejection comes back as 401.
  2. Account state (§1.4) — a still-valid access token must stop working the
     moment the account is deleted, banned or blocked.

(2) needs `getAccountStatus`, which reads through the module-level `database`
singleton. The root conftest replaces `core.database` with a MagicMock, so the
`scalar()` call returned a MagicMock that is neither None nor a rejected status
— every account looked enabled and the whole check was unreachable. Patching
`api.dependencies.auth.database` per test restores control over what the DB
says.
"""

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from core.config import config


def _build_app():
    from api.dependencies.auth import getCurrentUser
    app = FastAPI()

    @app.get("/protected")
    def protected(userId: str = Depends(getCurrentUser)):
        return {"userId": userId}

    return app


@contextmanager
def _account(status):
    """Make getAccountStatus report `status` (None = row is gone)."""
    session = MagicMock()
    session.query.return_value.filter.return_value.scalar.return_value = status
    db = MagicMock()
    db.session = session
    with patch("api.dependencies.auth.database", db), \
         patch("api.dependencies.auth.RLSContext"):
        yield session


@contextmanager
def _token(payload):
    with patch("api.dependencies.auth.jwtHandler") as mock_jwt:
        mock_jwt.verifyToken.return_value = payload
        yield mock_jwt


def _get(headers=None):
    client = TestClient(_build_app(), raise_server_exceptions=False)
    return client.get("/protected", headers=headers or {})


_ENABLED = config.STATUS_CODES["enabled"]


class TestTokenHandling:
    def test_valid_token_returns_user_id(self):
        with _token({"sub": "user-123"}), _account(_ENABLED):
            res = _get({"Authorization": "Bearer valid.token.here"})
        assert res.status_code == 200
        assert res.json()["userId"] == "user-123"

    def test_invalid_token_returns_401(self):
        with _token(None), _account(_ENABLED):
            res = _get({"Authorization": "Bearer bad.token.value"})
        assert res.status_code == 401

    def test_missing_auth_header_returns_4xx(self):
        res = _get()
        assert res.status_code in (401, 403)

    def test_verifyToken_called_with_correct_type(self):
        with _token({"sub": "uid"}) as mock_jwt, _account(_ENABLED):
            _get({"Authorization": "Bearer tok"})
        mock_jwt.verifyToken.assert_called_once_with("tok", "access")

    def test_returns_sub_claim_from_payload(self):
        with _token({"sub": "specific-uid-xyz", "jti": "irrelevant"}), _account(_ENABLED):
            res = _get({"Authorization": "Bearer t"})
        assert res.json()["userId"] == "specific-uid-xyz"


class TestAccountState:
    """§1.4 — a signature check alone let dead accounts keep using live tokens."""

    def test_enabled_account_passes(self):
        with _token({"sub": "uid-ok"}), _account(_ENABLED):
            res = _get({"Authorization": "Bearer t"})
        assert res.status_code == 200

    def test_pending_account_passes(self):
        """Unverified email still gets in — only the rejected states are blocked."""
        with _token({"sub": "uid-pending"}), _account(config.STATUS_CODES["pending"]):
            res = _get({"Authorization": "Bearer t"})
        assert res.status_code == 200

    def test_missing_row_returns_401(self):
        """Row gone (hard-deleted) → the token identifies nobody."""
        with _token({"sub": "uid-gone"}), _account(None):
            res = _get({"Authorization": "Bearer t"})
        assert res.status_code == 401

    @pytest.mark.parametrize(
        "state, expected_detail",
        [
            ("deleted", "Account not found."),
            ("banned",  "Account is banned."),
            ("blocked", "Account is blocked."),
        ],
    )
    def test_rejected_states_return_403(self, state, expected_detail):
        with _token({"sub": f"uid-{state}"}), _account(config.STATUS_CODES[state]):
            res = _get({"Authorization": "Bearer t"})
        assert res.status_code == 403
        assert res.json()["detail"] == expected_detail

    def test_status_is_looked_up_for_the_token_subject(self):
        """The status must be read for the token's own sub, not some other row."""
        with _token({"sub": "uid-777"}), _account(_ENABLED), \
             patch("api.dependencies.auth.RLSContext") as mock_rls:
            _get({"Authorization": "Bearer t"})
        # RLS context is set to the same subject before the read
        assert mock_rls.setUserId.call_args[0][1] == "uid-777"

    def test_session_is_closed_even_when_rejected(self):
        with _token({"sub": "uid-banned"}), _account(config.STATUS_CODES["banned"]) as session:
            _get({"Authorization": "Bearer t"})
        session.close.assert_called_once()
