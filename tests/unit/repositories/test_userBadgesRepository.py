import pytest
from unittest.mock import MagicMock, patch
from exceptions.baseExceptions import NoHarmException
from datetime import datetime, timezone


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    s.query.return_value.filter.return_value.all.return_value = []
    s.query.return_value.count.return_value = 0
    return s


@pytest.fixture
def db(session):
    d = MagicMock()
    d.session = session
    d.engine = MagicMock()
    return d


@pytest.fixture
def repo(db):
    with patch("infrastructure.database.repositories.userBadgesRepository.UserBadgesModel"):
        from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
        return UserBadgesRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("ubid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_ub = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_ub
    assert repo.findById("ubid").id is mock_ub.id


def test_grant_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("integrity error")
    with pytest.raises(NoHarmException) as exc:
        repo.grant("uid", "bid",datetime.now(timezone.utc))
    assert exc.value.statusCode == 500
    session.rollback.assert_called_once()


def test_updateStatus_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.updateStatus("nonexistent", 1)
    assert exc.value.statusCode == 404


def test_softDelete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.softDelete("nonexistent")
    assert exc.value.statusCode == 404


def test_softDelete_success(repo, session):
    from core.config import config
    session.query.return_value.filter.return_value.first.return_value = MagicMock()
    result = repo.softDelete("ubid")
    assert result is not None
    assert result.status == config.STATUS_CODES["deleted"]


def test_softDelete_sets_deleted_status(repo, session):
    from core.config import config
    mock_ub = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_ub
    repo.softDelete("ubid")
    assert mock_ub.status == config.STATUS_CODES["deleted"]


# ── findByUserId ──────────────────────────────────────────────────────────────

def test_findByUserId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findByUserId("uid"), list)


def test_findByUserId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 3
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findByUserId("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")
    assert result.total == 3


def test_findByUserId_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findByUserId("uid")
    assert exc.value.statusCode == 500


# ── findByBadgeId ─────────────────────────────────────────────────────────────

def test_findByBadgeId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findByBadgeId("bid"), list)


def test_findByBadgeId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 2
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findByBadgeId("bid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")


# ── existsByUserAndBadge ──────────────────────────────────────────────────────

def test_existsByUserAndBadge_returns_true_when_found(repo, session):
    session.query.return_value.filter.return_value.first.return_value = MagicMock()
    assert repo.existsByUserAndBadge("uid", "bid") is True


def test_existsByUserAndBadge_returns_false_when_not_found(repo, session):
    session.query.return_value.filter.return_value.first.return_value = None
    assert repo.existsByUserAndBadge("uid", "bid") is False


def test_existsByUserAndBadge_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.existsByUserAndBadge("uid", "bid")
    assert exc.value.statusCode == 500


# ── grant success paths ───────────────────────────────────────────────────────

def test_grant_existing_badge_updates_given_at(repo, session):
    mock_ub = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_ub
    new_date =datetime.now(timezone.utc)
    result = repo.grant("uid", "bid", new_date)
    assert result is not None
    assert mock_ub.given_at == new_date
    session.commit.assert_called()


def test_grant_new_badge_adds_to_session(repo, session):
    with patch("infrastructure.database.repositories.userBadgesRepository.UserBadgesModel") as MockModel:
        session.query.return_value.filter.return_value.first.return_value = None
        MockModel.return_value = MagicMock()
        result = repo.grant("uid", "bid",datetime.now(timezone.utc))
    assert result is not None
    session.add.assert_called()
    session.commit.assert_called()


# ── revoke ────────────────────────────────────────────────────────────────────

def test_revoke_found_sets_deleted_status(repo, session):
    from core.config import config
    mock_ub = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_ub
    result = repo.revoke("uid", "bid")
    assert result is not None
    assert mock_ub.status == config.STATUS_CODES["deleted"]


def test_revoke_not_found_raises_404(repo, session):
    session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(NoHarmException) as exc:
        repo.revoke("uid", "bid")
    assert exc.value.statusCode == 404


def test_revoke_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.revoke("uid", "bid")
    assert exc.value.statusCode == 500


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    mock_ub = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_ub
    repo.updateStatus("ubid", "deleted")
    assert mock_ub.status == 2
    session.commit.assert_called()


# ── update ────────────────────────────────────────────────────────────────────

def test_update_success_merges_status(repo, session):
    mock_ub = MagicMock()
    mock_ub.status = 1
    session.query.return_value.filter.return_value.first.return_value = mock_ub

    updated = MagicMock()
    updated.status = 2

    result = repo.update("ubid", updated)
    assert result.status == 2
    session.commit.assert_called_once()


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_success_returns_true(repo, session):
    mock_ub = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_ub
    assert repo.delete("ubid") is True
    session.delete.assert_called_once_with(mock_ub)


def test_delete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.delete("nonexistent")
    assert exc.value.statusCode == 404
