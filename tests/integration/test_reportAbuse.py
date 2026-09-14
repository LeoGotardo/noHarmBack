"""The ceilings that stop the report queue being a harassment tool.

Filing a report is free, invisible to its target, and needs no relationship
with them — which is exactly what makes it usable by someone being harassed and
usable *for* harassing. Everything here is the second half of that trade.

Two rules shape every test below:

- **A first report about someone is never refused.** Every refusal here follows
  either a moderator's decision or a volume this user has already put into the
  queue.
- **Nothing is ever actioned automatically.** A pile of reports against one
  account raises a flag for a human and changes nothing about the account.
"""

import pytest

from helpers import (
    as_admin,
    backdate_report_decision,
    new_identity,
    register,
    set_status,
)


ADMIN = "uid-abuse-moderator"


@pytest.fixture
def moderator(client):
    """One account on the allowlist, for resolving reports inside a test."""
    mod = register(client, new_identity(
        uid=ADMIN, username="abuse_mod", email="abusemod@example.com"
    ))
    with as_admin(ADMIN):
        yield mod


def _newUser(client):
    """A throwaway account, past the per-IP ceiling on `/auth/register`.

    Several tests here need five or more accounts, and every one of them
    registers from the TestClient's single address — so `5/minute` on that route
    refuses the sixth for a reason that has nothing to do with what is being
    tested. The report ceilings are the subject; the registration one is reset
    out of the way.
    """
    from security.limiter import limiter

    try:
        limiter.reset()
    except Exception:
        pass
    return register(client)


def _file(client, reporter, reportedUid, reason="harassment"):
    return client.post(
        f"/reports/{reportedUid}",
        json={"reason": reason},
        headers=reporter["headers"],
    )


def _resolve(client, moderator, reportId, decision):
    resp = client.put(f"/reports/{reportId}/resolve/{decision}", headers=moderator["headers"])
    assert resp.status_code == 200, resp.text
    return resp


# ── the pair cooldown ─────────────────────────────────────────────────────────

class TestDismissalCooldown:
    def test_a_dismissed_report_cannot_be_refiled_at_once(self, client, user_a, user_b, moderator):
        """Without this, "dismissed" is a round trip rather than a decision."""
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        _resolve(client, moderator, reportId, "ignored")

        again = _file(client, user_a, user_b["uid"], reason="spam")
        assert again.status_code == 409, again.text
        body = again.json()
        assert body["errorCode"] == "REPORT_RECENTLY_DISMISSED"
        # The date it lifts, which the client draws "you can report again on…"
        # from. It only survives because the route lets NoHarmException reach
        # the handler instead of flattening it to `detail`.
        assert body["details"]["canReportAgainAt"] is not None

    def test_an_actioned_report_does_not_block_the_next_one(self, client, user_a, user_b, moderator):
        """Being right the first time must not make reporting harder the second."""
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        _resolve(client, moderator, reportId, "accepted")

        again = _file(client, user_a, user_b["uid"], reason="spam")
        assert again.status_code == 201, again.text

    def test_the_cooldown_lapses(self, client, user_a, user_b, moderator):
        from core.config import config

        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        _resolve(client, moderator, reportId, "ignored")
        backdate_report_decision(reportId, config.REPORT_DISMISSED_COOLDOWN_DAYS + 1)

        again = _file(client, user_a, user_b["uid"], reason="spam")
        assert again.status_code == 201, again.text

    def test_it_is_per_pair_not_per_reporter(self, client, user_a, user_b, moderator):
        """A dismissal about one person says nothing about reporting another."""
        user_c = _newUser(client)
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        _resolve(client, moderator, reportId, "ignored")

        assert _file(client, user_a, user_c["uid"]).status_code == 201

    def test_it_does_not_stop_someone_else_reporting_the_same_user(self, client, user_a, user_b, moderator):
        user_c = _newUser(client)
        reportId = _file(client, user_a, user_b["uid"]).json()["id"]
        _resolve(client, moderator, reportId, "ignored")

        assert _file(client, user_c, user_b["uid"]).status_code == 201


# ── the backlog cap ───────────────────────────────────────────────────────────

class TestOpenReportCap:
    def _fill(self, client, reporter):
        """File REPORT_MAX_OPEN reports, each about a different person."""
        from core.config import config

        targets = [_newUser(client) for _ in range(config.REPORT_MAX_OPEN)]
        ids = []
        for target in targets:
            resp = _file(client, reporter, target["uid"])
            assert resp.status_code == 201, resp.text
            ids.append(resp.json()["id"])
        return ids

    def test_one_reporter_cannot_fill_the_queue(self, client, user_a):
        self._fill(client, user_a)
        extra = _newUser(client)

        refused = _file(client, user_a, extra["uid"])
        assert refused.status_code == 429, refused.text

    def test_resolving_one_frees_a_slot(self, client, user_a, moderator):
        """The cap clears itself as the queue moves — it is not a lifetime total."""
        ids = self._fill(client, user_a)
        extra = _newUser(client)
        assert _file(client, user_a, extra["uid"]).status_code == 429

        _resolve(client, moderator, ids[0], "accepted")
        assert _file(client, user_a, extra["uid"]).status_code == 201

    def test_the_cap_is_per_reporter(self, client, user_a, user_b):
        self._fill(client, user_a)
        extra = _newUser(client)

        assert _file(client, user_a, extra["uid"]).status_code == 429
        assert _file(client, user_b, extra["uid"]).status_code == 201


# ── the per-account quota ─────────────────────────────────────────────────────

class TestReporterQuota:
    @pytest.fixture
    def tinyQuota(self):
        """Two reports an hour, so the ceiling is reachable inside a test.

        The real numbers are tens per hour and per day; what is being tested is
        that the quota exists and keys on the account, not the value.
        """
        from domain.services import reportService

        limiter = reportService._reportLimiter
        originals = (limiter._shortMax, limiter._longMax)
        limiter._shortMax, limiter._longMax = 2, 2
        yield
        limiter._shortMax, limiter._longMax = originals

    def test_the_quota_refuses_the_next_report(self, client, user_a, tinyQuota):
        for _ in range(2):
            target = _newUser(client)
            assert _file(client, user_a, target["uid"]).status_code == 201

        third = register(client)
        refused = _file(client, user_a, third["uid"])
        assert refused.status_code == 429, refused.text

    def test_the_quota_is_per_account(self, client, user_a, user_b, tinyQuota):
        for _ in range(2):
            target = _newUser(client)
            _file(client, user_a, target["uid"])

        extra = _newUser(client)
        assert _file(client, user_a, extra["uid"]).status_code == 429
        assert _file(client, user_b, extra["uid"]).status_code == 201

    def test_a_refused_report_costs_no_quota(self, client, user_a, user_b, tinyQuota):
        """A duplicate is the app's mistake to have offered, not the user's to pay for."""
        assert _file(client, user_a, user_b["uid"]).status_code == 201
        # Three, not more: the route's own per-IP ceiling is 5/minute, and
        # tripping that would prove nothing about the per-account quota.
        for _ in range(3):
            assert _file(client, user_a, user_b["uid"]).status_code == 409

        # One unit of the two-per-hour quota is left, and the duplicates spent
        # none of it.
        target = _newUser(client)
        assert _file(client, user_a, target["uid"]).status_code == 201


# ── who may file at all ───────────────────────────────────────────────────────

class TestReporterEligibility:
    def test_an_unverified_account_cannot_report(self, client, user_a, user_b):
        """A throwaway that can file reports is a free harassment tool."""
        from core.config import config

        set_status(user_a["uid"], config.STATUS_CODES["pending"])

        refused = _file(client, user_a, user_b["uid"])
        assert refused.status_code == 403, refused.text

    def test_an_enabled_account_still_can(self, client, user_a, user_b):
        assert _file(client, user_a, user_b["uid"]).status_code == 201


# ── what the queue tells a moderator ──────────────────────────────────────────

class TestQueueSignals:
    def test_the_queue_carries_the_reporters_history(self, client, user_a, user_b, moderator):
        first = _file(client, user_a, user_b["uid"]).json()["id"]
        _resolve(client, moderator, first, "ignored")

        target = _newUser(client)
        _file(client, user_a, target["uid"])

        queue = client.get("/reports?status=4", headers=moderator["headers"]).json()
        row = next(r for r in queue["reports"] if r["reporter"] == user_a["uid"])
        assert row["reporter_standing"]["ignored"] == 1
        assert row["reporter_standing"]["accepted"] == 0
        assert row["reporter_standing"]["weight"] < 0.5

    def test_a_first_time_reporter_is_not_penalised(self, client, user_a, user_b, moderator):
        _file(client, user_a, user_b["uid"])

        queue = client.get("/reports?status=4", headers=moderator["headers"]).json()
        row = queue["reports"][0]
        assert row["reporter_standing"]["filed"] == 1
        assert row["reporter_standing"]["weight"] == 0.5

    def test_a_pile_up_against_one_account_is_flagged(self, client, user_b, moderator):
        from core.config import config

        for _ in range(config.REPORT_BRIGADING_THRESHOLD):
            reporter = _newUser(client)
            assert _file(client, reporter, user_b["uid"]).status_code == 201

        queue = client.get("/reports?status=4", headers=moderator["headers"]).json()
        row = queue["reports"][0]
        assert row["open_against_reported"] >= config.REPORT_BRIGADING_THRESHOLD
        assert row["looks_coordinated"] is True

    def test_the_flag_changes_nothing_about_the_account(self, client, user_b, moderator):
        """Acting on a count is exactly what a coordinated group is buying."""
        from core.config import config

        for _ in range(config.REPORT_BRIGADING_THRESHOLD):
            reporter = _newUser(client)
            _file(client, reporter, user_b["uid"])

        profile = client.get("/users/me", headers=user_b["headers"])
        assert profile.status_code == 200
        assert profile.json()["status"] == config.STATUS_CODES["enabled"]

    def test_an_ordinary_report_is_not_flagged(self, client, user_a, user_b, moderator):
        _file(client, user_a, user_b["uid"])

        queue = client.get("/reports?status=4", headers=moderator["headers"]).json()
        assert queue["reports"][0]["looks_coordinated"] is False

    def test_none_of_it_reaches_the_reporter(self, client, user_a, user_b):
        """A reporter must not learn how their own history is weighted."""
        _file(client, user_a, user_b["uid"])

        mine = client.get("/reports/mine", headers=user_a["headers"]).json()
        row = mine["reports"][0]
        assert "reporter_standing" not in row
        assert "open_against_reported" not in row
        assert "looks_coordinated" not in row


class TestPriorityOrdering:
    def test_self_harm_comes_first_whoever_filed_it(self, client, user_b, moderator):
        """A frightened friend with a bad record is still a frightened friend."""
        trusted = _newUser(client)
        _file(client, trusted, user_b["uid"], reason="spam")

        distrusted = _newUser(client)
        dismissed = _file(client, distrusted, user_b["uid"], reason="spam").json()["id"]
        _resolve(client, moderator, dismissed, "ignored")
        backdate_report_decision(dismissed, 400)
        _file(client, distrusted, user_b["uid"], reason="self_harm")

        queue = client.get("/reports?status=4&sort=priority", headers=moderator["headers"]).json()
        assert queue["reports"][0]["reason"] == "self_harm"

    def test_the_default_order_is_still_chronological(self, client, user_a, user_b, moderator):
        first = _file(client, user_a, user_b["uid"]).json()["id"]
        other = _newUser(client)
        second = _file(client, other, user_b["uid"]).json()["id"]

        queue = client.get("/reports?status=4", headers=moderator["headers"]).json()
        ids = [r["id"] for r in queue["reports"]]
        assert ids.index(second) < ids.index(first)

    def test_an_unknown_sort_is_refused(self, client, moderator):
        assert client.get("/reports?sort=whatever", headers=moderator["headers"]).status_code == 422
