import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from domain.entities.consent import Consent
from exceptions.baseExceptions import NoHarmException


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    s.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return s


@pytest.fixture
def db(session):
    d = MagicMock()
    d.session = session
    d.engine = MagicMock()
    return d


@pytest.fixture
def repo(db):
    with patch("infrastructure.database.repositories.consentRepository.ConsentModel"):
        from infrastructure.database.repositories.consentRepository import ConsentRepository
        return ConsentRepository(db)


def _model(document="terms", version="1.0", acceptedAt=None, withdrawnAt=None, modelId="c-1"):
    m = MagicMock()
    m.id = modelId
    m.user_id = "uid-001"
    m.document = document
    m.version = version
    m.accepted_at = acceptedAt or datetime(2026, 1, 1)
    m.withdrawn_at = withdrawnAt
    m.created_at = m.accepted_at
    m.updated_at = m.accepted_at
    return m


def _ordered(session):
    return session.query.return_value.filter.return_value.order_by.return_value


# ── create ────────────────────────────────────────────────────────────────────

def test_create_commits(repo, session):
    repo.create(Consent(user_id="uid-001", document="terms", version="1.0"))
    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_create_db_error_rolls_back_and_raises_500(repo, session):
    session.commit.side_effect = Exception("db error")

    with pytest.raises(NoHarmException) as exc:
        repo.create(Consent(user_id="uid-001", document="terms", version="1.0"))

    assert exc.value.statusCode == 500
    session.rollback.assert_called_once()


def test_createMany_is_one_commit(repo, session):
    """The set is the point.

    An account that recorded its agreement to the terms but not to the privacy
    policy — because the second insert failed — is one the consent gate stops
    at its next launch, with no way for the user to tell what went wrong.
    """
    repo.createMany([
        Consent(user_id="uid-001", document="terms", version="1.0"),
        Consent(user_id="uid-001", document="privacy", version="1.0"),
    ])

    session.add_all.assert_called_once()
    session.commit.assert_called_once()


def test_createMany_of_nothing_writes_nothing(repo, session):
    assert repo.createMany([]) == []
    session.add_all.assert_not_called()
    session.commit.assert_not_called()


# ── findCurrent ───────────────────────────────────────────────────────────────

def test_findCurrent_keeps_the_newest_row_per_document(repo, session):
    """Append-only: version 2 sits beside version 1, and the newest one wins."""
    _ordered(session).all.return_value = [
        _model("terms", "1.0", datetime(2026, 1, 1), modelId="c-1"),
        _model("terms", "2.0", datetime(2026, 6, 1), modelId="c-2"),
        _model("privacy", "1.0", datetime(2026, 1, 1), modelId="c-3"),
    ]

    current = repo.findCurrent("uid-001")

    assert set(current) == {"terms", "privacy"}
    assert current["terms"].version == "2.0"


def test_findCurrent_can_return_a_withdrawn_row(repo, session):
    """"Withdrawn yesterday" and "never given" are different states, and the
    caller has to be able to tell them apart."""
    _ordered(session).all.return_value = [
        _model("health_data", "1.0", datetime(2026, 1, 1),
               withdrawnAt=datetime(2026, 7, 1))
    ]

    current = repo.findCurrent("uid-001")

    assert current["health_data"].active is False
    assert current["health_data"].withdrawn_at == datetime(2026, 7, 1)


def test_findCurrent_of_an_account_with_nothing_is_empty(repo, session):
    assert repo.findCurrent("uid-001") == {}


def test_findByUser_returns_withdrawn_rows_too(repo, session):
    """The export carries the history, not the current state."""
    _ordered(session).all.return_value = [
        _model("health_data", "1.0", datetime(2026, 1, 1), withdrawnAt=datetime(2026, 7, 1)),
        _model("terms", "1.0", datetime(2026, 1, 1)),
    ]

    assert len(repo.findByUser("uid-001")) == 2


# ── withdraw ──────────────────────────────────────────────────────────────────

def test_withdraw_stamps_the_row(repo, session):
    model = _model("health_data", "1.0")
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = model

    result = repo.withdraw("uid-001", "health_data")

    assert model.withdrawn_at is not None
    assert result.withdrawn_at is not None
    session.commit.assert_called_once()


def test_withdraw_with_nothing_in_force_returns_none(repo, session):
    """Idempotent: a second call must not move the date."""
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    assert repo.withdraw("uid-001", "health_data") is None
    session.commit.assert_not_called()


def test_withdraw_db_error_rolls_back_and_raises_500(repo, session):
    model = _model("health_data", "1.0")
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = model
    session.commit.side_effect = Exception("db error")

    with pytest.raises(NoHarmException) as exc:
        repo.withdraw("uid-001", "health_data")

    assert exc.value.statusCode == 500
    session.rollback.assert_called_once()
