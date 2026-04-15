"""Unit tests for AuthService.

authService.py creates module-level singletons (_jwtHandler, _loginLimiter,
_blacklist). Each test patches those singletons so the service logic can be
exercised without a real JWT stack or rate limiter state.
"""

import pytest
from unittest.mock import MagicMock, patch

from exceptions.baseExceptions import NoHarmException
from schemas.authSchemas import AuthLoginRequest, AuthRegisterRequest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_service(mock_db):
    """Instantiate AuthService and replace repos with MagicMocks."""
    from domain.services.authService import AuthService
    service = AuthService(mock_db)
    service.userRepository = MagicMock()
    service.auditRepository = MagicMock()
    return service


def _login_request(uid="uid-001", email="user@test.com"):
    return AuthLoginRequest(uid=uid, email=email)


def _register_request(uid="uid-001", email="new@test.com", username="newuser"):
    return AuthRegisterRequest(
        uid=uid, email=email, username=username, emailVerified=True
    )


# ── login ─────────────────────────────────────────────────────────────────────

def test_login_success(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler") as mock_jwt:

        mock_limiter.check.return_value = (True, None)
        mock_jwt.createAccessToken.return_value = "access-tok"
        mock_jwt.createRefreshToken.return_value = "refresh-tok"

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-001"
        mock_user.status = 1  # enabled
        service.userRepository.findById.return_value = mock_user

        result = service.login(_login_request())

        assert result["accessToken"] == "access-tok"
        assert result["refreshToken"] == "refresh-tok"
        assert result["tokenType"] == "Bearer"
        mock_limiter.onSuccess.assert_called_once_with("uid-001")


def test_login_user_not_found_raises_401(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())
        assert exc.value.statusCode == 401


def test_login_rate_limit_raises_429(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (False, "Account locked.")

        service = _make_service(mock_db)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())
        assert exc.value.statusCode == 429


def test_login_banned_user_raises_403(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-banned"
        mock_user.status = 9  # banned
        service.userRepository.findById.return_value = mock_user

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())
        assert exc.value.statusCode == 403


def test_login_blocked_user_raises_403(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-blocked"
        mock_user.status = 3  # blocked
        service.userRepository.findById.return_value = mock_user

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())
        assert exc.value.statusCode == 403


def test_login_deleted_user_raises_403(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-deleted"
        mock_user.status = 2  # deleted
        service.userRepository.findById.return_value = mock_user

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())
        assert exc.value.statusCode == 403


def test_login_creates_audit_log_on_success(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler") as mock_jwt:

        mock_limiter.check.return_value = (True, None)
        mock_jwt.createAccessToken.return_value = "tok"
        mock_jwt.createRefreshToken.return_value = "ref"

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-001"
        mock_user.status = 1
        service.userRepository.findById.return_value = mock_user

        service.login(_login_request())
        service.auditRepository.create.assert_called_once()


# ── refresh ───────────────────────────────────────────────────────────────────

def test_refresh_valid_token_returns_new_pair(mock_db):
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        mock_jwt.verifyToken.return_value = {
            "sub": "uid-001", "jti": "old-jti", "exp": 9999999999
        }
        mock_jwt.createAccessToken.return_value = "new-access"
        mock_jwt.createRefreshToken.return_value = "new-refresh"

        service = _make_service(mock_db)
        result = service.refresh("valid-refresh-token")

        assert result["accessToken"] == "new-access"
        assert result["refreshToken"] == "new-refresh"
        mock_jwt.revokeToken.assert_called_once_with("old-jti", 9999999999)


def test_refresh_invalid_token_raises_401(mock_db):
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        mock_jwt.verifyToken.return_value = None  # invalid / expired

        service = _make_service(mock_db)
        with pytest.raises(NoHarmException) as exc:
            service.refresh("bad-token")
        assert exc.value.statusCode == 401


# ── logout ────────────────────────────────────────────────────────────────────

def test_logout_revokes_both_tokens(mock_db):
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        access_payload = {"sub": "uid-001", "jti": "jti-access", "exp": 1111}
        refresh_payload = {"sub": "uid-001", "jti": "jti-refresh", "exp": 2222}

        def verify_side_effect(token, token_type):
            if token_type == "access":
                return access_payload
            return refresh_payload

        mock_jwt.verifyToken.side_effect = verify_side_effect

        service = _make_service(mock_db)
        service.logout("access-tok", "refresh-tok")

        assert mock_jwt.revokeToken.call_count == 2


def test_logout_handles_invalid_tokens_gracefully(mock_db):
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        mock_jwt.verifyToken.return_value = None  # both tokens invalid

        service = _make_service(mock_db)
        # Should not raise
        service.logout("bad-access", "bad-refresh")
        mock_jwt.revokeToken.assert_not_called()


# ── register ──────────────────────────────────────────────────────────────────

def test_register_success_returns_tokens(mock_db):
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        mock_jwt.createAccessToken.return_value = "access"
        mock_jwt.createRefreshToken.return_value = "refresh"

        service = _make_service(mock_db)
        # email and username not taken → repos raise 404
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        result = service.register(_register_request())

        assert result["accessToken"] == "access"
        service.userRepository.create.assert_called_once()


def test_register_invalid_username_raises_400(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        # 3 chars satisfies Pydantic min_length, but '!' fails the service regex
        req = _register_request(username="a!b")

        with pytest.raises(NoHarmException) as exc:
            service.register(req)
        assert exc.value.statusCode == 400


def test_register_duplicate_email_raises_409(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        existing = MagicMock()
        service.userRepository.findByEmail.return_value = existing  # exists

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request())
        assert exc.value.statusCode == 409


def test_register_duplicate_username_raises_409(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.return_value = MagicMock()  # exists

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request())
        assert exc.value.statusCode == 409
