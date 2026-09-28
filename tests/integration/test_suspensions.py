"""Timed suspensions, end to end (§ moderation).

Moderation could only ban for ever, so every offence short of that got a
warning nobody could enforce. A suspension is the same `banned` status plus an
end date, and these guard the three things that makes true: the refusal says
when it ends, the ban lifts itself when it does, and nothing about a permanent
ban changed.
"""

import pytest
from sqlalchemy import text

from helpers import REGISTRATION_CONSENT, as_admin, fake_id_token, new_identity, register


ADMIN_UID = "uid-moderator"


@pytest.fixture
def admin(client):
    user = register(client, new_identity(uid=ADMIN_UID))
    with as_admin(ADMIN_UID):
        yield user


def _suspend(client, admin, uid, days=3):
    return client.put(f"/users/{uid}/suspend", json={"days": days}, headers=admin["headers"])


def _login(client, user):
    return client.post("/auth/login", json={"idToken": user["idToken"]})


def _backdate_suspension(uid, hours=1):
    """Move a suspension's end into the past. Waiting three days is not a test.

    Only touches a row that already has an end date: writing one onto a
    permanent ban would *create* a suspension rather than age one, which is a
    different thing to test and silently passes the test below.
    """
    from helpers import _engine

    with _engine().connect() as conn:
        conn.execute(
            text(
                "UPDATE tb_0 SET cl_0g = NOW() - make_interval(hours => :h)"
                " WHERE cl_0a = :uid AND cl_0g IS NOT NULL"
            ),
            {"h": hours, "uid": uid},
        )
        conn.commit()


class TestSuspending:
    def test_a_suspension_answers_with_its_end_date(self, client, user_a, admin):
        resp = _suspend(client, admin, user_a["uid"], days=3)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == 9
        assert resp.json()["banned_until"] is not None

        login = _login(client, user_a)
        assert login.status_code == 403
        body = login.json()
        # The date is the whole difference between a pause and a loss, and the
        # app draws a different screen for each.
        assert body["errorCode"] == "ACCOUNT_SUSPENDED"
        assert body["details"]["suspendedUntil"]

    def test_a_permanent_ban_still_reads_as_banned(self, client, user_a, admin):
        resp = client.put(
            f"/users/{user_a['uid']}/suspend", json={"days": None}, headers=admin["headers"]
        )
        assert resp.json()["banned_until"] is None

        login = _login(client, user_a)
        assert login.status_code == 403
        assert login.json()["errorCode"] == "ACCOUNT_BANNED"

    def test_a_suspended_account_cannot_use_a_token_it_already_had(self, client, user_a, admin):
        """The access token outlives the suspension by up to 15 minutes, so the
        status check on every request is what actually stops them."""
        _suspend(client, admin, user_a["uid"])
        assert client.get("/users/me", headers=user_a["headers"]).status_code == 403

    def test_nor_refresh_its_way_back_in(self, client, user_a, admin):
        _suspend(client, admin, user_a["uid"])
        resp = client.post("/auth/refresh", json={"refreshToken": user_a["refresh"]})
        assert resp.status_code == 403

    def test_a_suspension_is_not_reachable_by_an_ordinary_user(self, client, user_a, user_b):
        resp = client.put(
            f"/users/{user_b['uid']}/suspend", json={"days": 30}, headers=user_a["headers"]
        )
        assert resp.status_code == 404
        assert _login(client, user_b).status_code == 200

    def test_a_window_beyond_the_cap_is_refused(self, client, user_a, admin):
        resp = client.put(
            f"/users/{user_a['uid']}/suspend", json={"days": 100000}, headers=admin["headers"]
        )
        assert resp.status_code == 400
        assert _login(client, user_a).status_code == 200


class TestItEndsByItself:
    def test_signing_in_after_the_date_lifts_the_ban(self, client, user_a, admin):
        _suspend(client, admin, user_a["uid"], days=3)
        _backdate_suspension(user_a["uid"])

        login = _login(client, user_a)
        assert login.status_code == 200, login.text
        assert login.json()["accessToken"]

        # And the account is genuinely back, not merely let through once.
        headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}
        assert client.get("/users/me", headers=headers).status_code == 200

    def test_a_refresh_after_the_date_also_lifts_it(self, client, user_a, admin):
        _suspend(client, admin, user_a["uid"], days=3)
        _backdate_suspension(user_a["uid"])

        resp = client.post("/auth/refresh", json={"refreshToken": user_a["refresh"]})
        assert resp.status_code == 200, resp.text

    def test_a_permanent_ban_never_lifts_itself(self, client, user_a, admin):
        client.put(f"/users/{user_a['uid']}/suspend", json={"days": None}, headers=admin["headers"])
        # Nothing to age: a permanent ban has no end date, and the helper
        # refuses to invent one.
        _backdate_suspension(user_a["uid"], hours=99999)

        assert _login(client, user_a).status_code == 403

    def test_lifting_a_ban_by_hand_clears_the_date_with_it(self, client, user_a, admin):
        """Otherwise a later permanent ban carries a stale date and expires."""
        _suspend(client, admin, user_a["uid"], days=30)
        client.put(f"/users/{user_a['uid']}/status/1", headers=admin["headers"])

        assert _login(client, user_a).status_code == 200

        client.put(f"/users/{user_a['uid']}/suspend", json={"days": None}, headers=admin["headers"])
        assert _login(client, user_a).json()["errorCode"] == "ACCOUNT_BANNED"


class TestABanOutranksDeletion:
    def test_deleting_a_suspended_account_does_not_shed_the_suspension(self, client, user_a, admin):
        """Deleting and reactivating was the obvious way to launder a ban."""
        _suspend(client, admin, user_a["uid"], days=30)

        resp = client.post("/auth/reactivate", json={"idToken": user_a["idToken"]})
        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_SUSPENDED"

    def test_registering_again_while_suspended_is_refused(self, client, user_a, admin):
        _suspend(client, admin, user_a["uid"], days=30)

        resp = client.post(
            "/auth/register",
            json={
                "idToken": fake_id_token(user_a["uid"], "whatever@example.com"),
                "username": "newname",
                # Otherwise this is a 422 from the schema and the assertion
                # below passes without the ban ever being consulted.
                **REGISTRATION_CONSENT,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_SUSPENDED"
