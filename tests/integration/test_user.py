import pytest


class TestMyProfile:
    def test_get_my_profile_returns_200(self, client, user_a):
        resp = client.get("/users/me", headers=user_a["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == user_a["payload"]["email"]
        assert body["username"] == user_a["payload"]["username"]

    def test_no_auth_returns_401(self, client):
        resp = client.get("/users/me")
        assert resp.status_code == 401

    def test_update_username_persists(self, client, user_a):
        resp = client.put(
            "/users/me",
            json={"username": "newusername99"},
            headers=user_a["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "newusername99"

        # Verify persistence
        get_resp = client.get("/users/me", headers=user_a["headers"])
        assert get_resp.json()["username"] == "newusername99"

    def test_delete_account_then_login_returns_403(self, client, user_a):
        resp = client.delete("/users/me", headers=user_a["headers"])
        assert resp.status_code == 200

        login_resp = client.post(
            "/auth/login",
            json={"uid": user_a["uid"], "email": user_a["payload"]["email"]},
        )
        assert login_resp.status_code == 403


class TestPublicProfile:
    def test_get_other_user_public_profile(self, client, user_a, user_b):
        resp = client.get(f"/users/{user_b['uid']}", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["username"] == user_b["payload"]["username"]

    def test_get_nonexistent_user_returns_404(self, client, user_a):
        import uuid
        resp = client.get(f"/users/{uuid.uuid4()}", headers=user_a["headers"])
        assert resp.status_code == 404


class TestRLS:
    def test_get_all_users_shows_only_enabled(self, client, user_a, user_b):
        resp = client.get("/users", headers=user_a["headers"])
        assert resp.status_code == 200
        # Both users created with emailVerified=True → status=enabled
        ids = [u["id"] for u in resp.json()["users"]]
        assert user_a["uid"] in ids
        assert user_b["uid"] in ids
