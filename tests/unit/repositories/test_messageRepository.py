import pytest
from unittest.mock import MagicMock, patch
from exceptions.baseExceptions import NoHarmException


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
    with patch("infrastructure.database.repositories.messageRepository.MessageModel"):
        from infrastructure.database.repositories.messageRepository import MessageRepository
        return MessageRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("mid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_msg = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_msg
    assert repo.findById("mid").id is mock_msg.id


def test_create_success(repo, session):
    result = repo.create(MagicMock())
    assert session.add.called
    assert session.commit.called


def test_create_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("constraint error")
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
    assert repo.softDelete("mid") is True


# ── findByChatId ──────────────────────────────────────────────────────────────

def test_findByChatId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findByChatId("cid"), list)


def test_findByChatId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 5
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findByChatId("cid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")
    assert result.total == 5


def test_findByChatId_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findByChatId("cid")
    assert exc.value.statusCode == 500


# ── findUnreadByChatId ────────────────────────────────────────────────────────

def test_findUnreadByChatId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findUnreadByChatId("cid"), list)


def test_findUnreadByChatId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 2
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findUnreadByChatId("cid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")


# ── markAsRead ────────────────────────────────────────────────────────────────

def test_markAsRead_success_sets_status(repo, session):
    from core.config import config
    mock_msg = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_msg
    result = repo.markAsRead("mid")
    assert mock_msg.status == config.STATUS_CODES["read"]
    session.commit.assert_called()


def test_markAsRead_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.markAsRead("nonexistent")
    assert exc.value.statusCode == 404


# ── markAllAsRead ─────────────────────────────────────────────────────────────

def test_markAllAsRead_returns_true(repo, session):
    from core.config import config
    msgs = [MagicMock(), MagicMock()]
    session.query.return_value.filter.return_value.all.return_value = msgs
    result = repo.markAllAsRead("cid")
    assert result is True
    for m in msgs:
        assert m.status == config.STATUS_CODES["read"]
    session.commit.assert_called()


def test_markAllAsRead_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.markAllAsRead("cid")
    assert exc.value.statusCode == 500


# ── update (bug: non-NoHarm exception swallowed) ──────────────────────────────

def test_update_success_merges_fields(repo, session):
    mock_msg = MagicMock()
    mock_msg.sender = "old"
    mock_msg.status = 7
    session.query.return_value.filter.return_value.first.return_value = mock_msg

    updated = MagicMock()
    updated.sender = "new"
    updated.status = None

    result = repo.update("mid", updated)
    assert result.sender == "new"
    session.commit.assert_called_once()


def test_update_not_found_raises_404(repo):
    updated = MagicMock()
    with pytest.raises(NoHarmException) as exc:
        repo.update("nonexistent", updated)
    assert exc.value.statusCode == 404


def test_update_db_error_raises_500(repo, session):
    mock_msg = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_msg
    session.commit.side_effect = Exception("lock timeout")

    updated = MagicMock()
    updated.sender = None
    updated.status = None

    with pytest.raises(NoHarmException) as exc:
        repo.update("mid", updated)
    assert exc.value.statusCode == 500


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_success_returns_true(repo, session):
    mock_msg = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_msg
    result = repo.delete("mid")
    assert result is True
    session.delete.assert_called_once_with(mock_msg)


def test_delete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.delete("nonexistent")
    assert exc.value.statusCode == 404


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    mock_msg = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_msg
    repo.updateStatus("mid", 8)
    assert mock_msg.status == 8
    session.commit.assert_called()
