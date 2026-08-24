"""Unit tests for JwtHandler."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

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
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=16),
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


# ── type confusion ────────────────────────────────────────────────────────────
#
# The two tests above ("wrong type", "refresh as access") pass on the *signature*
# check: access and refresh are signed with different keys, so decode fails
# before _hasValidType is ever consulted. Replacing that method with
# `return True` left the whole suite green. These forge the token with the
# correct key so the type claim is the only thing that can reject it.

def _forge(claims, secret):
    from core.config import config
    base = {
        "sub": "user-1",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iat": datetime.now(timezone.utc),
        "jti": "forged-jti",
    }
    base.update(claims)
    key = config.JWT_SECRET_KEY if secret == "access" else config.JWT_REFRESH_SECRET_KEY
    return pyjwt.encode(base, key, algorithm="HS256")


def test_verifyToken_refresh_claim_signed_with_access_key_is_rejected(handler):
    """A correctly signed token still fails if its `type` is not the expected one."""
    token = _forge({"type": "refresh"}, secret="access")
    assert handler.verifyToken(token, "access") is None


def test_verifyToken_access_claim_signed_with_refresh_key_is_rejected(handler):
    token = _forge({"type": "access"}, secret="refresh")
    assert handler.verifyToken(token, "refresh") is None


def test_verifyToken_unknown_type_claim_is_rejected(handler):
    token = _forge({"type": "admin"}, secret="access")
    assert handler.verifyToken(token, "access") is None


def test_verifyToken_matching_type_is_accepted(handler):
    """Control for the three above: same forgery, right type, must pass."""
    token = _forge({"type": "access"}, secret="access")
    assert handler.verifyToken(token, "access") is not None


# ── algorithm and claim tampering ─────────────────────────────────────────────

def test_verifyToken_alg_none_is_rejected(handler):
    """An unsigned token must never authenticate anyone."""
    import base64, json

    def b64(raw):
        return base64.urlsafe_b64encode(json.dumps(raw).encode()).rstrip(b"=").decode()

    header = b64({"alg": "none", "typ": "JWT"})
    payload = b64({
        "sub": "attacker", "type": "access", "jti": "x",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    })
    assert handler.verifyToken(f"{header}.{payload}.", "access") is None


def test_verifyToken_signed_with_wrong_secret_is_rejected(handler):
    token = pyjwt.encode(
        {
            "sub": "attacker", "type": "access", "jti": "x",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        "an-attacker-chosen-secret",
        algorithm="HS256",
    )
    assert handler.verifyToken(token, "access") is None


@pytest.mark.parametrize("missing", ["sub", "type", "exp", "iat", "jti"])
def test_verifyToken_missing_required_claim_is_rejected(handler, missing):
    from core.config import config
    claims = {
        "sub": "user-1", "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iat": datetime.now(timezone.utc),
        "jti": "some-jti",
    }
    del claims[missing]
    token = pyjwt.encode(claims, config.JWT_SECRET_KEY, algorithm="HS256")
    assert handler.verifyToken(token, "access") is None


def test_secretForType_rejects_unknown_type(handler):
    with pytest.raises(ValueError):
        handler._secretForType("admin")


# ── revocation against a real blacklist ───────────────────────────────────────
#
# The previous revocation test set `mock_blacklist.isBlacklisted.return_value =
# True` by hand after calling revokeToken, so it asserted that a MagicMock
# returns what the test told it to. These run the real TokenBlacklist over
# fakeredis, which also covers the naive-datetime TTL path — the one
# revokeToken always takes, since it strips tzinfo before handing `exp` over.

@pytest.fixture
def real_blacklist():
    import fakeredis
    from security.tokenBlacklist import TokenBlacklist
    bl = TokenBlacklist.__new__(TokenBlacklist)
    bl._redis = fakeredis.FakeStrictRedis(decode_responses=True)
    return bl


def test_revoked_token_stops_verifying(real_blacklist):
    from core.config import config
    handler = JwtHandler(real_blacklist)
    token = handler.createAccessToken("user-1")
    assert handler.verifyToken(token, "access") is not None

    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    handler.revokeToken(payload["jti"], payload["exp"])

    assert handler.verifyToken(token, "access") is None


def test_revoking_one_token_leaves_the_others_valid(real_blacklist):
    from core.config import config
    handler = JwtHandler(real_blacklist)
    revoked = handler.createAccessToken("user-1")
    kept = handler.createAccessToken("user-1")

    payload = pyjwt.decode(revoked, config.JWT_SECRET_KEY, algorithms=["HS256"])
    handler.revokeToken(payload["jti"], payload["exp"])

    assert handler.verifyToken(revoked, "access") is None
    assert handler.verifyToken(kept, "access") is not None


def test_revocation_sets_a_positive_ttl(real_blacklist):
    """revokeToken hands `add` a naive datetime. If the naive branch in
    TokenBlacklist.add stopped tagging it UTC, the TTL would compute negative
    and the write would be skipped — revocation silently becoming a no-op."""
    from core.config import config
    handler = JwtHandler(real_blacklist)
    token = handler.createAccessToken("user-1")
    payload = pyjwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])

    handler.revokeToken(payload["jti"], payload["exp"])

    key = "jti:" + real_blacklist._hash(payload["jti"])
    assert real_blacklist._redis.ttl(key) > 0
