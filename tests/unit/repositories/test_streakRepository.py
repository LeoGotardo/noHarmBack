import pytest
from unittest.mock import MagicMock, patch
from exceptions.baseExceptions import NoHarmException
from datetime import datetime, timezone


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    s.query.return_value.filter.return_value.all.return_value = []
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
    with patch("infrastructure.database.repositories.streakRepository.StreakModel"):
        from infrastructure.database.repositories.streakRepository import StreakRepository
        return StreakRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("sid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    assert repo.findById("sid").id is mock_streak.id


def test_findCurrentStreak_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findCurrentStreak("uid")
    assert exc.value.statusCode == 404


def test_findCurrentStreak_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.findCurrentStreak("uid")
    assert exc.value.statusCode == 500


def test_findCurrentRecord_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findCurrentRecord("uid")
    assert exc.value.statusCode == 404


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


def test_softDelete_success(repo, session):
    session.query.return_value.filter.return_value.first.return_value = MagicMock()
    assert repo.softDelete("sid") is True


# ── findCurrentStreak success ─────────────────────────────────────────────────

def test_findCurrentStreak_success(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    # Repositories hand back domain entities, not ORM models.
    result = repo.findCurrentStreak("uid")
    assert result is not None
    assert result.owner_id is mock_streak.owner_id
    assert result.start_at is mock_streak.start_at


# ── findCurrentRecord success ─────────────────────────────────────────────────

def test_findCurrentRecord_success(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    assert repo.findCurrentRecord("uid").id is mock_streak.id


def test_findCurrentRecord_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findCurrentRecord("uid")
    assert exc.value.statusCode == 500


# ── findAllByOwnerId ──────────────────────────────────────────────────────────

def test_findAllByOwnerId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findAllByOwnerId("uid"), list)


def test_findAllByOwnerId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 4
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findAllByOwnerId("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")
    assert result.total == 4


def test_findAllByOwnerId_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findAllByOwnerId("uid")
    assert exc.value.statusCode == 500


# ── update ────────────────────────────────────────────────────────────────────

def test_update_success_merges_fields(repo, session):
    existing = MagicMock()
    existing.start = None
    existing.end = None
    existing.status = 1
    session.query.return_value.filter.return_value.first.return_value = existing

    updated = MagicMock()
    now =datetime.now(timezone.utc)
    updated.start_at = now
    updated.end_at = None
    updated.status = None

    result = repo.update("sid", updated)
    assert result.start_at == now
    session.commit.assert_called_once()


def test_update_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.update("nonexistent", MagicMock())
    assert exc.value.statusCode == 404


# ── markAsRecord ──────────────────────────────────────────────────────────────

def test_markAsRecord_success_sets_flag(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    result = repo.markAsRecord("sid")
    assert mock_streak.is_record is True
    session.commit.assert_called()


def test_markAsRecord_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.markAsRecord("nonexistent")
    assert exc.value.statusCode == 404


# ── updateEnd ─────────────────────────────────────────────────────────────────

def test_updateEnd_success_sets_end(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    end =datetime.now(timezone.utc)
    result = repo.updateEnd("sid", end)
    assert mock_streak.end_at == end
    session.commit.assert_called()


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    repo.updateStatus("sid", 2)
    assert mock_streak.status == 2
    session.commit.assert_called()


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_success_returns_true(repo, session):
    mock_streak = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_streak
    result = repo.delete("sid")
    assert result is True
    session.delete.assert_called_once_with(mock_streak)


def test_delete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.delete("nonexistent")
    assert exc.value.statusCode == 404
