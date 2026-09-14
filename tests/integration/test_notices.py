"""Moderation notices, end to end (§ moderation).

The rung between silence and a ban. What these guard is what a notice is for
and what it must never carry: the user learns what conduct was named and where
to appeal, and never who reported them.
"""

import pytest

from helpers import as_admin, new_identity, register


ADMIN_UID = "uid-moderator"


@pytest.fixture
def admin(client):
    user = register(client, new_identity(uid=ADMIN_UID))
    with as_admin(ADMIN_UID):
        yield user


def _warn(client, admin, uid, reason="harassment", message=None):
    body = {"reason": reason}
    if message is not None:
        body["message"] = message
    return client.post(f"/users/{uid}/warn", json=body, headers=admin["headers"])


class TestWarning:
    def test_a_warning_reaches_the_user_and_changes_nothing(self, client, user_a, admin):
        resp = _warn(client, admin, user_a["uid"], message="Please keep it civil.")
        assert resp.status_code == 201, resp.text

        mine = client.get("/notices/mine?pending=true", headers=user_a["headers"]).json()
        assert mine["total"] == 1
        assert mine["notices"][0]["kind"] == "warning"
        assert mine["notices"][0]["reason"] == "harassment"
        assert mine["notices"][0]["message"] == "Please keep it civil."

        # The account is untouched — that is the whole point of the rung.
        assert client.get("/users/me", headers=user_a["headers"]).status_code == 200
        assert client.post("/auth/login", json={"idToken": user_a["idToken"]}).status_code == 200

    def test_a_notice_never_names_the_moderator_or_the_reporter(self, client, user_a, user_b, admin):
        client.post(
            f"/reports/{user_a['uid']}", json={"reason": "harassment"}, headers=user_b["headers"]
        )
        _warn(client, admin, user_a["uid"], message="Stop messaging them.")

        body = client.get("/notices/mine", headers=user_a["headers"]).text
        assert user_b["uid"] not in body, "the reporter must never surface"
        assert ADMIN_UID not in body, "nor the moderator's uid"

    def test_html_in_the_moderators_words_is_stripped(self, client, user_a, admin):
        _warn(client, admin, user_a["uid"], message="<script>x</script>stop")
        mine = client.get("/notices/mine", headers=user_a["headers"]).json()
        assert "<script>" not in mine["notices"][0]["message"]

    def test_a_safety_report_is_not_answered_with_a_warning(self, client, user_a, admin):
        resp = _warn(client, admin, user_a["uid"], reason="self_harm")
        assert resp.status_code == 400
        assert "crisis" in resp.json()["message"].lower()
        assert client.get("/notices/mine", headers=user_a["headers"]).json()["total"] == 0

    def test_warning_is_admin_only(self, client, user_a, user_b):
        resp = _warn(client, {"headers": user_a["headers"]}, user_b["uid"])
        assert resp.status_code == 404
        assert client.get("/notices/mine", headers=user_b["headers"]).json()["total"] == 0


class TestSuspensionNotice:
    def test_a_suspension_tells_the_user_when_they_come_back(self, client, user_a, admin):
        resp = client.put(
            f"/users/{user_a['uid']}/suspend",
            json={"days": 3, "reason": "harassment", "message": "Three days. Come back calmer."},
            headers=admin["headers"],
        )
        assert resp.status_code == 200

        # Lift it early, the way a moderator would, and sign back in.
        client.put(f"/users/{user_a['uid']}/status/1", headers=admin["headers"])
        login = client.post("/auth/login", json={"idToken": user_a["idToken"]})
        headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}

        mine = client.get("/notices/mine?pending=true", headers=headers).json()
        assert mine["total"] == 1
        assert mine["notices"][0]["kind"] == "suspension"
        assert mine["notices"][0]["message"] == "Three days. Come back calmer."


class TestAcknowledging:
    def test_acknowledging_clears_it_from_pending_but_keeps_it_on_file(self, client, user_a, admin):
        noticeId = _warn(client, admin, user_a["uid"]).json()["id"]

        acked = client.post(f"/notices/{noticeId}/ack", headers=user_a["headers"])
        assert acked.status_code == 200
        assert acked.json()["acknowledged_at"] is not None

        assert client.get("/notices/mine?pending=true", headers=user_a["headers"]).json()["total"] == 0
        # Kept: an appeal is reviewed by someone who has to see what was said.
        assert client.get("/notices/mine", headers=user_a["headers"]).json()["total"] == 1

    def test_nobody_acknowledges_someone_elses_notice(self, client, user_a, user_b, admin):
        noticeId = _warn(client, admin, user_a["uid"]).json()["id"]

        assert client.post(f"/notices/{noticeId}/ack", headers=user_b["headers"]).status_code == 404
        assert client.get("/notices/mine?pending=true", headers=user_a["headers"]).json()["total"] == 1

    def test_the_list_is_only_ever_your_own(self, client, user_a, user_b, admin):
        _warn(client, admin, user_a["uid"])
        assert client.get("/notices/mine", headers=user_b["headers"]).json()["total"] == 0

    def test_notices_come_back_oldest_first(self, client, user_a, admin):
        """Two waiting notices are a sequence: the warning explains the ban."""
        _warn(client, admin, user_a["uid"], reason="spam")
        client.put(
            f"/users/{user_a['uid']}/suspend",
            json={"days": 1, "reason": "spam"},
            headers=admin["headers"],
        )

        # Read after the ban is lifted, because a suspended account cannot read
        # anything — including this. The notice waits for them, which is the
        # flow the app implements: it is shown on the next open.
        assert client.get("/notices/mine", headers=user_a["headers"]).status_code == 403
        client.put(f"/users/{user_a['uid']}/status/1", headers=admin["headers"])
        login = client.post("/auth/login", json={"idToken": user_a["idToken"]})
        headers = {"Authorization": f"Bearer {login.json()['accessToken']}"}

        mine = client.get("/notices/mine", headers=headers).json()["notices"]
        assert [n["kind"] for n in mine] == ["warning", "suspension"]
