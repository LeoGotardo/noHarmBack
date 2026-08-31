"""Verify that a caller really is who Google says they are.

`/auth/login` and `/auth/register` used to take a bare `uid` in the request
body and believe it. The UID is not a secret — it is the user id, and the API
hands it out in friend lists and search results — so anyone who had seen
another account's id could mint a token pair for it. Registration had the same
hole in reverse: any UID could be invented, and `emailVerified` was whatever
the client claimed.

The client now sends the Firebase ID token instead: a JWT signed by Google,
scoped to this project, carrying the UID and email as verified claims. This
module is the only place those claims are allowed to come from.

Failing closed matters more than availability here: with no Firebase app,
verification refuses every request rather than falling back to trusting the
body, which is exactly the hole being closed.

## Emulator mode

With `FIREBASE_AUTH_EMULATOR_HOST` set, firebase_admin skips the signature
check — the `aud`, `iss` and `sub` claims are still enforced, but any token
shaped right is accepted, and expiry is not checked either. That is what lets
the E2E suite mint identities without driving the Google popup, which
Playwright cannot automate. It is also a complete authentication bypass, so it
announces itself at boot and must never be set in production.
"""

import logging
from typing import NamedTuple

from exceptions.baseExceptions import NoHarmException
from infrastructure.external.firebaseApp import getFirebaseApp, isEmulated

logger = logging.getLogger(__name__)

# Server clocks drift. Firebase rejects a token whose `iat` is in the future,
# so a few seconds of tolerance is the difference between a working login and
# an unexplainable one. The SDK caps this at 60.
_CLOCK_SKEW_SECONDS = 10


class FirebaseIdentity(NamedTuple):
    """The claims we trust, extracted from a verified ID token."""

    uid: str
    email: str | None
    emailVerified: bool
    picture: str | None


def _invalidToken() -> NoHarmException:
    # Deliberately the same shape as a failed login: whether a token was
    # malformed, expired or issued to another project is not the caller's
    # business.
    return NoHarmException(
        statusCode=401,
        errorCode="INVALID_TOKEN",
        message="Invalid credentials.",
    )


def warnAboutEmulator() -> None:
    """Announce at boot that authentication is not actually being checked."""
    if isEmulated():
        logger.warning(
            "FIREBASE_AUTH_EMULATOR_HOST is set — ID token signatures are NOT "
            "verified and expiry is not checked. Anyone can authenticate as "
            "anyone. This must never be set in production."
        )


def verifyIdToken(idToken: str) -> FirebaseIdentity:
    """Verify a Firebase ID token and return its trusted claims.

    Raises:
        NoHarmException: 401 when the token is missing, malformed, expired or
            issued to another project; 503 when Firebase is not configured.
    """
    if not idToken or not isinstance(idToken, str):
        raise _invalidToken()

    app = getFirebaseApp()
    if app is None:
        logger.error("Refusing authentication: Firebase app unavailable.")
        raise NoHarmException(
            statusCode=503,
            errorCode="AUTH_UNAVAILABLE",
            message="Sign-in is temporarily unavailable. Please try again.",
        )

    try:
        from firebase_admin import auth as firebaseAuth

        claims = firebaseAuth.verify_id_token(
            idToken,
            app=app,
            clock_skew_seconds=_CLOCK_SKEW_SECONDS,
        )
    except Exception as e:
        # Includes InvalidIdTokenError, ExpiredIdTokenError and
        # CertificateFetchError. The last one is a Google outage rather than a
        # bad token, but treating it as anything other than "no" would mean
        # letting unverified tokens through.
        logger.info(f"ID token rejected: {type(e).__name__}")
        raise _invalidToken()

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise _invalidToken()

    return FirebaseIdentity(
        uid=uid,
        email=claims.get("email"),
        emailVerified=bool(claims.get("email_verified", False)),
        picture=claims.get("picture"),
    )


# Same reasoning as clientIp.py: a misconfiguration that silently disables a
# security control has to announce itself, because nothing else will.
warnAboutEmulator()
