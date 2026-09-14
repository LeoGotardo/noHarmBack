"""Evidence behind a report (§ moderation).

A report used to be one sentence of prose: acting on it meant believing one of
two strangers. These guard the three properties the copy has to have to be
worth anything.

- **The server writes it.** The reporter sends a chat id; the messages are read
  out of the database. Nothing typed by the reporter becomes evidence.
- **Only a moderator reads it.** Not the reported user, not even the reporter.
- **It outlives the account.** Deleting your account is otherwise a way to
  erase the complaints about you.
"""

import pytest

from helpers import (
    as_admin,
    backdate_report_resolution,
    open_chat,
    purge_user,
    register,
)


ADMIN_UID = "uid-moderator"


def _file(client, reporter, reportedUid, reason="harassment", details=None, chatId=None):
    body = {"reason": reason}
    if details is not None:
        body["details"] = details
    if chatId is not None:
        body["chatId"] = chatId
    return client.post(f"/reports/{reportedUid}", json=body, headers=reporter["headers"])


def _say(client, sender, chatId, content):
    resp = client.post("/messages", json={"chatId": chatId, "content": content}, headers=sender["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def _evidence(client, reportId, viewer):
    return client.get(f"/reports/{reportId}/evidence", headers=viewer["headers"])


@pytest.fixture
def admin(client):
    """A registered account that is also on the allowlist while the test runs."""
    from helpers import new_identity

    user = register(client, new_identity(uid=ADMIN_UID))
    with as_admin(ADMIN_UID):
        yield user


class TestCapture:
    def test_a_report_always_captures_the_reported_profile(self, client, user_a, user_b, admin):
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]

        items = _evidence(client, reportId, admin).json()["evidence"]
        assert [item["kind"] for item in items] == ["profile"]
        # The username as it was: renaming the account afterwards cannot rewrite
        # what an impersonation report was about.
        assert user_b["identity"]["username"] in items[0]["content"]

    def test_a_named_chat_is_copied_in_full_conversation_order(self, client, user_a, user_b, admin):
        chatId = open_chat(client, user_a, user_b)
        _say(client, user_b, chatId, "you should just give up")
        _say(client, user_a, chatId, "please stop")
        _say(client, user_b, chatId, "no")

        reportId = _file(client, user_a, user_b["uid"], chatId=chatId).json()["id"]

        items = _evidence(client, reportId, admin).json()["evidence"]
        messages = [item for item in items if item["kind"] == "message"]
        assert [m["content"] for m in messages] == [
            "you should just give up",
            "please stop",
            "no",
        ]
        # Both sides. A recorte of one half is not evidence of anything.
        assert {m["author_id"] for m in messages} == {user_a["uid"], user_b["uid"]}

    def test_the_reporter_cannot_put_words_in_the_other_mouth(self, client, user_a, user_b, admin):
        """`details` is the reporter's own prose and stays on the report; the
        evidence is only ever what the database already held."""
        chatId = open_chat(client, user_a, user_b)
        _say(client, user_b, chatId, "what they actually said")

        reportId = _file(
            client, user_a, user_b["uid"],
            details="they said they would find me",
            chatId=chatId,
        ).json()["id"]

        items = _evidence(client, reportId, admin).json()["evidence"]
        quoted = [item["content"] for item in items if item["kind"] == "message"]
        assert quoted == ["what they actually said"]

    def test_a_body_carrying_message_text_is_refused(self, client, user_a, user_b):
        resp = client.post(
            f"/reports/{user_b['uid']}",
            json={"reason": "harassment", "messages": ["a line I invented"]},
            headers=user_a["headers"],
        )
        assert resp.status_code == 422

    def test_a_chat_the_reporter_is_not_in_files_nothing(self, client, user_a, user_b):
        outsider = register(client)
        chatId = open_chat(client, user_b, outsider)

        resp = _file(client, user_a, user_b["uid"], chatId=chatId)
        # RLS hides someone else's chat outright; either way it is refused, and
        # what matters is that no report was filed.
        assert resp.status_code in (403, 404)
        assert client.get("/reports/mine", headers=user_a["headers"]).json()["total"] == 0

    def test_a_chat_that_does_not_involve_the_reported_user_is_400(self, client, user_a, user_b):
        third = register(client)
        chatId = open_chat(client, user_a, third)

        resp = _file(client, user_a, user_b["uid"], chatId=chatId)
        assert resp.status_code == 400
        assert client.get("/reports/mine", headers=user_a["headers"]).json()["total"] == 0

    def test_the_capture_is_tamper_evident(self, client, user_a, user_b, admin):
        from security.encryption import Encryption

        chatId = open_chat(client, user_a, user_b)
        _say(client, user_b, chatId, "one line")
        reportId = _file(client, user_a, user_b["uid"], chatId=chatId).json()["id"]

        items = _evidence(client, reportId, admin).json()["evidence"]
        for item in items:
            assert item["content_hash"] == Encryption.hash(item["content"])


class TestWhoCanRead:
    def test_the_reported_user_cannot_read_it(self, client, user_a, user_b):
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        assert _evidence(client, reportId, user_b).status_code == 404

    def test_the_reporter_cannot_read_it_either(self, client, user_a, user_b):
        """Filing a report is not a licence to re-read the conversation through
        a moderation surface."""
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        assert _evidence(client, reportId, user_a).status_code == 404

    def test_a_moderator_reading_it_is_audited(self, client, user_a, user_b, admin):
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        _evidence(client, reportId, admin)

        # Type 11 is "a moderator read evidence", and the entry names them.
        logs = client.get("/logs/type/11", headers=admin["headers"]).json()
        entries = logs["audit_logs"]
        assert entries, "reading evidence must leave an audit entry"
        assert all(entry["catalyst_id"] == ADMIN_UID for entry in entries)


class TestSurvivingTheAccount:
    def test_a_purged_account_does_not_take_its_reports_with_it(self, client, user_a, user_b, admin):
        chatId = open_chat(client, user_a, user_b)
        _say(client, user_b, chatId, "before they deleted the account")
        reportId = _file(client, user_a, user_b["uid"], chatId=chatId).json()["id"]

        purge_user(user_b["uid"])

        queued = client.get("/reports", headers=admin["headers"]).json()
        mine = [r for r in queued["reports"] if r["id"] == reportId]
        assert mine, "the report must survive the account it names"
        report = mine[0]
        assert report["reported"] is None          # the foreign key went
        assert report["reported_uid"] == user_b["uid"]  # the snapshot did not
        assert report["status"] == 4

        # And the messages are still readable, though tb_4 no longer holds them.
        items = _evidence(client, reportId, admin).json()["evidence"]
        assert "before they deleted the account" in [item["content"] for item in items]

    def test_a_purged_account_does_not_collapse_the_duplicate_check(self, client, user_a, user_b):
        """Two reports about two different purged accounts are two reports —
        matching on the nulled foreign key would make the second a 409."""
        other = register(client)
        assert _file(client, user_a, user_b["uid"]).status_code == 201
        purge_user(user_b["uid"])

        assert _file(client, user_a, other["uid"]).status_code == 201
        assert client.get("/reports/mine", headers=user_a["headers"]).json()["total"] == 2


class TestRetention:
    def _sweep(self, days):
        from infrastructure.database.repositories.reportEvidenceRepository import ReportEvidenceRepository
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        import os

        url = os.environ["TEST_DATABASE_URL"].replace("postgres://", "postgresql://", 1)
        engine = create_engine(url)
        session = sessionmaker(engine)()

        class _Db:
            def __init__(self, session):
                self.session = session
                self.engine = engine

        try:
            return ReportEvidenceRepository(_Db(session)).deleteExpired(days)
        finally:
            session.close()

    def test_evidence_goes_after_the_window_and_the_report_stays(self, client, user_a, user_b, admin):
        chatId = open_chat(client, user_a, user_b)
        _say(client, user_b, chatId, "long since dealt with")
        reportId = _file(client, user_a, user_b["uid"], chatId=chatId).json()["id"]

        client.put(f"/reports/{reportId}/resolve/accepted", headers=admin["headers"])
        backdate_report_resolution(reportId, 200)

        assert self._sweep(180) > 0

        # The decision survives; the copied conversation does not.
        report = client.get(f"/reports/{reportId}", headers=admin["headers"]).json()
        assert report["status"] == 5
        assert _evidence(client, reportId, admin).json()["total"] == 0

    def test_an_open_report_is_never_swept_however_old(self, client, user_a, user_b, admin):
        chatId = open_chat(client, user_a, user_b)
        _say(client, user_b, chatId, "still waiting for a moderator")
        reportId = _file(client, user_a, user_b["uid"], chatId=chatId).json()["id"]
        backdate_report_resolution(reportId, 3650)

        assert self._sweep(180) == 0
        assert _evidence(client, reportId, admin).json()["total"] > 0
