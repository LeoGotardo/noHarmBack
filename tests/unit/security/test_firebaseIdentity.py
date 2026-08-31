"""Tests for Firebase ID token verification.

These run the real firebase_admin verifier against the Auth emulator switch
(`FIREBASE_AUTH_EMULATOR_HOST`), which skips the signature check but still
enforces `aud`, `iss` and `sub`. That is enough to cover everything this module
decides — what it accepts, what it refuses, and what it refuses to guess — with
no Firebase project and no network.

The signature check itself is Google's code, not ours.
"""

import os
import time

import jwt as pyjwt
import pytest

from exceptions.baseExceptions import NoHarmException

_PROJECT_ID = "demo-noharm"


def _token(uid="uid-001", email="user@test.com", emailVerified=True,
           picture=None, aud=_PROJECT_ID, iss=None, exp_offset=3600):
    """A token shaped like Firebase's, signed with a throwaway key.

    In emulator mode the signature is ignored, so the algorithm and key are
    arbitrary — what the verifier still checks is everything else.
    """
    now = int(time.time())
    claims = {
        "iss": iss if iss is not None else f"https://securetoken.google.com/{aud}",
        "aud": aud,
        "sub": uid,
        "iat": now,
        "exp": now + exp_offset,
        "email": email,
        "email_verified": emailVerified,
    }
    if picture:
        claims["picture"] = picture
    return pyjwt.encode(claims, "signature-is-not-checked-in-emulator-mode", algorithm="HS256")


@pytest.fixture
def verify(monkeypatch):
    """`verifyIdToken` wired to an emulator-mode app, isolated per test."""
    import firebase_admin
    from security import firebaseIdentity

    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")

    # A named app: the default one is process-global, and a test that claimed it
    # would leak into every other test in the session.
    try:
        app = firebase_admin.get_app("test-verifier")
    except ValueError:
        app = firebase_admin.initialize_app(
            None, {"projectId": _PROJECT_ID}, name="test-verifier"
        )

    monkeypatch.setattr(firebaseIdentity, "getFirebaseApp", lambda: app)
    return firebaseIdentity.verifyIdToken


# ── accepted ──────────────────────────────────────────────────────────────────

def test_returns_claims_from_a_valid_token(verify):
    identity = verify(_token(uid="uid-abc", email="a@b.com", picture="https://pic"))

    assert identity.uid == "uid-abc"
    assert identity.email == "a@b.com"
    assert identity.emailVerified is True
    assert identity.picture == "https://pic"


def test_unverified_email_is_reported_as_such(verify):
    assert verify(_token(emailVerified=False)).emailVerified is False


def test_missing_picture_claim_is_none(verify):
    assert verify(_token()).picture is None


# ── refused ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", None, 12345, "not-a-jwt", "a.b.c"])
def test_malformed_token_raises_401(verify, bad):
    with pytest.raises(NoHarmException) as exc:
        verify(bad)
    assert exc.value.statusCode == 401


def test_token_from_another_firebase_project_raises_401(verify):
    # The signature check is off in emulator mode, so this is exactly the case
    # a forged token would take: well-formed, wrong project.
    with pytest.raises(NoHarmException) as exc:
        verify(_token(aud="someone-elses-project"))
    assert exc.value.statusCode == 401


def test_token_with_mismatched_issuer_raises_401(verify):
    with pytest.raises(NoHarmException) as exc:
        verify(_token(iss="https://evil.example.com/"))
    assert exc.value.statusCode == 401


def test_token_without_subject_raises_401(verify):
    with pytest.raises(NoHarmException) as exc:
        verify(_token(uid=""))
    assert exc.value.statusCode == 401


def test_error_message_does_not_say_why(verify):
    # Whether a token was malformed, expired or issued elsewhere is not the
    # caller's business — same response as a login for an account that is not
    # there, so neither can be used to probe the other.
    with pytest.raises(NoHarmException) as exc:
        verify(_token(aud="someone-elses-project"))
    assert exc.value.message == "Invalid credentials."


# ── fails closed ──────────────────────────────────────────────────────────────

def test_unconfigured_firebase_raises_503_not_a_bypass(monkeypatch):
    from security import firebaseIdentity

    monkeypatch.setattr(firebaseIdentity, "getFirebaseApp", lambda: None)

    with pytest.raises(NoHarmException) as exc:
        firebaseIdentity.verifyIdToken(_token())

    # 503, never a pass-through: with no way to check the token, the only safe
    # answer is no answer.
    assert exc.value.statusCode == 503
