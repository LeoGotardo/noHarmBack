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
from datetime import date, datetime, timedelta, timezone
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
    service.consentService = MagicMock()
    return service


def _token(uid="uid-001", email="user@test.com", **claims):
    """A token the `stub_firebase` fixture knows how to resolve."""
    return json.dumps({"uid": uid, "email": email, **claims})


def _login_request(uid="uid-001", email="user@test.com", **claims):
    return AuthLoginRequest(idToken=_token(uid, email, **claims))


# Comfortably over any plausible MINIMUM_AGE_YEARS, so a test about usernames
# does not start failing the day the setting moves.
ADULT_BIRTH_DATE = date(1990, 6, 15)


def _register_request(
    uid="uid-001",
    email="new@test.com",
    username="newuser",
    birthDate=ADULT_BIRTH_DATE,
    acceptedTerms=True,
    acceptedPrivacy=True,
    healthDataConsent=True,
    **claims
):
    return AuthRegisterRequest(
        idToken=_token(uid, email, **claims),
        username=username,
        birthDate=birthDate,
        acceptedTerms=acceptedTerms,
        acceptedPrivacy=acceptedPrivacy,
        healthDataConsent=healthDataConsent,
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
        mock_user.status = config.STATUS_CODES["enabled"]
        service.userRepository.findById.return_value = mock_user

        result = service.login(_login_request())

        assert result["accessToken"] == "access-tok"
        assert result["refreshToken"] == "refresh-tok"
        assert result["tokenType"] == "Bearer"
        mock_limiter.onSuccess.assert_called_once_with("uid-001")


def test_login_refreshes_the_profile_picture_from_the_token(mock_db):
    """The photo used to be read once, at registration, and never again — an
    account that registered without one showed a blank avatar for ever, and
    there is no upload endpoint to fix it with."""
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-001"
        mock_user.status = config.STATUS_CODES["enabled"]
        mock_user.profile_picture = None
        mock_user.picture_blocked = False
        userModel = MagicMock()
        service.userRepository.findById.side_effect = (
            lambda _id, returnModel=False: userModel if returnModel else mock_user
        )

        service.login(_login_request(picture="https://pic/new.jpg"))

        assert userModel.profile_picture == "https://pic/new.jpg"
        service.userRepository.session.commit.assert_called()


def test_login_leaves_an_unchanged_picture_alone(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-001"
        mock_user.status = config.STATUS_CODES["enabled"]
        mock_user.profile_picture = "https://pic/same.jpg"
        mock_user.picture_blocked = False
        service.userRepository.findById.return_value = mock_user

        service.login(_login_request(picture="https://pic/same.jpg"))

        service.userRepository.session.commit.assert_not_called()


def test_login_survives_a_failed_picture_write(mock_db):
    """A photo that will not save must never cost anyone their sign-in."""
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler") as mock_jwt:

        mock_limiter.check.return_value = (True, None)
        mock_jwt.createAccessToken.return_value = "access-tok"
        mock_jwt.createRefreshToken.return_value = "refresh-tok"

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-001"
        mock_user.status = config.STATUS_CODES["enabled"]
        mock_user.profile_picture = None
        mock_user.picture_blocked = False
        service.userRepository.findById.side_effect = (
            lambda _id, returnModel=False: mock_user
        )
        service.userRepository.session.commit.side_effect = Exception("db down")

        result = service.login(_login_request(picture="https://pic/new.jpg"))

        assert result["accessToken"] == "access-tok"
        service.userRepository.session.rollback.assert_called()


def test_login_user_not_found_raises_404_account_not_found(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())
        # Not 401: the app reads 401 as an expired session.
        assert exc.value.statusCode == 404
        assert exc.value.errorCode == "ACCOUNT_NOT_FOUND"


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
        mock_user.banned_until = None  # permanent, not a timed suspension
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


def _deleted_user(daysAgo: float, userId: str = "uid-deleted"):
    """A soft-deleted user whose deletion happened `daysAgo` days ago."""
    user = MagicMock()
    user.id = userId
    user.status = config.STATUS_CODES["deleted"]
    user.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=daysAgo)
    return user


def test_login_deleted_user_inside_grace_window_offers_restore(mock_db):
    """Deleted but still restorable: the client needs to draw a different screen.

    A flat 403 "Account not found." would leave the app unable to tell this from
    a real rejection, and the user would never learn the account they deleted
    yesterday is still there to reclaim.
    """
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        service.userRepository.findById.return_value = _deleted_user(daysAgo=1)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())

        assert exc.value.statusCode == 403
        assert exc.value.errorCode == "ACCOUNT_PENDING_DELETION"
        assert "deletionScheduledAt" in exc.value.details


def test_login_deleted_user_past_grace_window_is_gone(mock_db):
    """Window closed: the purge has not run yet, but nobody outside needs to know."""
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        service.userRepository.findById.return_value = _deleted_user(
            daysAgo=config.ACCOUNT_DELETION_GRACE_DAYS + 1
        )

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())

        assert exc.value.statusCode == 403
        assert exc.value.errorCode == "ACCOUNT_DELETED"
        assert exc.value.details is None


def test_login_deleted_user_without_timestamp_is_gone(mock_db):
    """No `deleted_at` means no statable deadline, so no restore is offered."""
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        user = _deleted_user(daysAgo=1)
        user.deleted_at = None
        service.userRepository.findById.return_value = user

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())

        assert exc.value.errorCode == "ACCOUNT_DELETED"


def test_reactivate_restores_inside_the_window(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler") as mock_jwt, \
         patch("domain.services.authService.verifyIdToken") as mock_verify:

        mock_limiter.check.return_value = (True, None)
        mock_verify.return_value = MagicMock(uid="uid-deleted")
        mock_jwt.createAccessToken.return_value = "tok"
        mock_jwt.createRefreshToken.return_value = "ref"

        service = _make_service(mock_db)
        service.userRepository.findById.return_value = _deleted_user(daysAgo=2)
        restored = MagicMock()
        restored.id = "uid-deleted"
        service.userRepository.restore.return_value = restored

        result = service.reactivate("id-token")

        service.userRepository.restore.assert_called_once_with("uid-deleted")
        assert result["accessToken"] == "tok"


def test_reactivate_past_the_window_is_refused(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"), \
         patch("domain.services.authService.verifyIdToken") as mock_verify:

        mock_limiter.check.return_value = (True, None)
        mock_verify.return_value = MagicMock(uid="uid-deleted")

        service = _make_service(mock_db)
        service.userRepository.findById.return_value = _deleted_user(
            daysAgo=config.ACCOUNT_DELETION_GRACE_DAYS + 1
        )

        with pytest.raises(NoHarmException) as exc:
            service.reactivate("id-token")

        assert exc.value.errorCode == "ACCOUNT_DELETED"
        service.userRepository.restore.assert_not_called()


def test_reactivate_never_launders_a_ban(mock_db):
    """A ban outranks a deletion — otherwise deleting is a way to shed one."""
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"), \
         patch("domain.services.authService.verifyIdToken") as mock_verify:

        mock_limiter.check.return_value = (True, None)
        mock_verify.return_value = MagicMock(uid="uid-banned")

        service = _make_service(mock_db)
        banned = MagicMock()
        banned.id = "uid-banned"
        banned.status = config.STATUS_CODES["banned"]
        banned.banned_until = None
        service.userRepository.findById.return_value = banned

        with pytest.raises(NoHarmException) as exc:
            service.reactivate("id-token")

        assert exc.value.errorCode == "ACCOUNT_BANNED"
        service.userRepository.restore.assert_not_called()


def test_reactivate_on_an_active_account_is_a_conflict(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"), \
         patch("domain.services.authService.verifyIdToken") as mock_verify:

        mock_limiter.check.return_value = (True, None)
        mock_verify.return_value = MagicMock(uid="uid-active")

        service = _make_service(mock_db)
        active = MagicMock()
        active.id = "uid-active"
        active.status = config.STATUS_CODES["enabled"]
        service.userRepository.findById.return_value = active

        with pytest.raises(NoHarmException) as exc:
            service.reactivate("id-token")

        assert exc.value.statusCode == 409
        assert exc.value.errorCode == "ACCOUNT_NOT_DELETED"


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


def test_register_records_the_three_consents(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        service.register(_register_request(healthDataConsent=True))

        service.consentService.recordRegistrationConsents.assert_called_once_with(
            "uid-001", True
        )


def test_register_passes_a_declined_health_consent_through(mock_db):
    """Declining creates a working account without the streak tracker."""
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        service.register(_register_request(healthDataConsent=False))

        service.consentService.recordRegistrationConsents.assert_called_once_with(
            "uid-001", False
        )
        service.userRepository.create.assert_called_once()


def test_register_stores_the_declared_birth_date(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        service.register(_register_request(birthDate=date(1988, 3, 4)))

        created = service.userRepository.create.call_args[0][0]
        assert created.birth_date == date(1988, 3, 4)


@pytest.mark.parametrize("terms,privacy,missing", [
    (False, True, ["terms"]),
    (True, False, ["privacy"]),
    (False, False, ["terms", "privacy"]),
])
def test_register_without_both_binding_consents_raises_400(mock_db, terms, privacy, missing):
    """Refused before anything is written.

    A row created first and gated afterwards is an account that exists having
    agreed to nothing, and the only way out of that state is a hand-written
    DELETE.
    """
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request(acceptedTerms=terms, acceptedPrivacy=privacy))

        assert exc.value.statusCode == 400
        assert exc.value.errorCode == "CONSENT_REQUIRED"
        assert exc.value.details["missing"] == missing
        service.userRepository.create.assert_not_called()
        service.consentService.recordRegistrationConsents.assert_not_called()


def test_register_below_the_minimum_age_raises_403(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        today = datetime.now(timezone.utc).date()
        # One day short of the minimum: the boundary is what a `days // 365`
        # implementation gets wrong.
        justTooYoung = date(
            today.year - config.MINIMUM_AGE_YEARS, today.month, today.day
        ) + timedelta(days=1)

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request(birthDate=justTooYoung))

        assert exc.value.statusCode == 403
        assert exc.value.errorCode == "UNDERAGE"
        assert exc.value.details["minimumAge"] == config.MINIMUM_AGE_YEARS
        service.userRepository.create.assert_not_called()


def test_register_exactly_on_the_minimum_age_birthday_is_allowed(mock_db):
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        service.userRepository.findById.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByEmail.side_effect = NoHarmException(statusCode=404)
        service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)

        today = datetime.now(timezone.utc).date()
        exactly = date(today.year - config.MINIMUM_AGE_YEARS, today.month, today.day)

        service.register(_register_request(birthDate=exactly))

        service.userRepository.create.assert_called_once()


def test_register_with_a_future_birth_date_raises_400_not_underage(mock_db):
    """A broken client or a typo. Telling someone born in 2035 that they are
    too young is a worse answer than telling them the date is wrong."""
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request(birthDate=tomorrow))

        assert exc.value.statusCode == 400
        assert exc.value.errorCode == "INVALID_BIRTH_DATE"


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


# ── timed suspensions ─────────────────────────────────────────────────────────
#
# A suspension is the `banned` status plus an end date. What these guard is the
# difference that makes: the refusal has to carry the date, and the ban has to
# lift itself when the date passes — there is no cron that does it.

def _suspended(uid="uid-suspended", until=None):
    user = MagicMock()
    user.id = uid
    user.status = config.STATUS_CODES["banned"]
    user.banned_until = until
    return user


def test_login_while_suspended_says_when_it_ends(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        until = datetime.now() + timedelta(days=3)
        service.userRepository.findById.return_value = _suspended(until=until)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())

        # Not ACCOUNT_BANNED: telling someone serving three days that their
        # account is gone is a different message than the truth.
        assert exc.value.errorCode == "ACCOUNT_SUSPENDED"
        assert exc.value.details["suspendedUntil"].startswith(until.isoformat()[:10])
        service.userRepository.liftExpiredSuspension.assert_not_called()


def test_a_permanent_ban_still_says_banned(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        service.userRepository.findById.return_value = _suspended(until=None)

        with pytest.raises(NoHarmException) as exc:
            service.login(_login_request())

        assert exc.value.errorCode == "ACCOUNT_BANNED"
        assert exc.value.details is None or "suspendedUntil" not in (exc.value.details or {})


def test_login_after_the_suspension_ended_lifts_it_and_succeeds(mock_db):
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler") as mock_jwt:

        mock_limiter.check.return_value = (True, None)
        mock_jwt.createAccessToken.return_value = "access"
        mock_jwt.createRefreshToken.return_value = "refresh"

        service = _make_service(mock_db)
        expired = _suspended(until=datetime.now() - timedelta(hours=1))
        service.userRepository.findById.return_value = expired

        restored = MagicMock()
        restored.id = expired.id
        restored.status = config.STATUS_CODES["enabled"]
        restored.banned_until = None
        service.userRepository.liftExpiredSuspension.return_value = restored

        result = service.login(_login_request())

        assert result["accessToken"] == "access"
        service.userRepository.liftExpiredSuspension.assert_called_once()


def test_refresh_after_the_suspension_ended_issues_a_new_pair(mock_db):
    """The app refreshes every 15 minutes, so this is where a served
    suspension ends for someone who left the app open."""
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        mock_jwt.verifyToken.return_value = {"sub": "uid-suspended", "jti": "j", "exp": 1}
        mock_jwt.createAccessToken.return_value = "access"
        mock_jwt.createRefreshToken.return_value = "refresh"

        service = _make_service(mock_db)
        expired = _suspended(until=datetime.now() - timedelta(minutes=1))
        service.userRepository.findById.return_value = expired

        restored = MagicMock()
        restored.id = expired.id
        restored.status = config.STATUS_CODES["enabled"]
        restored.banned_until = None
        service.userRepository.liftExpiredSuspension.return_value = restored

        result = service.refresh("refresh-token")
        assert result["accessToken"] == "access"


def test_refresh_while_still_suspended_is_refused(mock_db):
    with patch("domain.services.authService._jwtHandler") as mock_jwt:
        mock_jwt.verifyToken.return_value = {"sub": "uid-suspended", "jti": "j", "exp": 1}

        service = _make_service(mock_db)
        service.userRepository.findById.return_value = _suspended(
            until=datetime.now() + timedelta(days=1)
        )

        with pytest.raises(NoHarmException) as exc:
            service.refresh("refresh-token")
        assert exc.value.statusCode == 403


def test_registering_again_after_a_suspension_ended_is_not_refused_as_banned(mock_db):
    """Same gesture as signing in, so it gets the same answer."""
    with patch("domain.services.authService._jwtHandler"):
        service = _make_service(mock_db)
        expired = _suspended(uid="uid-001", until=datetime.now() - timedelta(days=1))
        service.userRepository.findById.return_value = expired

        restored = MagicMock()
        restored.id = "uid-001"
        restored.status = config.STATUS_CODES["enabled"]
        restored.banned_until = None
        service.userRepository.liftExpiredSuspension.return_value = restored

        with pytest.raises(NoHarmException) as exc:
            service.register(_register_request())

        # It falls through to the ordinary "this account already exists", not
        # to a ban — which is the point.
        assert exc.value.errorCode != "ACCOUNT_BANNED"


def test_login_does_not_restore_a_blocked_picture(mock_db):
    """This sync is the exact path that would undo a moderator's decision,
    silently, at the user's next sign-in."""
    with patch("domain.services.authService._loginLimiter") as mock_limiter, \
         patch("domain.services.authService._jwtHandler"):

        mock_limiter.check.return_value = (True, None)

        service = _make_service(mock_db)
        mock_user = MagicMock()
        mock_user.id = "uid-001"
        mock_user.status = config.STATUS_CODES["enabled"]
        mock_user.profile_picture = None
        mock_user.picture_blocked = True
        service.userRepository.findById.return_value = mock_user

        service.login(_login_request(picture="https://pic/new.jpg"))

        service.userRepository.session.commit.assert_not_called()
