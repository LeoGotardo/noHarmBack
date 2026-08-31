"""Unit tests for AuthService.

authService.py creates module-level singletons (_jwtHandler, _loginLimiter,
_blacklist). Each test patches those singletons so the service logic can be
exercised without a real JWT stack or rate limiter state.

Firebase is stubbed the same way, by `stub_firebase` below: the identity a
token resolves to is encoded in the token string itself, so a test can pick a
UID without a Firebase project existing. What that stub replaces —
signature, audience and issuer — is covered in
`tests/unit/security/test_firebaseIdentity.py`.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from core.config import config
from exceptions.baseExceptions import NoHarmException
from schemas.authSchemas import AuthLoginRequest, AuthRegisterRequest


# ── helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def stub_firebase():
    """Resolve a fake ID token to the identity encoded in it.

    Autouse: every path through login and register starts with verification
    now, so a test that forgot it would fail on a Firebase app that does not
    exist rather than on what it is asserting.
    """
    from security.firebaseIdentity import FirebaseIdentity

    def _verify(idToken):
        claims = json.loads(idToken)
        return FirebaseIdentity(
            uid=claims["uid"],
            email=claims.get("email"),
            emailVerified=claims.get("emailVerified", True),
            picture=claims.get("picture"),
        )

    with patch("domain.services.authService.verifyIdToken", side_effect=_verify) as mock:
        yield mock


def _make_service(mock_db):
    """Instantiate AuthService and replace repos with MagicMocks."""
    from domain.services.authService import AuthService
    service = AuthService(mock_db)
    service.userRepository = MagicMock()
    service.auditRepository = MagicMock()
    return service


def _token(uid="uid-001", email="user@test.com", **claims):
    """A token the `stub_firebase` fixture knows how to resolve."""
    return json.dumps({"uid": uid, "email": email, **claims})


def _login_request(uid="uid-001", email="user@test.com"):
    return AuthLoginRequest(idToken=_token(uid, email))


def _register_request(uid="uid-001", email="new@test.com", username="newuser", **claims):
    return AuthRegisterRequest(idToken=_token(uid, email, **claims), username=username)


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
        mock_user.status = config.STATUS_CODES["enabled"]
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
        mock_user.status = config.STATUS_CODES["banned"]
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
        mock_user.status = config.STATUS_CODES["blocked"]
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
        mock_user.status = config.STATUS_CODES["deleted"]
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
        mock_user.status = config.STATUS_CODES["enabled"]
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
        # uid, email and username not taken → repos raise 404
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
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
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        existing = MagicMock()
        service.userRepository.findByEmail.return_value = existing  # exists

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request())
        assert exc.value.statusCode == 409


def test_register_duplicate_username_raises_409(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.return_value = MagicMock()  # exists

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request())
        assert exc.value.statusCode == 409


# ── identity comes from the token, not the body ───────────────────────────────

def test_login_uses_uid_from_verified_token(mock_db, stub_firebase):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler") as mock_jwt:

        mock_limiter.check.return_value = (True, None)
        mock_jwt.createAccessToken.return_value = "acc"
        mock_jwt.createRefreshToken.return_value = "ref"

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-from-token"
        mock_user.status = config.STATUS_CODES["enabled"]
        service.userRepository.findById.return_value = mock_user

        service.login(_login_request(uid="uid-from-token"))

        service.userRepository.findById.assert_called_once_with("uid-from-token")


def test_login_rejected_token_propagates_401(mock_db, stub_firebase):
    stub_firebase.side_effect = NoHarmException(
        statusCode=401, errorCode="INVALID_TOKEN", message="Invalid credentials."
    )

    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())

        assert exc.value.statusCode == 401
        # Nothing was looked up: an unverified token never reaches the database,
        # and it must not consume the per-UID rate-limit budget either.
        service.userRepository.findById.assert_not_called()
        mock_limiter.check.assert_not_called()


def test_register_stores_uid_and_email_from_token(mock_db):
    # UserModel is mocked out by the unit conftest, so the built row keeps no
    # attributes — the kwargs it was constructed with are the assertion.
    with patch("domain.services.authService._jwtHandler") as mock_jwt, \
         patch("domain.services.authService.UserModel") as MockUserModel:
        mock_jwt.createAccessToken.return_value = "acc"
        mock_jwt.createRefreshToken.return_value = "ref"

        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        service.register(_register_request(
            uid="uid-claimed", email="claimed@test.com", picture="https://pic"
        ))

        built = MockUserModel.call_args.kwargs
        assert built["id"] == "uid-claimed"
        assert built["email"] == "claimed@test.com"
        assert built["profile_picture"] == "https://pic"


def test_register_unverified_email_stays_pending(mock_db):
    with patch("domain.services.authService._jwtHandler"), \
         patch("domain.services.authService.UserModel") as MockUserModel:
        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        # The client used to send this flag. From the claims it cannot be
        # self-declared, so an unverified Google account cannot skip `pending`.
        service.register(_register_request(emailVerified=False))

        assert MockUserModel.call_args.kwargs["status"] == config.STATUS_CODES["pending"]


def test_register_duplicate_uid_raises_409(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findById.return_value = MagicMock()  # already registered

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request())
        assert exc.value.statusCode == 409


def test_register_without_email_claim_raises_400(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request(email=None))
        assert exc.value.statusCode == 400
