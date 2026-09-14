"""The moderation queue and its review lock (§ moderation).

With one moderator none of this matters. With two, the failure is specific and
expensive: both open the same report, both read the same private conversation,
and the account is punished twice — or one of them dismisses what the other
just actioned.
"""

import pytest
from sqlalchemy import text

from helpers import as_admin, new_identity, register


ADMIN_A = "uid-moderator"
ADMIN_B = "uid-moderator-2"


@pytest.fixture
def moderators(client):
    """Two accounts on the allowlist at once.

    Username and e-mail are both spelled out: `new_identity` derives each from
    the first eight characters of the uid, and these two uids share them — the
    second registration would come back 409 on a collision that has nothing to
    do with what is being tested.
    """
    first = register(client, new_identity(
        uid=ADMIN_A, username="moderator_one", email="mod1@example.com"
    ))
    second = register(client, new_identity(
        uid=ADMIN_B, username="moderator_two", email="mod2@example.com"
    ))
    with as_admin(ADMIN_A):
        from core.config import config
        config.ADMIN_USER_IDS = list(config.ADMIN_USER_IDS) + [ADMIN_B]
        yield first, second


def _file(client, reporter, reportedUid, reason="harassment"):
    return client.post(f"/reports/{reportedUid}", json={"reason": reason}, headers=reporter["headers"])


def _stale(reportId, minutes):
    """Age a claim, so the expiry can be tested without waiting half an hour."""
    from helpers import _engine

    with _engine().connect() as conn:
        conn.execute(
            text("UPDATE tb_10 SET cl_10j = NOW() - make_interval(mins => :m) WHERE cl_10a = :id"),
            {"m": minutes, "id": reportId},
        )
        conn.commit()


class TestClaiming:
    def test_claiming_marks_the_report_and_shows_in_the_queue(self, client, user_a, user_b, moderators):
        first, _ = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]

        claimed = client.post(f"/reports/{reportId}/claim", headers=first["headers"])
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["locked_by"] == ADMIN_A

        queue = client.get("/reports?status=4", headers=first["headers"]).json()
        row = next(r for r in queue["reports"] if r["id"] == reportId)
        assert row["locked_by"] == ADMIN_A
        assert row["locked_at"] is not None

    def test_a_second_moderator_is_turned_away(self, client, user_a, user_b, moderators):
        first, second = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])

        collision = client.post(f"/reports/{reportId}/claim", headers=second["headers"])
        assert collision.status_code == 409

    def test_and_cannot_resolve_it_either(self, client, user_a, user_b, moderators):
        """The collision that ends with two punishments for one offence."""
        first, second = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])

        resp = client.put(f"/reports/{reportId}/resolve/accepted", headers=second["headers"])
        assert resp.status_code == 409

        # Still open, still theirs to decide.
        assert client.get(f"/reports/{reportId}", headers=first["headers"]).json()["status"] == 4

    def test_the_holder_resolves_it_and_the_lock_goes(self, client, user_a, user_b, moderators):
        first, _ = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])

        resolved = client.put(f"/reports/{reportId}/resolve/accepted", headers=first["headers"])
        assert resolved.status_code == 200

        queue = client.get("/reports", headers=first["headers"]).json()
        row = next(r for r in queue["reports"] if r["id"] == reportId)
        assert row["status"] == 5
        # A decided report is nobody's to review; a lock left behind would make
        # the queue's "in review" column lie for half an hour.
        assert row["locked_by"] is None

    def test_resolving_without_claiming_still_works(self, client, user_a, user_b, moderators):
        """A single moderator never has to think about locks."""
        first, _ = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]

        assert client.put(
            f"/reports/{reportId}/resolve/ignored", headers=first["headers"]
        ).status_code == 200


class TestTheLockExpires:
    def test_a_stale_claim_can_be_taken_over(self, client, user_a, user_b, moderators):
        """A moderator who closed the tab must not park a report for ever."""
        from core.config import config

        first, second = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])
        _stale(reportId, config.REPORT_LOCK_MINUTES + 5)

        taken = client.post(f"/reports/{reportId}/claim", headers=second["headers"])
        assert taken.status_code == 200
        assert taken.json()["locked_by"] == ADMIN_B

    def test_a_fresh_claim_still_holds(self, client, user_a, user_b, moderators):
        from core.config import config

        first, second = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])
        _stale(reportId, max(config.REPORT_LOCK_MINUTES - 5, 1))

        assert client.post(
            f"/reports/{reportId}/claim", headers=second["headers"]
        ).status_code == 409


class TestReleasing:
    def test_releasing_puts_it_back_without_a_decision(self, client, user_a, user_b, moderators):
        first, second = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])

        released = client.delete(f"/reports/{reportId}/claim", headers=first["headers"])
        assert released.status_code == 200
        assert released.json()["locked_by"] is None
        assert released.json()["status"] == 4  # still open

        assert client.post(
            f"/reports/{reportId}/claim", headers=second["headers"]
        ).status_code == 200

    def test_nobody_steals_a_live_lock_by_releasing_it(self, client, user_a, user_b, moderators):
        first, second = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])

        assert client.delete(
            f"/reports/{reportId}/claim", headers=second["headers"]
        ).status_code == 409


class TestWhoCanTouchTheQueue:
    def test_an_ordinary_user_cannot_claim_or_release(self, client, user_a, user_b, moderators):
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]

        assert client.post(f"/reports/{reportId}/claim", headers=user_a["headers"]).status_code == 404
        assert client.delete(f"/reports/{reportId}/claim", headers=user_a["headers"]).status_code == 404

    def test_the_reporter_is_never_told_who_is_reading_it(self, client, user_a, user_b, moderators):
        """Naming the moderator gives the reporter a person to complain about,
        and answers a question they never asked."""
        first, _ = moderators
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        client.post(f"/reports/{reportId}/claim", headers=first["headers"])

        mine = client.get("/reports/mine", headers=user_a["headers"]).json()
        assert mine["reports"][0]["id"] == reportId
        assert "locked_by" not in mine["reports"][0]
