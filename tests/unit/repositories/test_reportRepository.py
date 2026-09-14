"""Unit tests for ReportRepository.

Two different things are checked here, with two different setups:

- the **mapping** methods (`standingsByReporters`, `countOpenAgainstMany`) turn
  grouped rows into dicts, and that logic is worth testing against a mocked
  session because the interesting part is what happens to ids the query
  returned nothing for.
- the **priority ordering** is SQL, and a mocked session would accept any
  expression at all. It is built against a real (unbound) `Session` and
  compiled to Postgres instead, so a wrong column or an invalid join fails
  here rather than in production.
"""

import pytest
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from core.config import config
from exceptions.baseExceptions import NoHarmException

import infrastructure.database.models  # noqa: F401  — populates the mapper registry
from infrastructure.database.repositories.reportRepository import ReportRepository


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    s.query.return_value.filter.return_value.all.return_value = []
    s.query.return_value.count.return_value = 0
    return s


@pytest.fixture
def repo(session):
    db = MagicMock()
    db.session = session
    db.engine = MagicMock()
    return ReportRepository(db)


@pytest.fixture
def realRepo():
    """A repository over a real, unbound Session — for compiling, never running."""
    db = MagicMock()
    db.session = Session()
    db.engine = MagicMock()
    return ReportRepository(db)


def _grouped(session, rows):
    """Point the session at `rows` as the result of a grouped query."""
    session.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows


# ── standingsByReporters ─────────────────────────────────────────────────────

def test_standings_of_nobody_asks_nothing(repo, session):
    assert repo.standingsByReporters([]) == {}
    session.query.assert_not_called()


def test_standings_ignores_null_reporters(repo, session):
    """A purged reporter's column is NULL; it is not an id to group on."""
    assert repo.standingsByReporters([None]) == {}
    session.query.assert_not_called()


def test_standings_tallies_each_status(repo, session):
    _grouped(session, [
        ("uid-a", config.STATUS_CODES["pending"], 2),
        ("uid-a", config.STATUS_CODES["accepted"], 3),
        ("uid-a", config.STATUS_CODES["ignored"], 1),
    ])

    standings = repo.standingsByReporters(["uid-a"])
    assert standings["uid-a"] == {"pending": 2, "accepted": 3, "ignored": 1}


def test_standings_returns_zeroes_for_a_reporter_with_no_rows(repo, session):
    """Every id asked for comes back, so callers never guess what a gap means."""
    _grouped(session, [("uid-a", config.STATUS_CODES["accepted"], 1)])

    standings = repo.standingsByReporters(["uid-a", "uid-b"])
    assert standings["uid-b"] == {"pending": 0, "accepted": 0, "ignored": 0}


def test_standings_skips_statuses_that_are_not_report_outcomes(repo, session):
    """`tb_10.status` is only ever the report trio; anything else is not counted."""
    _grouped(session, [
        ("uid-a", config.STATUS_CODES["accepted"], 1),
        ("uid-a", config.STATUS_CODES["banned"], 7),
    ])

    assert repo.standingsByReporters(["uid-a"]) == {
        "uid-a": {"pending": 0, "accepted": 1, "ignored": 0}
    }


def test_standings_wraps_a_database_error(repo, session):
    session.query.side_effect = RuntimeError("connection reset")

    with pytest.raises(NoHarmException) as exc:
        repo.standingsByReporters(["uid-a"])
    assert exc.value.statusCode == 500


# ── countOpenAgainstMany ─────────────────────────────────────────────────────

def test_open_counts_of_nobody_asks_nothing(repo, session):
    assert repo.countOpenAgainstMany([]) == {}
    session.query.assert_not_called()


def test_open_counts_fill_in_zero_for_an_unreported_user(repo, session):
    _grouped(session, [("uid-x", 3)])

    counts = repo.countOpenAgainstMany(["uid-x", "uid-y"])
    assert counts == {"uid-x": 3, "uid-y": 0}


def test_open_counts_wrap_a_database_error(repo, session):
    session.query.side_effect = RuntimeError("connection reset")

    with pytest.raises(NoHarmException) as exc:
        repo.countOpenAgainstMany(["uid-x"])
    assert exc.value.statusCode == 500


# ── findRecentByPair ─────────────────────────────────────────────────────────

def test_recent_by_pair_returns_none_when_nothing_was_ever_filed(repo, session):
    ordered = session.query.return_value.filter.return_value.order_by.return_value
    ordered.first.return_value = None

    assert repo.findRecentByPair("uid-a", "uid-b") is None


def test_recent_by_pair_wraps_a_database_error(repo, session):
    session.query.side_effect = RuntimeError("connection reset")

    with pytest.raises(NoHarmException) as exc:
        repo.findRecentByPair("uid-a", "uid-b")
    assert exc.value.statusCode == 500


def test_recent_by_pair_filters_on_the_pair_alone(repo, session):
    """No status in the filter.

    The service needs the *last* report about this pair whatever became of it:
    an open one is a duplicate, a recently dismissed one starts a cooldown, an
    actioned one starts nothing. Narrowing to open reports here is the bug this
    method replaced, and it comes back the moment someone "optimises" the query.
    """
    ordered = session.query.return_value.filter.return_value.order_by.return_value
    ordered.first.return_value = None

    repo.findRecentByPair("uid-a", "uid-b")

    session.query.return_value.filter.assert_called_once()
    assert len(session.query.return_value.filter.call_args[0]) == 2


def test_recent_by_pair_takes_the_newest(repo, session):
    """A dismissal from last year must not outrank one from this morning."""
    ordered = session.query.return_value.filter.return_value.order_by.return_value
    ordered.first.return_value = None

    repo.findRecentByPair("uid-a", "uid-b")

    session.query.return_value.filter.return_value.order_by.assert_called_once()
    ordered.first.assert_called_once()


# ── the priority ordering, compiled for real ─────────────────────────────────

def _prioritySql(realRepo, status=None, sort="newest") -> str:
    """Run `findAll` far enough to capture the SQL it would execute.

    `_paginate` with no params calls `.all()`, which an unbound Session refuses,
    so the query is intercepted there and compiled instead.
    """
    captured = {}

    def capture(query, params):
        captured["statement"] = query.statement
        return []

    original = realRepo._paginate
    realRepo._paginate = capture
    try:
        realRepo.findAll(status=status, sort=sort)
    finally:
        realRepo._paginate = original

    return str(captured["statement"].compile(dialect=postgresql.dialect()))


def test_priority_ordering_compiles_against_postgres(realRepo):
    sql = _prioritySql(realRepo, sort="priority")
    assert "LEFT OUTER JOIN" in sql
    assert "GROUP BY tb_10.cl_10b" in sql


def test_priority_puts_self_harm_first(realRepo):
    sql = _prioritySql(realRepo, sort="priority")
    orderBy = sql.split("ORDER BY", 1)[1]
    # The reason test is the first ordering term, before the weight.
    assert orderBy.index("cl_10d") < orderBy.index("coalesce")


def test_priority_divides_as_floats(realRepo):
    """Integer division would collapse every weight to 0 and sort nothing."""
    sql = _prioritySql(realRepo, sort="priority")
    assert "AS FLOAT" in sql


def test_priority_falls_back_to_newest_within_equal_weights(realRepo):
    sql = _prioritySql(realRepo, sort="priority")
    assert sql.rstrip().endswith("tb_10.created_at DESC")


def test_the_default_sort_is_chronological_and_joins_nothing(realRepo):
    sql = _prioritySql(realRepo, sort="newest")
    assert "JOIN" not in sql
    assert sql.rstrip().endswith("ORDER BY tb_10.created_at DESC")


def test_an_unknown_sort_behaves_like_newest(realRepo):
    """The route validates the value; the repository must not invent a third order."""
    assert _prioritySql(realRepo, sort="nonsense") == _prioritySql(realRepo, sort="newest")


def test_a_status_filter_survives_the_priority_join(realRepo):
    sql = _prioritySql(realRepo, status=config.STATUS_CODES["pending"], sort="priority")
    assert "WHERE tb_10.cl_10f" in sql
