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
    with patch("infrastructure.database.repositories.chatRepository.ChatModel"):
        from infrastructure.database.repositories.chatRepository import ChatRepository
        return ChatRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("cid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_chat = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_chat
    assert repo.findById("cid").id is mock_chat.id


def test_create_success(repo, session):
    result = repo.create(MagicMock())
    assert session.add.called
    assert session.commit.called


def test_create_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("db error")
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
    assert repo.softDelete("cid") is True


def test_softDelete_sets_deleted_status(repo, session):
    from core.config import config
    mock_chat = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_chat
    repo.softDelete("cid")
    assert mock_chat.status == config.STATUS_CODES["deleted"]


# ── findByParticipant ─────────────────────────────────────────────────────────

def test_findByParticipant_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findByParticipant("uid"), list)


def test_findByParticipant_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findByParticipant("uid")
    assert exc.value.statusCode == 500


# ── findAllBySenderId ─────────────────────────────────────────────────────────

def test_findAllBySenderId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findAllBySenderId("uid"), list)


def test_findAllBySenderId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 3
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findAllBySenderId("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")
    assert result.total == 3


def test_findAllBySenderId_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.findAllBySenderId("uid")
    assert exc.value.statusCode == 500


# ── findAllByReciverId ────────────────────────────────────────────────────────

def test_findAllByReciverId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findAllByReciverId("uid"), list)


def test_findAllByReciverId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 2
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findAllByReciverId("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")


# ── update ────────────────────────────────────────────────────────────────────

def test_update_success_merges_fields(repo, session):
    existing = MagicMock()
    existing.sender = "old-sender"
    existing.reciver = "old-reciver"
    existing.status = 4
    existing.ended_at = None
    session.query.return_value.filter.return_value.first.return_value = existing

    updated = MagicMock()
    updated.sender = "new-sender"
    updated.reciver = None
    updated.status = None
    updated.ended_at = None

    result = repo.update("cid", updated)
    assert result.sender == "new-sender"
    session.commit.assert_called_once()


def test_update_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.update("nonexistent", MagicMock())
    assert exc.value.statusCode == 404


# ── updateEndedAt ─────────────────────────────────────────────────────────────

def test_updateEndedAt_success(repo, session):
    mock_chat = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_chat
    end =datetime.now(timezone.utc)
    repo.updateEndedAt("cid", end)
    assert mock_chat.ended_at == end
    session.commit.assert_called()


def test_updateEndedAt_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.updateEndedAt("nonexistent",datetime.now(timezone.utc))
    assert exc.value.statusCode == 404


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    mock_chat = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_chat
    repo.updateStatus("cid", 1)
    assert mock_chat.status == 1
    session.commit.assert_called()


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_success_returns_true(repo, session):
    mock_chat = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_chat
    result = repo.delete("cid")
    assert result is True
    session.delete.assert_called_once_with(mock_chat)


def test_delete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.delete("nonexistent")
    assert exc.value.statusCode == 404
