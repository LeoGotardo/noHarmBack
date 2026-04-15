"""Unit tests for JwtHandler."""

import time
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import jwt as pyjwt

from security.jwtHandler import JwtHandler
from security.tokenBlacklist import TokenBlacklist


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_blacklist():
    bl = MagicMock(spec=TokenBlacklist)
    bl.isBlacklisted.return_value = False
    return bl


@pytest.fixture
def handler(mock_blacklist):
    return JwtHandler(mock_blacklist)


# ── createAccessToken ─────────────────────────────────────────────────────────

def test_createAccessToken_returns_string(handler):
    token = handler.createAccessToken("user-123")
    assert isinstance(token, str)
    assert len(token) > 0


def test_createAccessToken_has_required_claims(handler):
    from core.config import config
    token = handler.createAccessToken("user-123")
    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    for claim in ["sub", "type", "exp", "iat", "jti"]:
        assert claim in payload


def test_createAccessToken_type_is_access(handler):
    from core.config import config
    token = handler.createAccessToken("user-abc")
    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload["type"] == "access"


def test_createAccessToken_sub_matches_user_id(handler):
    from core.config import config
    token = handler.createAccessToken("user-xyz")
    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == "user-xyz"


def test_createAccessToken_unique_jti_per_call(handler):
    from core.config import config
    t1 = handler.createAccessToken("user-1")
    t2 = handler.createAccessToken("user-1")
    p1 = pyjwt.decode(t1, config.JWT_SECRET_KEY, algorithms=["HS256"])
    p2 = pyjwt.decode(t2, config.JWT_SECRET_KEY, algorithms=["HS256"])
    assert p1["jti"] != p2["jti"]


# ── createRefreshToken ────────────────────────────────────────────────────────

def test_createRefreshToken_type_is_refresh(handler):
    from core.config import config
    token = handler.createRefreshToken("user-123")
    payload = pyjwt.decode(token, config.JWT_REFRESH_SECRET_KEY, algorithms=["HS256"])
    assert payload["type"] == "refresh"


def test_createRefreshToken_longer_expiry_than_access(handler):
    from core.config import config
    access = handler.createAccessToken("user-1")
    refresh = handler.createRefreshToken("user-1")
    pa = pyjwt.decode(access, config.JWT_SECRET_KEY, algorithms=["HS256"])
    pr = pyjwt.decode(refresh, config.JWT_REFRESH_SECRET_KEY, algorithms=["HS256"])
    assert pr["exp"] > pa["exp"]


# ── verifyToken ───────────────────────────────────────────────────────────────

def test_verifyToken_valid_access_token(handler):
    token = handler.createAccessToken("user-123")
    payload = handler.verifyToken(token, "access")
    assert payload is not None
    assert payload["sub"] == "user-123"


def test_verifyToken_valid_refresh_token(handler):
    token = handler.createRefreshToken("user-123")
    payload = handler.verifyToken(token, "refresh")
    assert payload is not None
    assert payload["sub"] == "user-123"


def test_verifyToken_expired_returns_none(mock_blacklist):
    """Forge an already-expired token to verify None is returned."""
    from core.config import config
    handler = JwtHandler(mock_blacklist)
    expired_payload = {
        "sub": "user-1",
        "type": "access",
        "exp": datetime.utcnow() - timedelta(seconds=1),
        "iat": datetime.utcnow() - timedelta(minutes=16),
        "jti": "expired-jti",
    }
    expired_token = pyjwt.encode(expired_payload, config.JWT_SECRET_KEY, algorithm="HS256")
    assert handler.verifyToken(expired_token, "access") is None


def test_verifyToken_wrong_type_returns_none(handler):
    """Access token rejected when expected type is 'refresh'."""
    access_token = handler.createAccessToken("user-1")
    assert handler.verifyToken(access_token, "refresh") is None


def test_verifyToken_refresh_as_access_returns_none(handler):
    refresh_token = handler.createRefreshToken("user-1")
    assert handler.verifyToken(refresh_token, "access") is None


def test_verifyToken_tampered_signature_returns_none(handler):
    token = handler.createAccessToken("user-1")
    # Replace the signature (3rd JWT segment) with garbage bytes
    header, payload, _ = token.split(".")
    tampered = f"{header}.{payload}.invalidsignatureXXXXXXXXXXXXXXXX"
    assert handler.verifyToken(tampered, "access") is None


def test_verifyToken_blacklisted_returns_none(handler, mock_blacklist):
    token = handler.createAccessToken("user-1")
    mock_blacklist.isBlacklisted.return_value = True
    assert handler.verifyToken(token, "access") is None


def test_verifyToken_returns_payload_dict(handler):
    token = handler.createAccessToken("user-1")
    payload = handler.verifyToken(token, "access")
    assert isinstance(payload, dict)


# ── revokeToken ───────────────────────────────────────────────────────────────

def test_revokeToken_calls_blacklist_add(handler, mock_blacklist):
    token = handler.createAccessToken("user-1")
    from core.config import config
    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    handler.revokeToken(payload["jti"], payload["exp"])
    mock_blacklist.add.assert_called_once()


def test_revokeToken_then_verify_returns_none(mock_blacklist):
    """After revocation, verify must return None (blacklist returns True)."""
    handler = JwtHandler(mock_blacklist)
    token = handler.createAccessToken("user-1")

    from core.config import config
    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    handler.revokeToken(payload["jti"], payload["exp"])

    mock_blacklist.isBlacklisted.return_value = True
    assert handler.verifyToken(token, "access") is None
