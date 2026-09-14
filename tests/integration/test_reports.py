"""Reporting another user, end to end (§ moderation).

The invariant these guard is who can *read* a report: the reporter, and nobody
else. A reported user learning that they were reported — or by whom — is the
failure that stops people reporting at all.
"""

import pytest


def _file(client, reporter, reportedUid, reason="harassment", details=None):
    body = {"reason": reason}
    if details is not None:
        body["details"] = details
    return client.post(f"/reports/{reportedUid}", json=body, headers=reporter["headers"])


class TestFileReport:
    def test_report_returns_201_open(self, client, user_a, user_b):
        resp = _file(client, user_a, user_b["uid"])
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == 4  # pending — unreviewed
        assert body["reporter"] == user_a["uid"]
        assert body["reported"] == user_b["uid"]

    def test_details_are_stored(self, client, user_a, user_b):
        resp = _file(client, user_a, user_b["uid"], details="They keep messaging me.")
        assert resp.json()["details"] == "They keep messaging me."

    def test_html_in_details_is_stripped(self, client, user_a, user_b):
        resp = _file(client, user_a, user_b["uid"], details="<script>x</script>stop")
        assert "<script>" not in resp.json()["details"]

    def test_cannot_report_yourself(self, client, user_a):
        assert _file(client, user_a, user_a["uid"]).status_code == 400

    def test_cannot_report_an_unknown_user(self, client, user_a):
        assert _file(client, user_a, "uid-that-does-not-exist").status_code == 404

    def test_unknown_reason_is_rejected(self, client, user_a, user_b):
        assert _file(client, user_a, user_b["uid"], reason="because").status_code == 422

    def test_second_report_while_the_first_is_open_returns_409(self, client, user_a, user_b):
        assert _file(client, user_a, user_b["uid"]).status_code == 201
        assert _file(client, user_a, user_b["uid"], reason="spam").status_code == 409

    def test_two_reporters_may_both_report_the_same_user(self, client, user_a, user_b):
        from helpers import register
        user_c = register(client)
        assert _file(client, user_a, user_b["uid"]).status_code == 201
        assert _file(client, user_c, user_b["uid"]).status_code == 201

    def test_reporting_does_not_require_a_friendship(self, client, user_a, user_b):
        """Harassment arrives from strangers too — no relationship is needed."""
        assert client.get("/friendships", headers=user_a["headers"]).json()["total"] == 0
        assert _file(client, user_a, user_b["uid"]).status_code == 201

    def test_reporting_changes_nothing_about_the_relationship(self, client, user_a, user_b):
        client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"])
        _file(client, user_a, user_b["uid"])
        friendships = client.get("/friendships", headers=user_a["headers"]).json()
        assert friendships["friendships"][0]["status"] == 4  # still just pending

    def test_anonymous_cannot_report(self, client, user_b):
        resp = client.post(f"/reports/{user_b['uid']}", json={"reason": "spam"})
        assert resp.status_code in (401, 403)


class TestReadReports:
    def test_reporter_sees_their_own_report(self, client, user_a, user_b):
        _file(client, user_a, user_b["uid"])
        resp = client.get("/reports/mine", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_reported_user_sees_nothing(self, client, user_a, user_b):
        _file(client, user_a, user_b["uid"])
        resp = client.get("/reports/mine", headers=user_b["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_a_third_party_sees_nothing(self, client, user_a, user_b):
        from helpers import register
        user_c = register(client)
        _file(client, user_a, user_b["uid"])
        assert client.get("/reports/mine", headers=user_c["headers"]).json()["total"] == 0


class TestModerationIsAdminOnly:
    """ADMIN_USER_IDS is empty in the test environment, so nobody is an admin."""

    def test_queue_is_not_readable_by_an_ordinary_user(self, client, user_a):
        assert client.get("/reports", headers=user_a["headers"]).status_code == 404

    def test_single_report_is_not_readable_by_its_reporter(self, client, user_a, user_b):
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        resp = client.get(f"/reports/{reportId}", headers=user_a["headers"])
        assert resp.status_code == 404

    def test_resolve_is_not_reachable_by_an_ordinary_user(self, client, user_a, user_b):
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        resp = client.put(f"/reports/{reportId}/resolve/ignored", headers=user_a["headers"])
        assert resp.status_code == 404
        assert client.get("/reports/mine", headers=user_a["headers"]).json()["reports"][0]["status"] == 4
