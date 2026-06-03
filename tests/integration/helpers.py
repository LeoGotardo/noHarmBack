"""Shared helper functions for integration tests.

Import these in test files — do NOT import from conftest.py directly.
"""

import uuid


def new_user_payload():
    uid = str(uuid.uuid4())
    return {
        "uid": uid,
        "email": f"test_{uid[:8]}@example.com",
        "username": f"user_{uid[:8]}",
        "emailVerified": True,
        "photoURL": None,
    }


def register(client, payload=None):
    payload = payload or new_user_payload()
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    return {
        "payload": payload,
        "uid": payload["uid"],
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
