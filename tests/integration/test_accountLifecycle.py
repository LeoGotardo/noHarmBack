"""Integration tests for the account deletion window, bans, and the purge.

These are the paths the nightly `purge-accounts` cron made irreversible, so
what they mostly assert is the *timing*: that an account is restorable while the
window is open, gone the moment it closes, and that a ban is not something a
deletion can be used to shed.

The two tests that already existed for this (`test_deleted_account_returns_403`
and `test_delete_account_then_login_returns_403`) assert only `403`. They stayed
green when the grace window landed and silently started exercising the
pending-deletion branch instead of the gone branch — which is why the assertions
below name `errorCode` rather than the status alone.
"""

import pytest
from unittest.mock import patch

from core.config import config
from helpers import (
    account_exists,
    backdate_deletion,
    body_for,
    make_friends,
    new_identity,
    open_chat,
    register,
    set_status,
)


def _delete(client, user):
    resp = client.delete("/users/me", headers=user["headers"])
    assert resp.status_code == 200, resp.text
    return resp


class TestDeletionGraceWindow:
    def test_login_inside_the_window_offers_a_restore(self, client, user_a):
        _delete(client, user_a)

        resp = client.post("/auth/login", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 403
        body = resp.json()
        assert body["errorCode"] == "ACCOUNT_PENDING_DELETION"
        # The deadline has to survive the route: the app draws a different
        # screen for this, and the date is the whole content of it.
        assert body["details"]["deletionScheduledAt"]

    def test_registering_again_inside_the_window_offers_a_restore(self, client):
        """Signing up with a mid-deletion account is the same intent as signing in.

        Answering 409 CONFLICT here — which is what an existing UID used to
        get — would tell the user their account is unavailable and give them no
        way to reach it.
        """
        identity = new_identity()
        user = register(client, identity)
        _delete(client, user)

        resp = client.post("/auth/register", json=body_for(identity))

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_PENDING_DELETION"

    def test_reactivate_restores_the_account_and_its_data(self, client, user_a, user_b):
        """The round trip: everything comes back, not just the login."""
        make_friends(client, user_a, user_b)
        client.post("/streaks/start", headers=user_a["headers"])

        _delete(client, user_a)

        resp = client.post("/auth/reactivate", json={"idToken": user_a["idToken"]})
        assert resp.status_code == 200, resp.text
        tokens = resp.json()
        assert tokens["accessToken"] and tokens["refreshToken"]

        headers = {"Authorization": f"Bearer {tokens['accessToken']}"}
        profile = client.get("/users/me", headers=headers)
        assert profile.status_code == 200
        assert profile.json()["id"] == user_a["uid"]

        friends = client.get("/friendships", headers=headers)
        assert friends.status_code == 200
        assert friends.json()["total"] >= 1

    def test_login_works_again_after_reactivation(self, client, user_a):
        _delete(client, user_a)
        client.post("/auth/reactivate", json={"idToken": user_a["idToken"]})

        resp = client.post("/auth/login", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 200

    def test_past_the_window_the_account_reads_as_gone(self, client, user_a):
        _delete(client, user_a)
        backdate_deletion(user_a["uid"], config.ACCOUNT_DELETION_GRACE_DAYS + 1)

        resp = client.post("/auth/login", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_DELETED"
        # No deadline: there is nothing left to offer.
        assert "details" not in resp.json()

    def test_reactivate_past_the_window_is_refused(self, client, user_a):
        _delete(client, user_a)
        backdate_deletion(user_a["uid"], config.ACCOUNT_DELETION_GRACE_DAYS + 1)

        resp = client.post("/auth/reactivate", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_DELETED"

        # And it stayed deleted — a refused restore must not half-apply.
        assert client.post("/auth/login", json={"idToken": user_a["idToken"]}).status_code == 403

    def test_reactivate_on_an_active_account_is_a_conflict(self, client, user_a):
        resp = client.post("/auth/reactivate", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 409
        assert resp.json()["errorCode"] == "ACCOUNT_NOT_DELETED"

    def test_reactivate_needs_a_token_for_that_account(self, client, user_a, user_b):
        """user_b's token restores user_b's account, never user_a's.

        The UID is public — it is handed out in friend lists and search — so if
        anything but the ID token decided whose account is restored, undoing
        someone else's deletion would be a matter of typing their id.
        """
        _delete(client, user_a)

        resp = client.post("/auth/reactivate", json={"idToken": user_b["idToken"]})

        assert resp.status_code == 409  # user_b is active, nothing to restore
        assert client.post("/auth/login", json={"idToken": user_a["idToken"]}).status_code == 403

    def test_deleted_account_cannot_refresh_its_way_back(self, client, user_a):
        """The refresh token outlives the delete by 7 days if nothing checks."""
        _delete(client, user_a)

        resp = client.post("/auth/refresh", json={"refreshToken": user_a["refresh"]})

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_UNAVAILABLE"


class TestBannedAccount:
    def test_banned_cannot_log_in(self, client, user_a):
        set_status(user_a["uid"], config.STATUS_CODES["banned"])

        resp = client.post("/auth/login", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_BANNED"

    def test_banned_access_token_stops_working(self, client, user_a):
        """The ban has to bite before the 15-minute token expires on its own."""
        assert client.get("/users/me", headers=user_a["headers"]).status_code == 200

        set_status(user_a["uid"], config.STATUS_CODES["banned"])

        assert client.get("/users/me", headers=user_a["headers"]).status_code == 403

    def test_banned_cannot_refresh(self, client, user_a):
        set_status(user_a["uid"], config.STATUS_CODES["banned"])

        resp = client.post("/auth/refresh", json={"refreshToken": user_a["refresh"]})

        assert resp.status_code == 403

    def test_banned_cannot_register_again(self, client):
        """Re-running sign-up with the same Google account must not mint a new one."""
        identity = new_identity()
        user = register(client, identity)
        set_status(user["uid"], config.STATUS_CODES["banned"])

        resp = client.post("/auth/register", json=body_for(identity))

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_BANNED"

    def test_deleting_then_reactivating_does_not_shed_a_ban(self, client, user_a):
        """Deleting is not a laundry cycle.

        Without the ban check ordered ahead of the deletion branch, a banned
        user could delete the account and restore it back into `enabled`.
        """
        _delete(client, user_a)
        set_status(user_a["uid"], config.STATUS_CODES["banned"])

        resp = client.post("/auth/reactivate", json={"idToken": user_a["idToken"]})

        assert resp.status_code == 403
        assert resp.json()["errorCode"] == "ACCOUNT_BANNED"
        assert client.post("/auth/login", json={"idToken": user_a["idToken"]}).status_code == 403


class TestAdminStatusRoute:
    """`PUT /users/{id}/status/{status}` — bans, unbans, undeletes.

    Before `getAdminUser` it was authenticated-only, so any signed-in user could
    lift their own ban or ban anyone else, which made every check in
    TestBannedAccount above unenforceable in practice.
    """

    def test_a_normal_user_cannot_change_anyone_status(self, client, user_a, user_b):
        resp = client.put(
            f"/users/{user_b['uid']}/status/{config.STATUS_CODES['banned']}",
            headers=user_a["headers"],
        )

        assert resp.status_code == 404
        # And user_b is untouched.
        assert client.post("/auth/login", json={"idToken": user_b["idToken"]}).status_code == 200

    def test_a_normal_user_cannot_unban_themselves(self, client, user_a):
        set_status(user_a["uid"], config.STATUS_CODES["banned"])

        resp = client.put(
            f"/users/{user_a['uid']}/status/{config.STATUS_CODES['enabled']}",
            headers=user_a["headers"],
        )

        # 403 from the account-status check in getCurrentUser, 404 from the
        # allowlist — either way the ban holds. What must not happen is a 200.
        assert resp.status_code in (403, 404)
        assert client.post("/auth/login", json={"idToken": user_a["idToken"]}).status_code == 403

    def test_an_admin_can_ban_and_unban(self, client, user_a, user_b):
        with patch.object(config, "ADMIN_USER_IDS", [user_a["uid"]]):
            resp = client.put(
                f"/users/{user_b['uid']}/status/{config.STATUS_CODES['banned']}",
                headers=user_a["headers"],
            )
            assert resp.status_code == 200, resp.text
            assert client.post("/auth/login", json={"idToken": user_b["idToken"]}).status_code == 403

            resp = client.put(
                f"/users/{user_b['uid']}/status/{config.STATUS_CODES['enabled']}",
                headers=user_a["headers"],
            )
            assert resp.status_code == 200, resp.text

        assert client.post("/auth/login", json={"idToken": user_b["idToken"]}).status_code == 200


class TestPurge:
    """The cron job, against a real database.

    `jobs.purgeAccounts` builds its own session from `core.database`, which the
    root conftest replaced with a MagicMock — so it is pointed back at the test
    engine here, the same way `real_account_status_lookups` does for the auth
    dependency.
    """

    @pytest.fixture
    def run_purge(self):
        import conftest as integrationConftest
        import jobs.purgeAccounts as purgeModule

        class _RealDatabase:
            @property
            def session(self):
                return integrationConftest._SessionFactory()

            @property
            def engine(self):
                return integrationConftest._engine

        def _run():
            with patch.object(purgeModule, "database", _RealDatabase()):
                return purgeModule.purgeExpiredAccounts()

        return _run

    def test_purges_an_account_past_its_window(self, client, user_a, run_purge):
        _delete(client, user_a)
        backdate_deletion(user_a["uid"], config.ACCOUNT_DELETION_GRACE_DAYS + 1)

        assert run_purge() == 0

        assert not account_exists(user_a["uid"])
        # And the UID stops resolving at all, rather than resolving to a ghost.
        assert client.post("/auth/login", json={"idToken": user_a["idToken"]}).status_code == 401

    def test_purge_leaves_accounts_inside_the_window(self, client, user_a, run_purge):
        _delete(client, user_a)

        assert run_purge() == 0

        assert account_exists(user_a["uid"])
        # Still restorable, which is the entire point of the window.
        assert client.post("/auth/reactivate", json={"idToken": user_a["idToken"]}).status_code == 200

    def test_purge_leaves_active_accounts_alone(self, client, user_a, run_purge):
        assert run_purge() == 0

        assert account_exists(user_a["uid"])
        assert client.get("/users/me", headers=user_a["headers"]).status_code == 200

    def test_purging_takes_the_account_data_with_it(self, client, user_a, user_b, run_purge):
        """The cascade from migration 20260901_01, end to end.

        The other participant's copy of the conversation goes too: both halves
        of a 1-on-1 chat are one `tb_3` row, and keeping it would leave a chat
        pointing at a user id that no longer resolves.
        """
        open_chat(client, user_a, user_b)
        client.post("/streaks/start", headers=user_a["headers"])

        assert client.get("/chats", headers=user_b["headers"]).json()["total"] == 1

        _delete(client, user_a)
        backdate_deletion(user_a["uid"], config.ACCOUNT_DELETION_GRACE_DAYS + 1)
        assert run_purge() == 0

        assert not account_exists(user_a["uid"])
        # user_b survives intact, minus the conversation they shared.
        assert client.get("/users/me", headers=user_b["headers"]).status_code == 200
        assert client.get("/chats", headers=user_b["headers"]).json()["total"] == 0
