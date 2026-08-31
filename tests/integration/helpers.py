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


def new_identity(uid=None, email=None, username=None, emailVerified=True):
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
    }


def body_for(identity):
    """The register body: a token, and the one field the client gets to choose."""
    return {"idToken": identity["idToken"], "username": identity["username"]}


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
