"""Single Firebase Admin app for the whole process.

`firebase_admin.initialize_app()` claims a process-global default app and
raises when called twice, so both users of the SDK — push (FCM) and ID-token
verification — have to come through here.

Initialisation is attempted once. A failure is remembered so a broken
credential does not cost a stack trace on every request; the callers decide
what a missing app means for them (push skips, verification refuses).

"Once" has to mean once *finished*, not once *started*. `_tried` used to be set
before `initialize_app` returned, so a second request arriving during a cold
start took the `if _tried: return None` branch and was refused with 503
`AUTH_UNAVAILABLE` — for no reason, with nothing logged, while the first
request was still building the very app it needed. Concurrent sign-ins in the
first moments after a restart are the normal case, not a rare one: it is what
the E2E suite does on every run, and what a deploy does to real users. The lock
below is what makes the flag mean what the paragraph above says.
"""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

_app = None
_tried = False
_lock = threading.Lock()

# Read by firebase_admin itself. When set, `verify_id_token` skips the
# signature check — see `security/firebaseIdentity.py` for why that exists and
# what still has to hold for a token to be accepted.
EMULATOR_HOST_ENV_VAR = "FIREBASE_AUTH_EMULATOR_HOST"


def isEmulated() -> bool:
    """True when tokens are verified against a Firebase Auth emulator."""
    return bool(os.environ.get(EMULATOR_HOST_ENV_VAR, "").strip())


def _credential():
    """Service-account credential, or None when none is configured."""
    from firebase_admin import credentials
    from core.config import config

    raw = getattr(config, "FIREBASE_SERVICE_ACCOUNT", None)
    if raw:
        return credentials.Certificate(json.loads(raw))

    path = getattr(config, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    if path:
        return credentials.Certificate(path)

    return None


def getFirebaseApp():
    """The process-wide Firebase app, or None when it cannot be built."""
    global _app, _tried

    # Fast path, no lock: once built, the app never changes.
    if _app is not None:
        return _app

    with _lock:
        # Re-checked under the lock — whoever held it may have finished the
        # work this caller was about to start.
        if _app is not None:
            return _app
        if _tried:
            return None

        return _initialise()


def _initialise():
    """Build the app. Called once, under `_lock`."""
    global _app, _tried

    try:
        import firebase_admin
        from core.config import config

        cred = _credential()

        # The project id is what `verify_id_token` matches the token's `aud`
        # and `iss` against. A service account carries its own; the emulator
        # path has no credential to read it from, so it must be configured.
        options = {}
        projectId = getattr(config, "FIREBASE_PROJECT_ID", None)
        if projectId:
            options["projectId"] = projectId

        if cred is None and not (isEmulated() and options.get("projectId")):
            logger.warning(
                "Firebase not configured: set FIREBASE_SERVICE_ACCOUNT "
                "(or FIREBASE_SERVICE_ACCOUNT_PATH). Login and registration "
                "will be refused."
            )
            _tried = True
            return None

        try:
            _app = firebase_admin.initialize_app(cred, options)
        except ValueError:
            # Something else already claimed the default app — reuse it rather
            # than failing, since a second app would only duplicate state.
            _app = firebase_admin.get_app()

        return _app
    except Exception as e:
        # Only a real failure sets the flag: a configuration that cannot work
        # will not start working on the next request, and retrying it per
        # request costs a stack trace each time.
        _tried = True
        logger.warning(f"Firebase init failed: {e}")
        return None
