import uuid
import pytest
from helpers import new_user_payload, register


class TestRegister:
    def test_success_returns_201_and_token_pair(self, client):
        resp = client.post("/auth/register", json=new_user_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert "accessToken" in body
        assert "refreshToken" in body
        assert body["tokenType"] == "Bearer"

    def test_duplicate_email_returns_409(self, client):
        payload = new_user_payload()
        client.post("/auth/register", json=payload)
        payload2 = {**payload, "uid": str(uuid.uuid4()), "username": "different_user"}
        resp = client.post("/auth/register", json=payload2)
        assert resp.status_code == 409

    def test_duplicate_username_returns_409(self, client):
        payload = new_user_payload()
        client.post("/auth/register", json=payload)
        payload2 = {**payload, "uid": str(uuid.uuid4()), "email": "other@test.com"}
        resp = client.post("/auth/register", json=payload2)
        assert resp.status_code == 409

    def test_invalid_username_format_returns_400(self, client):
        payload = {**new_user_payload(), "username": "bad username!"}
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 400


class TestLogin:
    def test_success_returns_token_pair(self, client):
        p = new_user_payload()
        client.post("/auth/register", json=p)
        resp = client.post("/auth/login", json={"uid": p["uid"], "email": p["email"]})
        assert resp.status_code == 200
        body = resp.json()
        assert "accessToken" in body
        assert "refreshToken" in body

    def test_nonexistent_uid_returns_401(self, client):
        resp = client.post("/auth/login", json={"uid": str(uuid.uuid4()), "email": "x@x.com"})
        assert resp.status_code == 401

    def test_deleted_account_returns_403(self, client):
        p = new_user_payload()
        tokens = client.post("/auth/register", json=p).json()
        headers = {"Authorization": f"Bearer {tokens['accessToken']}"}
        client.delete("/users/me", headers=headers)
        resp = client.post("/auth/login", json={"uid": p["uid"], "email": p["email"]})
        assert resp.status_code == 403


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
