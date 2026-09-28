"""Shared helper functions for integration tests.

Import these in test files — do NOT import from conftest.py directly.

## Why the tokens here are hand-made

`/auth/register` and `/auth/login` take a Firebase ID token and verify it. No
test can produce one signed by Google, so the suite runs the backend in
emulator mode (`FIREBASE_AUTH_EMULATOR_HOST`, set in conftest.py): the
signature is skipped, while `aud`, `iss` and `sub` are still enforced. The
tokens below are shaped to satisfy exactly that.

Everything the emulator switch turns off is covered directly in
`tests/unit/security/test_firebaseIdentity.py`.
"""

import os
import time
import uuid

import jwt as pyjwt

# Matches FIREBASE_PROJECT_ID in conftest.py — a token minted for another
# project is rejected even in emulator mode.
PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "demo-noharm")


def fake_id_token(uid, email=None, emailVerified=True, picture=None, aud=None):
    """An ID token accepted by the backend while it runs in emulator mode."""
    aud = aud or PROJECT_ID
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{aud}",
        "aud": aud,
        "sub": uid,
        "iat": now,
        "exp": now + 3600,
        "email_verified": emailVerified,
    }
    if email:
        claims["email"] = email
    if picture:
        claims["picture"] = picture
    return pyjwt.encode(claims, "signature-is-not-checked-in-emulator-mode", algorithm="HS256")


def new_identity(uid=None, email=None, username=None, emailVerified=True, **overrides):
    """A throwaway Google identity: the claims plus the token that proves them.

    Only `idToken` and `username` are sent to the API — the rest is here so a
    test can assert against the identity the backend will read out of the token.
    """
    uid = uid or str(uuid.uuid4())
    email = email if email is not None else f"test_{uid[:8]}@example.com"
    return {
        "uid": uid,
        "email": email,
        "username": username or f"user_{uid[:8]}",
        "idToken": fake_id_token(uid, email, emailVerified=emailVerified),
        # e.g. healthDataConsent=False, birthDate="2015-01-01" — picked up by
        # `body_for` and sent instead of the default.
        **overrides,
    }


# What every registration needs beyond a token and a username.
#
# A fixed adult birth date, and the two consents the backend refuses without —
# which is the point of both. `healthDataConsent` is true because a test account
# that cannot start a streak is useless to most of this suite:
# `POST /streaks/start` answers 403 HEALTH_CONSENT_REQUIRED without it. A test
# about the refusal passes `healthDataConsent=False` to `new_identity`.
REGISTRATION_CONSENT = {
    "birthDate": "1990-06-15",
    "acceptedTerms": True,
    "acceptedPrivacy": True,
    "healthDataConsent": True,
}


def body_for(identity):
    """The register body: a token, plus the fields the client does choose."""
    return {
        "idToken": identity["idToken"],
        "username": identity["username"],
        **REGISTRATION_CONSENT,
        # Anything the identity overrode wins, so a test can register an
        # account that declined health-data consent or is under age.
        **{k: identity[k] for k in REGISTRATION_CONSENT if k in identity},
    }


def new_user_payload(**kwargs):
    return body_for(new_identity(**kwargs))


def register(client, identity=None):
    identity = identity or new_identity()
    resp = client.post("/auth/register", json=body_for(identity))
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    return {
        "identity": identity,
        "uid": identity["uid"],
        "idToken": identity["idToken"],
        "access": tokens["accessToken"],
        "refresh": tokens["refreshToken"],
        "headers": {"Authorization": f"Bearer {tokens['accessToken']}"},
    }


def make_friends(client, a, b):
    """Send and accept a friend request between two registered users."""
    resp = client.post(f"/friendships/{b['uid']}", headers=a["headers"])
    assert resp.status_code == 201, resp.text
    fid = resp.json()["id"]
    resp = client.post(f"/friendships/{fid}/accept", headers=b["headers"])
    assert resp.status_code == 200, resp.text
    return fid


def open_chat(client, a, b):
    """Create an accepted chat between two already-friended users."""
    make_friends(client, a, b)
    resp = client.post("/chats", json={"receiverId": b["uid"]}, headers=a["headers"])
    assert resp.status_code == 201, resp.text
    chat_id = resp.json()["id"]
    client.post(f"/chats/{chat_id}/accept", headers=b["headers"])
    return chat_id


# ── Account deletion window ──────────────────────────────────────────────────

def _engine():
    """A direct engine on the test database, for state no endpoint can set."""
    from sqlalchemy import create_engine

    url = os.environ["TEST_DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    return create_engine(url)


def backdate_deletion(uid, days):
    """Move an account's `deleted_at` back, to simulate a closed grace window.

    There is no endpoint for this and there should not be: the only legitimate
    writer of `cl_0f` is the delete itself. Waiting 30 days is not a test, so
    the row is edited directly.
    """
    from sqlalchemy import text

    with _engine().connect() as conn:
        conn.execute(
            text("UPDATE tb_0 SET cl_0f = NOW() - make_interval(days => :days) WHERE cl_0a = :uid"),
            {"days": days, "uid": uid},
        )
        conn.commit()


def set_status(uid, status):
    """Force an account status directly — bans, without needing an admin."""
    from sqlalchemy import text

    with _engine().connect() as conn:
        conn.execute(
            text("UPDATE tb_0 SET cl_0e = :status WHERE cl_0a = :uid"),
            {"status": status, "uid": uid},
        )
        conn.commit()


def account_exists(uid):
    """True while the row is still there — the purge is what makes it False."""
    from sqlalchemy import text

    with _engine().connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM tb_0 WHERE cl_0a = :uid"), {"uid": uid}
        ).scalar() > 0


# ── Moderation ───────────────────────────────────────────────────────────────

def backdate_report_decision(reportId, days):
    """Move a resolved report's decision back, to simulate a lapsed cooldown.

    `REPORT_DISMISSED_COOLDOWN_DAYS` runs from `updated_at` — the moment the
    moderator closed it — and waiting 30 days is not a test. There is no
    endpoint for this and should not be: the only legitimate writer of that
    column is the resolution itself.
    """
    from sqlalchemy import text

    with _engine().connect() as conn:
        conn.execute(
            text("UPDATE tb_10 SET updated_at = NOW() - make_interval(days => :days) WHERE cl_10a = :id"),
            {"days": days, "id": reportId},
        )
        conn.commit()


def as_admin(uid):
    """Put a uid on the admin allowlist for the duration of a `with` block.

    Authorisation for the moderation routes is `config.ADMIN_USER_IDS` read at
    call time and nothing else, so this is the whole of "being a moderator".
    The list is empty everywhere else in the suite, which is what the
    admin-only tests rely on.
    """
    from contextlib import contextmanager
    from core.config import config

    @contextmanager
    def _scope():
        original = list(config.ADMIN_USER_IDS)
        config.ADMIN_USER_IDS = original + [uid]
        try:
            yield
        finally:
            config.ADMIN_USER_IDS = original

    return _scope()


def purge_user(uid):
    """Hard-delete an account, the way `jobs/purgeAccounts.py` eventually does.

    The job itself reads `core.database`, which the root conftest replaces with
    a MagicMock, so the DELETE is issued here instead. What matters to the tests
    using it is the database's own ON DELETE behaviour, which is identical
    either way.
    """
    from sqlalchemy import text

    with _engine().connect() as conn:
        conn.execute(text("DELETE FROM tb_0 WHERE cl_0a = :uid"), {"uid": uid})
        conn.commit()


def backdate_report_resolution(reportId, days):
    """Move a report's `updated_at` back, so the retention sweep considers it.

    `updated_at` is when a moderator closed it; waiting 180 days is not a test.
    """
    from sqlalchemy import text

    with _engine().connect() as conn:
        conn.execute(
            text("UPDATE tb_10 SET updated_at = NOW() - make_interval(days => :days) WHERE cl_10a = :id"),
            {"days": days, "id": reportId},
        )
        conn.commit()
