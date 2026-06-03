import pytest
from unittest.mock import MagicMock, patch
from exceptions.baseExceptions import NoHarmException


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    s.query.return_value.all.return_value = []
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
    with patch("infrastructure.database.repositories.badgeRepository.BadgeModel"):
        from infrastructure.database.repositories.badgeRepository import BadgeRepository
        return BadgeRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("bid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_badge = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_badge
    assert repo.findById("bid").id is mock_badge.id


def test_findAll_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findAll()
    assert exc.value.statusCode == 500


def test_findAll_returns_list(repo):
    assert repo.findAll() == []


def test_create_success(repo, session):
    result = repo.create(MagicMock())
    assert session.add.called
    assert session.commit.called


def test_create_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("integrity error")
    with pytest.raises(NoHarmException) as exc:
        repo.create(MagicMock())
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


def test_softDelete_success_returns_true(repo, session):
    session.query.return_value.filter.return_value.first.return_value = MagicMock()
    assert repo.softDelete("bid") is True


def test_softDelete_sets_deleted_status(repo, session):
    from core.config import config
    mock_badge = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_badge
    repo.softDelete("bid")
    assert mock_badge.status == config.STATUS_CODES["deleted"]


# ── findAll paginated ─────────────────────────────────────────────────────────

def test_findAll_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.count.return_value = 10
    session.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findAll(PaginationParams(page=1, pageSize=5))
    assert hasattr(result, "total")
    assert result.total == 10


# ── update ────────────────────────────────────────────────────────────────────

def test_update_success_merges_fields(repo, session):
    existing = MagicMock()
    existing.name = "old-name"
    existing.description = "old-desc"
    existing.milestone = None
    existing.icon = b""
    existing.status = 1
    session.query.return_value.filter.return_value.first.return_value = existing

    updated = MagicMock()
    updated.name = "new-name"
    updated.description = None
    updated.milestone = None
    updated.icon = None
    updated.status = None

    result = repo.update("bid", updated)
    assert result.name == "new-name"
    session.commit.assert_called_once()


def test_update_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.update("nonexistent", MagicMock())
    assert exc.value.statusCode == 404


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    mock_badge = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_badge
    repo.updateStatus("bid", "disabled")
    assert mock_badge.status == 0
    session.commit.assert_called()


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_success_returns_true(repo, session):
    mock_badge = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_badge
    assert repo.delete("bid") is True
    session.delete.assert_called_once_with(mock_badge)


def test_delete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.delete("nonexistent")
    assert exc.value.statusCode == 404
