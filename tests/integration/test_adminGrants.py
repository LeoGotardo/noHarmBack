"""Promoting and demoting administrators from the app (tb_19).

What is held in place:

- **who may promote** — official accounts only; an administrator, promoted or
  allowlisted, gets the same 404 as anyone else;
- **what a promotion grants** — exactly the admin routes, on the next request,
  and the "admin" mark beside the name;
- **what cannot be revoked here** — an administrator named by the environment;
- **an official account is an administrator** without being on ADMIN_USER_IDS.
"""

import pytest

from core.config import config
from helpers import register, set_status


@pytest.fixture
def official(client):
    user = register(client)
    original = list(config.OFFICIAL_USER_IDS)
    config.OFFICIAL_USER_IDS = original + [user["uid"]]
    try:
        yield user
    finally:
        config.OFFICIAL_USER_IDS = original


def _isAdmin(client, user):
    return client.get("/admin/users", headers=user["headers"]).status_code == 200


class TestOfficialIsAdmin:
    def test_an_official_account_reaches_the_admin_routes(self, client, official):
        assert _isAdmin(client, official)
        assert client.get("/reports", headers=official["headers"]).status_code == 200


class TestPromote:
    def test_promotion_grants_the_admin_routes(self, client, official, user_a):
        assert not _isAdmin(client, user_a)

        resp = client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
        assert resp.status_code == 204, resp.text

        assert _isAdmin(client, user_a)
        me = client.get("/users/me", headers=user_a["headers"]).json()
        assert me["role"] == "admin"

    def test_it_is_listed_with_who_granted_it(self, client, official, user_a):
        client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])

        rows = client.get("/admin/admins", headers=official["headers"]).json()
        byId = {row["id"]: row for row in rows}

        assert byId[user_a["uid"]]["source"] == "granted"
        assert byId[user_a["uid"]]["granted_by"] == official["uid"]
        assert byId[official["uid"]]["source"] == "official"

    def test_promoting_twice_is_409(self, client, official, user_a):
        client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
        resp = client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
        assert resp.status_code == 409

    def test_an_unknown_account_is_404(self, client, official):
        assert client.post("/admin/admins/nobody-here", headers=official["headers"]).status_code == 404

    def test_an_inactive_account_cannot_be_promoted(self, client, official, user_a):
        set_status(user_a["uid"], config.STATUS_CODES["deleted"])
        resp = client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
        assert resp.status_code == 409


class TestDemote:
    def test_demotion_takes_effect_on_the_next_request(self, client, official, user_a):
        client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
        assert _isAdmin(client, user_a)

        resp = client.delete(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
        assert resp.status_code == 204, resp.text

        assert not _isAdmin(client, user_a)

    def test_an_environment_admin_cannot_be_demoted(self, client, official, user_a):
        original = list(config.ADMIN_USER_IDS)
        config.ADMIN_USER_IDS = original + [user_a["uid"]]
        try:
            resp = client.delete(f"/admin/admins/{user_a['uid']}", headers=official["headers"])
            assert resp.status_code == 409
            assert _isAdmin(client, user_a)
        finally:
            config.ADMIN_USER_IDS = original

    def test_demoting_a_non_admin_is_404(self, client, official, user_a):
        assert client.delete(f"/admin/admins/{user_a['uid']}", headers=official["headers"]).status_code == 404


class TestTheGate:
    def test_an_ordinary_account_gets_404(self, client, user_a, user_b):
        h = user_a["headers"]
        assert client.get("/admin/admins", headers=h).status_code == 404
        assert client.post(f"/admin/admins/{user_b['uid']}", headers=h).status_code == 404
        assert client.post(f"/admin/admins/{user_a['uid']}", headers=h).status_code == 404

    def test_a_promoted_admin_cannot_promote(self, client, official, user_a, user_b):
        client.post(f"/admin/admins/{user_a['uid']}", headers=official["headers"])

        resp = client.post(f"/admin/admins/{user_b['uid']}", headers=user_a["headers"])
        assert resp.status_code == 404
        assert not _isAdmin(client, user_b)
