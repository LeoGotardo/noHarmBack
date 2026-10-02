import uuid
import pytest
from helpers import (
    REGISTRATION_CONSENT,
    body_for,
    fake_id_token,
    new_identity,
    new_user_payload,
    register,
)


class TestRegister:
    def test_success_returns_201_and_token_pair(self, client):
        resp = client.post("/auth/register", json=new_user_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert "accessToken" in body
        assert "refreshToken" in body
        assert body["tokenType"] == "Bearer"

    def test_duplicate_email_returns_409(self, client):
        first = new_identity()
        client.post("/auth/register", json=body_for(first))
        # Same email, different Google account and username.
        second = new_identity(email=first["email"], username="different_user")
        resp = client.post("/auth/register", json=body_for(second))
        assert resp.status_code == 409

    def test_duplicate_username_returns_409(self, client):
        first = new_identity()
        client.post("/auth/register", json=body_for(first))
        second = new_identity(username=first["username"])
        resp = client.post("/auth/register", json=body_for(second))
        assert resp.status_code == 409

    def test_duplicate_uid_returns_409(self, client):
        identity = new_identity()
        client.post("/auth/register", json=body_for(identity))
        # Same Google account, everything else fresh — the UID is the primary
        # key, so this used to reach the INSERT and blow up as a 500.
        again = new_identity(uid=identity["uid"], email="second@example.com",
                             username="second_user")
        resp = client.post("/auth/register", json=body_for(again))
        assert resp.status_code == 409

    def test_invalid_username_format_returns_400(self, client):
        payload = {**new_user_payload(), "username": "bad username!"}
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 400

    def test_missing_id_token_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "someuser"})
        assert resp.status_code == 422

    def test_token_from_another_project_returns_401(self, client):
        uid = str(uuid.uuid4())
        resp = client.post("/auth/register", json={
            "idToken": fake_id_token(uid, f"{uid[:8]}@example.com", aud="other-project"),
            "username": f"user_{uid[:8]}",
            # Present so the request gets past schema validation: a 422 here
            # would pass the assertion below for entirely the wrong reason.
            **REGISTRATION_CONSENT,
        })
        assert resp.status_code == 401

    def test_identity_fields_in_the_body_are_refused(self, client):
        identity = new_identity()
        resp = client.post("/auth/register", json={
            **body_for(identity),
            # What a patched client would send. Identity comes from the token.
            "uid": "attacker-chosen-uid",
            "email": "attacker@example.com",
            "emailVerified": True,
            "photoURL": "https://attacker.example.com/pic.png",
        })
        assert resp.status_code == 422

        # ...and nothing was created under either identity.
        ok = client.post("/auth/register", json=body_for(identity))
        assert ok.status_code == 201
        headers = {"Authorization": f"Bearer {ok.json()['accessToken']}"}
        me = client.get("/users/me", headers=headers).json()
        assert me["id"] == identity["uid"]
        assert me["email"] == identity["email"]

    def test_unverified_email_registers_as_pending(self, client):
        identity = new_identity(emailVerified=False)
        resp = client.post("/auth/register", json=body_for(identity))
        assert resp.status_code == 201

        headers = {"Authorization": f"Bearer {resp.json()['accessToken']}"}
        me = client.get("/users/me", headers=headers).json()
        assert me["status"] == 4  # pending


class TestLogin:
    def test_success_returns_token_pair(self, client):
        identity = new_identity()
        client.post("/auth/register", json=body_for(identity))
        resp = client.post("/auth/login", json={"idToken": identity["idToken"]})
        assert resp.status_code == 200
        body = resp.json()
        assert "accessToken" in body
        assert "refreshToken" in body

    def test_a_google_account_with_no_noharm_account_is_404(self, client):
        """Not 401: the app reads 401 as an expired session and told people who
        had never signed up to sign in again."""
        resp = client.post("/auth/login", json={"idToken": fake_id_token(str(uuid.uuid4()))})
        assert resp.status_code == 404
        assert resp.json()["errorCode"] == "ACCOUNT_NOT_FOUND"

    def test_bare_uid_is_not_accepted(self, client):
        # The old contract, and the hole it left: anyone who had seen another
        # account's id — the API hands it out in friend lists and search — could
        # trade it for that account's tokens.
        identity = new_identity()
        client.post("/auth/register", json=body_for(identity))

        resp = client.post("/auth/login", json={
            "uid": identity["uid"], "email": identity["email"],
        })
        assert resp.status_code == 422

    def test_token_from_another_project_returns_401(self, client):
        identity = new_identity()
        client.post("/auth/register", json=body_for(identity))

        forged = fake_id_token(identity["uid"], identity["email"], aud="other-project")
        resp = client.post("/auth/login", json={"idToken": forged})
        assert resp.status_code == 401

    def test_deleted_account_returns_403(self, client):
        identity = new_identity()
        tokens = client.post("/auth/register", json=body_for(identity)).json()
        headers = {"Authorization": f"Bearer {tokens['accessToken']}"}
        client.delete("/users/me", headers=headers)
        resp = client.post("/auth/login", json={"idToken": identity["idToken"]})
        assert resp.status_code == 403
        # Named, not just the status: a fresh deletion is inside its grace
        # window, so this is the restorable branch. Asserting 403 alone stayed
        # green when the window landed and stopped testing what it says it
        # tests. The closed-window and purge cases live in
        # tests/integration/test_accountLifecycle.py.
        assert resp.json()["errorCode"] == "ACCOUNT_PENDING_DELETION"


class TestLogout:
    def test_logout_then_access_token_rejected(self, client):
        user = register(client)
        client.post(
            "/auth/logout",
            json={"refreshToken": user["refresh"]},
            headers=user["headers"],
        )
        resp = client.get("/users/me", headers=user["headers"])
        assert resp.status_code == 401

    def test_logout_then_refresh_token_rejected(self, client):
        user = register(client)
        client.post(
            "/auth/logout",
            json={"refreshToken": user["refresh"]},
            headers=user["headers"],
        )
        resp = client.post("/auth/refresh", json={"refreshToken": user["refresh"]})
        assert resp.status_code == 401



class TestLogoutEverywhere:
    """A second device's tokens die too — the ones the caller never held."""

    @staticmethod
    def _secondDevice(client, user):
        import time
        time.sleep(1.1)  # `iat` has one-second resolution
        resp = client.post("/auth/login", json={"idToken": user["idToken"]})
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_every_device_is_signed_out(self, client):
        user = register(client)
        other = self._secondDevice(client, user)

        resp = client.post("/auth/logout-all", headers=user["headers"])
        assert resp.status_code == 204

        assert client.get("/users/me", headers=user["headers"]).status_code == 401
        otherHeaders = {"Authorization": f"Bearer {other['accessToken']}"}
        assert client.get("/users/me", headers=otherHeaders).status_code == 401
        for refresh in (user["refresh"], other["refreshToken"]):
            assert client.post("/auth/refresh", json={"refreshToken": refresh}).status_code == 401

    def test_signing_in_again_afterwards_works(self, client):
        import time
        user = register(client)
        client.post("/auth/logout-all", headers=user["headers"])
        time.sleep(1.1)
        resp = client.post("/auth/login", json={"idToken": user["idToken"]})
        assert resp.status_code == 200
        fresh = {"Authorization": f"Bearer {resp.json()['accessToken']}"}
        assert client.get("/users/me", headers=fresh).status_code == 200

    def test_push_devices_are_unregistered_too(self, client):
        """A lost phone keeps receiving message previews until its FCM token goes."""
        from sqlalchemy import text
        from conftest import _engine
        user = register(client)
        resp = client.post("/notifications", json={"deviceFCM": "fcm-lost-phone"}, headers=user["headers"])
        assert resp.status_code in (200, 201), resp.text

        client.post("/auth/logout-all", headers=user["headers"])

        with _engine.connect() as conn:
            statuses = conn.execute(
                text("SELECT cl_9d FROM tb_9 WHERE cl_9b = :uid"), {"uid": user["uid"]}
            ).scalars().all()
        assert statuses and all(st == 2 for st in statuses)

    def test_other_accounts_are_untouched(self, client):
        a, b = register(client), register(client)
        client.post("/auth/logout-all", headers=a["headers"])
        assert client.get("/users/me", headers=b["headers"]).status_code == 200


class TestRefresh:
    def test_refresh_returns_new_token_pair(self, client):
        user = register(client)
        resp = client.post("/auth/refresh", json={"refreshToken": user["refresh"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["accessToken"] != user["access"]
        assert body["refreshToken"] != user["refresh"]

    def test_old_refresh_token_invalid_after_rotation(self, client):
        user = register(client)
        client.post("/auth/refresh", json={"refreshToken": user["refresh"]})
        resp = client.post("/auth/refresh", json={"refreshToken": user["refresh"]})
        assert resp.status_code == 401

    def test_tampered_token_returns_401(self, client):
        user = register(client)
        bad = user["refresh"] + "tampered"
        resp = client.post("/auth/refresh", json={"refreshToken": bad})
        assert resp.status_code == 401
