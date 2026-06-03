import pytest
from unittest.mock import MagicMock, patch
from exceptions.baseExceptions import NoHarmException


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    s.query.return_value.filter.return_value.all.return_value = []
    return s


@pytest.fixture
def db(session):
    d = MagicMock()
    d.session = session
    d.engine = MagicMock()
    return d


@pytest.fixture
def repo(db):
    with patch("infrastructure.database.repositories.friendshipRepository.FriendshipModel"):
        from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
        return FriendshipRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("fid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_fs = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_fs
    assert repo.findById("fid").id is mock_fs.id


def test_findByUsers_not_found_raises_404(repo, session):
    session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(NoHarmException) as exc:
        repo.findByUsers("uid-a", "uid-b")
    assert exc.value.statusCode == 404


def test_findByUsers_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.findByUsers("uid-a", "uid-b")
    assert exc.value.statusCode == 500


def test_create_success(repo, session):
    result = repo.create(MagicMock())
    assert session.add.called
    assert session.commit.called


def test_create_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("constraint violation")
    with pytest.raises(NoHarmException) as exc:
        repo.create(MagicMock())
    assert exc.value.statusCode == 500
    session.rollback.assert_called_once()


def test_updateStatus_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.updateStatus("nonexistent", "accepted")
    assert exc.value.statusCode == 404


def test_updateStatus_db_error_raises_500(repo, session):
    mock_fs = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_fs
    session.commit.side_effect = Exception("lock error")
    with pytest.raises(NoHarmException) as exc:
        repo.updateStatus("fid", "accepted")
    assert exc.value.statusCode == 500


def test_softDelete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.softDelete("nonexistent")
    assert exc.value.statusCode == 404


def test_softDelete_success(repo, session):
    session.query.return_value.filter.return_value.first.return_value = MagicMock()
    assert repo.softDelete("fid") is True


def test_softDelete_sets_deleted_status(repo, session):
    from core.config import config
    mock_fs = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_fs
    repo.softDelete("fid")
    assert mock_fs.status == config.STATUS_CODES["deleted"]


# ── findByUsers success ───────────────────────────────────────────────────────

def test_findByUsers_success_returns_friendship(repo, session):
    mock_fs = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_fs
    result = repo.findByUsers("uid-a", "uid-b")
    assert result.id is mock_fs.id


# ── existsByUsers ─────────────────────────────────────────────────────────────

def test_existsByUsers_returns_true_when_found(repo, session):
    session.query.return_value.filter.return_value.first.return_value = MagicMock()
    assert repo.existsByUsers("uid-a", "uid-b") is True


def test_existsByUsers_returns_false_when_not_found(repo, session):
    session.query.return_value.filter.return_value.first.return_value = None
    assert repo.existsByUsers("uid-a", "uid-b") is False


def test_existsByUsers_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.existsByUsers("uid-a", "uid-b")
    assert exc.value.statusCode == 500


# ── findAllByUserId ───────────────────────────────────────────────────────────

def test_findAllByUserId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    result = repo.findAllByUserId("uid")
    assert isinstance(result, list)


def test_findAllByUserId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 3
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findAllByUserId("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")
    assert result.total == 3


def test_findAllByUserId_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.findAllByUserId("uid")
    assert exc.value.statusCode == 500


# ── findPendingReceived ───────────────────────────────────────────────────────

def test_findPendingReceived_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    result = repo.findPendingReceived("uid")
    assert isinstance(result, list)


def test_findPendingReceived_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 2
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findPendingReceived("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")


# ── findPendingSent ───────────────────────────────────────────────────────────

def test_findPendingSent_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findPendingSent("uid"), list)


# ── update ────────────────────────────────────────────────────────────────────

def test_update_success_merges_fields(repo, session):
    existing = MagicMock()
    existing.sender = "old-sender"
    existing.reciver = "old-reciver"
    existing.status = 4
    session.query.return_value.filter.return_value.first.return_value = existing

    updated = MagicMock()
    updated.sender = "new-sender"
    updated.reciver = None
    updated.status = None

    result = repo.update("fid", updated)
    assert result.sender == "new-sender"
    session.commit.assert_called_once()


def test_update_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.update("nonexistent", MagicMock())
    assert exc.value.statusCode == 404


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    from core.config import config
    mock_fs = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_fs
    result = repo.updateStatus("fid", "accepted")
    assert mock_fs.status == config.STATUS_CODES["accepted"]
    session.commit.assert_called()
