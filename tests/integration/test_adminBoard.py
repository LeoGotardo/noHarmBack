"""Integration tests for the admin board's HTTP surface.

Three things are worth holding in place here, and none of them is a number:

- **the gate** — every route answers 404, not 403, to anyone outside the
  allowlist, so an ordinary caller cannot even confirm the board exists;
- **what the responses do not carry** — no e-mail, no streak, nothing about
  anyone's recovery. The list is browsable, so every field on it is readable in
  bulk by whoever holds one admin credential;
- **the audit** — opening the board is recorded, for the same reason reading a
  report's evidence is.
"""

import pytest
from sqlalchemy import text

from core.config import config
from helpers import body_for, new_identity


ROUTES = ["/admin/overview", "/admin/users", "/admin/errors", "/admin/access"]


@pytest.fixture
def admin(client):
    """An account on the ADMIN_USER_IDS allowlist."""
    identity = new_identity()
    resp = client.post("/auth/register", json=body_for(identity))
    assert resp.status_code == 201

    original = list(config.ADMIN_USER_IDS)
    config.ADMIN_USER_IDS = original + [identity["uid"]]
    try:
        yield {
            "uid": identity["uid"],
            "headers": {"Authorization": f"Bearer {resp.json()['accessToken']}"},
        }
    finally:
        config.ADMIN_USER_IDS = original


class TestTheGate:
    @pytest.mark.parametrize("route", ROUTES)
    def test_an_ordinary_account_gets_404_not_403(self, client, user_a, route):
        """Whether an admin surface exists here is not something an ordinary
        caller needs confirmed."""
        assert client.get(route, headers=user_a["headers"]).status_code == 404

    @pytest.mark.parametrize("route", ROUTES)
    def test_no_token_is_refused(self, client, route):
        assert client.get(route).status_code in (401, 403)

    @pytest.mark.parametrize("route", ROUTES)
    def test_an_admin_is_let_through(self, client, admin, route):
        assert client.get(route, headers=admin["headers"]).status_code == 200


class TestOverview:
    def test_it_answers_with_every_panel(self, client, admin):
        body = client.get("/admin/overview", headers=admin["headers"]).json()

        assert set(body) == {
            "accounts", "moderation", "health", "series", "security", "generated_at"
        }
        assert set(body["accounts"]) == {
            "by_status", "created", "bans", "sanctions", "consent_debt"
        }
        # Status names rather than the integers STATUS_CODES happens to use.
        assert "enabled" in body["accounts"]["by_status"]

    def test_health_reads_zero_when_nothing_is_wrong(self, client, admin):
        """The point of the panel: every field is a failure, so a healthy
        system shows nothing rather than showing activity."""
        health = client.get("/admin/overview", headers=admin["headers"]).json()["health"]

        assert health["purge_overdue"] == 0
        assert health["evidence_overdue"] == 0
        assert health["error_occurrences_24h"] == 0

    def test_it_never_carries_an_account_identifier(self, client, admin, user_a):
        """It aggregates and does not enumerate. A username or a uid appearing
        in the overview would mean some count became a list."""
        raw = client.get("/admin/overview", headers=admin["headers"]).text

        assert user_a["uid"] not in raw
        assert user_a["identity"]["username"] not in raw

    def test_a_second_read_is_served_from_cache(self, client, admin):
        """`generated_at` is when the numbers were computed, not when they were
        asked for — so the panel can say it rather than imply a fresh read."""
        first = client.get("/admin/overview", headers=admin["headers"]).json()
        second = client.get("/admin/overview", headers=admin["headers"]).json()

        assert first["generated_at"] == second["generated_at"]

    def test_opening_the_board_is_audited(self, client, admin, db):
        """A power to look that leaves no trace is indistinguishable from one
        being abused, and this board can list every account in the system.

        Asserted against `tb_7` rather than through the audit-log endpoint:
        what matters is that the row exists, and routing the check through a
        second surface would make this fail for reasons that have nothing to do
        with the board.
        """
        before = db.session.execute(
            text("SELECT count(*) FROM tb_7 WHERE cl_7b = 16 AND cl_7c = :uid"),
            {"uid": admin["uid"]},
        ).scalar()

        client.get("/admin/overview", headers=admin["headers"])

        after = db.session.execute(
            text("SELECT count(*) FROM tb_7 WHERE cl_7b = 16 AND cl_7c = :uid"),
            {"uid": admin["uid"]},
        ).scalar()

        assert after == before + 1


class TestSecurityPanel:
    def test_a_burst_of_404s_is_flagged(self, client, admin):
        """The end-to-end shape of path scanning: many refusals from one
        address inside the window, surfaced as a prompt to look."""
        from core.config import config as appConfig
        from security.middleware import _suspicious

        _suspicious._redis.delete(*(_suspicious._redis.keys("nh:sus:*") or ["_none"]))

        for i in range(appConfig.SUSPICIOUS_NOT_FOUND_THRESHOLD + 2):
            client.get(f"/definitely-not-a-route-{i}")

        flagged = _suspicious.flagged()
        assert flagged, "expected the scanning address to be flagged"
        assert "notfound" in flagged[0]["reasons"]

    def test_success_is_never_counted(self, client, admin):
        """The whole affordability argument: a write on failures, not on
        traffic."""
        from security.middleware import _suspicious

        _suspicious._redis.delete(*(_suspicious._redis.keys("nh:sus:*") or ["_none"]))

        for _ in range(5):
            assert client.get("/admin/overview", headers=admin["headers"]).status_code == 200

        assert _suspicious._redis.keys("nh:sus:*") == []

    def test_the_panel_reports_the_window_it_measured(self, client, admin):
        from core.config import config as appConfig

        body = client.get("/admin/overview", headers=admin["headers"]).json()

        assert body["security"]["window_seconds"] == appConfig.SUSPICIOUS_WINDOW_SECONDS
        assert isinstance(body["security"]["flagged_addresses"], list)


class TestUserList:
    def test_it_shows_the_accounts_the_app_hides(self, client, admin, user_a):
        """`GET /users` hides deleted, banned and blocked — right for the app,
        useless here, since those are what an administrator is looking for."""
        suspended = client.put(
            f"/users/{user_a['uid']}/suspend",
            json={"days": None},
            headers=admin["headers"],
        )
        assert suspended.status_code == 200, suspended.text

        body = client.get(
            "/admin/users", params={"pageSize": 100}, headers=admin["headers"]
        ).json()
        rows = {row["id"]: row for row in body["items"]}

        assert user_a["uid"] in rows
        assert rows[user_a["uid"]]["status"] == config.STATUS_CODES["banned"]

    def test_it_carries_no_email_and_nothing_about_recovery(self, client, admin, user_a):
        body = client.get("/admin/users", headers=admin["headers"]).json()

        assert body["items"], "expected at least one account"
        for row in body["items"]:
            assert set(row) == {
                "id", "username", "status", "created_at", "banned_until",
                "deleted_at", "must_change_username", "picture_blocked",
            }

    def test_the_status_filter_narrows_the_query_not_the_page(self, client, admin, user_a):
        """Filtering the page after taking it answers "the banned accounts that
        happen to be on page one", and reports the unfiltered total beside it."""
        client.put(
            f"/users/{user_a['uid']}/suspend",
            json={"days": None},
            headers=admin["headers"],
        )

        body = client.get(
            "/admin/users",
            params={"status": config.STATUS_CODES["banned"], "pageSize": 1},
            headers=admin["headers"],
        ).json()

        assert body["items"], "the banned account should survive a page size of one"
        assert all(row["status"] == config.STATUS_CODES["banned"] for row in body["items"])
        # And the total counts the filtered set, not everyone.
        assert body["total"] == 1

    def test_the_response_is_paginated(self, client, admin):
        body = client.get(
            "/admin/users", params={"page": 1, "pageSize": 1}, headers=admin["headers"]
        ).json()

        assert body["pageSize"] == 1
        assert "totalPages" in body and "hasNext" in body
