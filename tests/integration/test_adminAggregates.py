"""Integration tests for the counts behind the admin board.

Every one of these groups in SQL, and a mocked session proves nothing about a
`GROUP BY` or a `DISTINCT ON` — the mock returns whatever it was told to. So
they run against a real Postgres, with rows planted to make each branch
distinguishable from the others.

`countOwingReacceptance` gets most of the file. It is the only query here that
cannot be a `GROUP BY`: three different states count as owing and one of them —
an account with no consent row at all — is invisible in `tb_13` entirely.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from core.config import config
from infrastructure.database.models.consentModel import ConsentModel
from infrastructure.database.models.errorLogModel import ErrorLogModel
from infrastructure.database.models.moderationNoticeModel import ModerationNoticeModel
from infrastructure.database.models.reportEvidenceModel import ReportEvidenceModel
from infrastructure.database.models.reportModel import ReportModel
from infrastructure.database.models.userModel import UserModel
from infrastructure.database.repositories.consentRepository import ConsentRepository
from infrastructure.database.repositories.errorLogRepository import ErrorLogRepository
from infrastructure.database.repositories.hostAccessRepository import HostAccessRepository
from infrastructure.database.repositories.moderationNoticeRepository import ModerationNoticeRepository
from infrastructure.database.repositories.reportEvidenceRepository import ReportEvidenceRepository
from infrastructure.database.repositories.reportRepository import ReportRepository
from infrastructure.database.repositories.userRepository import UserRepository
from domain.entities.errorLog import ErrorLog, HostAccess


S = config.STATUS_CODES
NOW = datetime.now(timezone.utc).replace(tzinfo=None)
CURRENT = {"terms": "1.0", "privacy": "1.0"}


def _user(db, uid, status=None, **kw):
    db.session.add(
        UserModel(
            id=uid,
            username=f"u-{uid}",
            email=f"{uid}@agg.test",
            status=S["enabled"] if status is None else status,
            **kw,
        )
    )
    # Flushed before any consent references it: the FK is checked at insert,
    # and SQLAlchemy is free to batch the two tables in the wrong order.
    db.session.flush()


def _consent(db, uid, document, version, withdrawn=None, at=None):
    db.session.add(
        ConsentModel(
            user_id=uid,
            document=document,
            version=version,
            accepted_at=at or NOW,
            withdrawn_at=withdrawn,
        )
    )


class TestOwingReacceptance:
    def test_the_four_states_that_count_as_owing(self, db):
        """Up to date · behind · withdrawn · never answered."""
        _user(db, "ok")
        _consent(db, "ok", "terms", "1.0")
        _consent(db, "ok", "privacy", "1.0")

        _user(db, "behind")
        _consent(db, "behind", "terms", "0.9")
        _consent(db, "behind", "privacy", "1.0")

        _user(db, "withdrew")
        _consent(db, "withdrew", "terms", "1.0", withdrawn=NOW)
        _consent(db, "withdrew", "privacy", "1.0")

        # No consent row at all — the population a newly published policy is
        # aimed at, and the one a query over tb_13 alone cannot see.
        _user(db, "never")

        db.session.commit()

        counts = ConsentRepository(db).countOwingReacceptance(CURRENT)

        assert counts["terms"] == 3       # behind, withdrew, never
        assert counts["privacy"] == 1     # never
        assert counts["any"] == 3

    def test_any_is_not_the_sum(self, db):
        """One account behind on both documents is one account. Adding the
        per-document numbers would report more work than exists."""
        _user(db, "both")
        _consent(db, "both", "terms", "0.9")
        _consent(db, "both", "privacy", "0.8")
        db.session.commit()

        counts = ConsentRepository(db).countOwingReacceptance(CURRENT)

        assert counts["terms"] == 1
        assert counts["privacy"] == 1
        assert counts["any"] == 1

    def test_the_newest_row_wins(self, db):
        """Accepting again appends rather than replacing, so an account that
        re-accepted still has its stale row underneath."""
        _user(db, "reaccepted")
        _consent(db, "reaccepted", "terms", "0.9", at=NOW - timedelta(days=10))
        _consent(db, "reaccepted", "terms", "1.0", at=NOW)
        _consent(db, "reaccepted", "privacy", "1.0")
        db.session.commit()

        assert ConsentRepository(db).countOwingReacceptance(CURRENT)["any"] == 0

    def test_only_enabled_accounts_owe(self, db):
        """A banned or deleted account cannot reach the gate to answer, so
        counting it would grow the number every time someone leaves."""
        for uid, status in (("banned", S["banned"]), ("gone", S["deleted"])):
            _user(db, uid, status=status)
            _consent(db, uid, "terms", "0.9")
            _consent(db, uid, "privacy", "0.9")
        db.session.commit()

        assert ConsentRepository(db).countOwingReacceptance(CURRENT)["any"] == 0

    def test_no_documents_asked_is_nobody_owing(self, db):
        assert ConsentRepository(db).countOwingReacceptance({}) == {"any": 0}


class TestUserAggregates:
    def test_bans_split_by_whether_they_end(self, db):
        """`banned_until` NULL on a banned row means permanent — the column is
        overloaded, and this is where the overload has to be read carefully."""
        _user(db, "perm", status=S["banned"])
        _user(db, "timed", status=S["banned"], banned_until=NOW + timedelta(days=3))
        _user(db, "lapsed", status=S["banned"], banned_until=NOW - timedelta(days=1))
        db.session.commit()

        assert UserRepository(db).countBans() == {
            "total": 3,
            "permanent": 1,
            # Already past its date and still flagged: the ban lifts itself at
            # the next sign-in, so this is the backlog nobody has tried to use.
            "expired": 1,
        }

    def test_sanctions_count_separately_and_together(self, db):
        _user(db, "name", must_change_username=True)
        _user(db, "pic", picture_blocked=True)
        _user(db, "both-s", must_change_username=True, picture_blocked=True)
        db.session.commit()

        assert UserRepository(db).countSanctioned() == {
            "mustChangeUsername": 2,
            "pictureBlocked": 2,
            "both": 1,
        }

    def test_overdue_purge_is_the_signal_that_the_cron_stopped(self, db):
        grace = config.ACCOUNT_DELETION_GRACE_DAYS
        _user(db, "overdue", status=S["deleted"], deleted_at=NOW - timedelta(days=grace + 30))
        _user(db, "inside", status=S["deleted"], deleted_at=NOW - timedelta(days=1))
        # Deleted with no timestamp is never swept and never counted: the
        # instant is the only evidence of when the window opened.
        _user(db, "undated", status=S["deleted"])
        db.session.commit()

        assert UserRepository(db).countExpiredDeleted(grace) == 1

    def test_status_counts_omit_what_is_absent(self, db):
        _user(db, "a")
        _user(db, "b")
        _user(db, "c", status=S["banned"])
        db.session.commit()

        counts = UserRepository(db).countsByStatus()
        assert counts[S["enabled"]] == 2
        assert counts[S["banned"]] == 1
        # The caller supplies its own zero, which keeps this honest about what
        # it actually found.
        assert S["deleted"] not in counts

    def test_creation_windows_are_cumulative(self, db):
        _user(db, "new")
        db.session.commit()

        counts = UserRepository(db).countCreatedSince(1, 7, 30)
        assert counts[1] == 1
        # 30 days includes the last 7, on purpose: both are read as totals.
        assert counts[7] >= counts[1]
        assert counts[30] >= counts[7]


class TestModerationAggregates:
    def _report(self, db, reason, status, locked_at=None, resolved_at=None):
        report = ReportModel(
            reporter="rep",
            reported_uid="tgt",
            reported_username="tgt",
            reason=reason,
            status=status,
            locked_by="adm" if locked_at else None,
            locked_at=locked_at,
        )
        db.session.add(report)
        db.session.flush()
        if resolved_at is not None:
            report.updated_at = resolved_at
        return report

    def test_open_reports_are_grouped_by_reason(self, db):
        """`self_harm` is why this is not a single queue total: it is the one
        reason where a position in the queue is the wrong answer."""
        _user(db, "rep")
        self._report(db, "spam", S["pending"])
        self._report(db, "spam", S["pending"])
        self._report(db, "self_harm", S["pending"])
        self._report(db, "spam", S["accepted"])   # decided: not open
        db.session.commit()

        assert ReportRepository(db).countOpenByReason() == {"spam": 2, "self_harm": 1}

    def test_only_locks_past_the_window_are_stale(self, db):
        _user(db, "rep")
        self._report(db, "spam", S["pending"], locked_at=NOW - timedelta(minutes=90))
        self._report(db, "spam", S["pending"], locked_at=NOW - timedelta(minutes=2))
        self._report(db, "spam", S["pending"])                      # never claimed
        # A decided report holds no lock, whatever its timestamp says.
        self._report(db, "spam", S["accepted"], locked_at=NOW - timedelta(minutes=90))
        db.session.commit()

        assert ReportRepository(db).countStaleLocks(30) == 1

    def test_reports_counted_by_status(self, db):
        _user(db, "rep")
        self._report(db, "spam", S["pending"])
        self._report(db, "spam", S["accepted"])
        self._report(db, "spam", S["ignored"])
        db.session.commit()

        counts = ReportRepository(db).countsByStatus()
        assert counts[S["pending"]] == 1
        assert counts[S["accepted"]] == 1
        assert counts[S["ignored"]] == 1

    def test_notices_are_grouped_by_kind_not_totalled(self, db):
        """Four kinds are four different decisions; one total would read as one
        activity, which is the opposite of what the ladder is for."""
        _user(db, "tgt")
        for kind in ("warning", "warning", "suspension", "rename", "picture"):
            db.session.add(
                ModerationNoticeModel(user_id="tgt", kind=kind, reason="spam", issued_by="adm")
            )
        db.session.commit()

        counts = ModerationNoticeRepository(db).countsByKindSince(NOW - timedelta(days=30))
        assert counts == {"warning": 2, "suspension": 1, "rename": 1, "picture": 1}

    def test_notices_outside_the_window_are_not_counted(self, db):
        _user(db, "tgt")
        old = ModerationNoticeModel(user_id="tgt", kind="warning", reason="spam", issued_by="adm")
        db.session.add(old)
        db.session.flush()
        old.created_at = NOW - timedelta(days=90)
        db.session.commit()

        assert ModerationNoticeRepository(db).countsByKindSince(NOW - timedelta(days=30)) == {}

    def test_unacknowledged_notices(self, db):
        _user(db, "tgt")
        db.session.add(ModerationNoticeModel(user_id="tgt", kind="warning", reason="spam", issued_by="adm"))
        db.session.add(
            ModerationNoticeModel(
                user_id="tgt", kind="warning", reason="spam", issued_by="adm",
                acknowledged_at=NOW,
            )
        )
        db.session.commit()

        assert ModerationNoticeRepository(db).countUnacknowledged() == 1

    def test_expired_evidence_is_the_signal_that_purge_evidence_stopped(self, db):
        _user(db, "rep")
        retention = config.REPORT_EVIDENCE_RETENTION_DAYS

        stale = self._report(db, "spam", S["ignored"], resolved_at=NOW - timedelta(days=retention + 100))
        fresh = self._report(db, "spam", S["ignored"])
        # Open reports are never swept, however old — nobody has read them yet.
        open_old = self._report(db, "spam", S["pending"], resolved_at=NOW - timedelta(days=retention + 100))

        for report in (stale, fresh, open_old):
            db.session.add(
                ReportEvidenceModel(report=report.id, kind="profile", content="{}", content_hash="h")
            )
        db.session.commit()

        assert ReportEvidenceRepository(db).countExpired(retention) == 1


class TestErrorLog:
    def _fault(self, fingerprint, *, last_seen=None, message="boom"):
        return ErrorLog(
            kind="unhandled",
            path="/streaks/start",
            method="POST",
            fingerprint=fingerprint,
            exception_type="ValueError",
            status_code=500,
            last_seen=last_seen or NOW,
            message=message,
            traceback="Traceback...\nValueError: boom",
        )

    def test_the_same_fingerprint_bumps_one_row(self, db):
        repo = ErrorLogRepository(db)
        repo.record(self._fault("fp-1", message="first"))
        repo.record(self._fault("fp-1", message="second"))

        rows = repo.findRecent()
        assert len(rows) == 1
        assert rows[0].count == 2
        # The newest occurrence's detail: when a fault shifts slightly, the
        # recent one is the one being debugged.
        assert rows[0].message == "second"

    def test_the_traceback_is_encrypted_at_rest(self, db):
        """The column exists encrypted because a SQLAlchemy traceback carries
        the statement's parameters — a message body, an e-mail address."""
        ErrorLogRepository(db).record(
            self._fault("fp-secret", message="leaked: private-message-text")
        )
        db.session.commit()

        raw = db.session.execute(
            text("SELECT cl_14j, cl_14k FROM tb_14 WHERE cl_14e = 'fp-secret'")
        ).one()
        assert "private-message-text" not in (raw[0] or "")
        assert "private-message-text" not in (raw[1] or "")

        # And it reads back through the ORM.
        stored = ErrorLogRepository(db).findRecent()[0]
        assert "private-message-text" in stored.message

    def test_count_since_sums_occurrences_not_rows(self, db):
        repo = ErrorLogRepository(db)
        repo.record(self._fault("fp-a"))
        repo.record(self._fault("fp-a"))
        repo.record(self._fault("fp-b"))

        # Two rows, three hits.
        assert len(repo.findRecent()) == 2
        assert repo.countSince(NOW - timedelta(hours=1)) == 3

    def test_count_since_ignores_what_is_older(self, db):
        repo = ErrorLogRepository(db)
        repo.record(self._fault("fp-old", last_seen=NOW - timedelta(days=5)))

        assert repo.countSince(NOW - timedelta(hours=1)) == 0

    def test_purge_is_measured_from_the_last_sighting(self, db):
        """A bug first seen in January and still firing today is current."""
        repo = ErrorLogRepository(db)
        repo.record(self._fault("fp-stale", last_seen=NOW - timedelta(days=200)))
        repo.record(self._fault("fp-live", last_seen=NOW))

        assert repo.purgeOlderThan(90) == 1
        assert [r.fingerprint for r in repo.findRecent()] == ["fp-live"]


class TestHostAccess:
    def _login(self, at=None, ip="203.0.113.4", user="ubuntu"):
        return HostAccess(
            occurred_at=at or NOW,
            os_user=user,
            source_ip=ip,
            method="publickey",
            result="accepted",
        )

    def test_a_login_is_stored(self, db):
        repo = HostAccessRepository(db)
        assert repo.record(self._login()) is not None
        assert len(repo.findRecent()) == 1

    def test_resending_the_same_window_does_not_duplicate(self, db):
        """The host script sends a window of the SSH log; a lost cursor file
        makes that window overlap the last one."""
        repo = HostAccessRepository(db)
        login = self._login()

        assert repo.record(login) is not None
        assert repo.record(self._login(at=login.occurred_at)) is None
        assert len(repo.findRecent()) == 1

    def test_the_natural_key_is_instant_address_and_user(self, db):
        repo = HostAccessRepository(db)
        at = NOW
        repo.record(self._login(at=at))
        # Same second, different address — a different login.
        assert repo.record(self._login(at=at, ip="198.51.100.9")) is not None
        # Same second, same address, different account — also different.
        assert repo.record(self._login(at=at, user="root")) is not None

        assert len(repo.findRecent()) == 3

    def test_newest_first(self, db):
        repo = HostAccessRepository(db)
        repo.record(self._login(at=NOW - timedelta(hours=2), ip="198.51.100.1"))
        repo.record(self._login(at=NOW, ip="198.51.100.2"))

        assert [r.source_ip for r in repo.findRecent()] == ["198.51.100.2", "198.51.100.1"]
