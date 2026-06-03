"""Unit tests for UserRepository.

Verifies that every error path raises NoHarmException with a valid statusCode
attribute — not a TypeError caused by wrong keyword argument names.
"""

import pytest
from unittest.mock import MagicMock, patch

from exceptions.baseExceptions import NoHarmException


# ── fixtures ─────────────────────────────────────────────────────────────────

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
    with patch("infrastructure.database.repositories.userRepository.UserModel"):
        from infrastructure.database.repositories.userRepository import UserRepository
        yield UserRepository(db)


# ── findById ─────────────────────────────────────────────────────────────────

def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("connection refused")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("uid")
    assert exc.value.statusCode == 500


def test_findById_success_returns_user(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    result = repo.findById("uid-001")
    assert result.id is mock_user.id


# ── findByEmail ───────────────────────────────────────────────────────────────

def test_findByEmail_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findByEmail("notfound@test.com")
    assert exc.value.statusCode == 404


def test_findByEmail_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.findByEmail("user@test.com")
    assert exc.value.statusCode == 500


# ── findByUsername ────────────────────────────────────────────────────────────

def test_findByUsername_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findByUsername("ghost")
    assert exc.value.statusCode == 404


def test_findByUsername_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.findByUsername("someuser")
    assert exc.value.statusCode == 500


# ── findAll ───────────────────────────────────────────────────────────────────

def test_findAll_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db down")
    with pytest.raises(NoHarmException) as exc:
        repo.findAll()
    assert exc.value.statusCode == 500


def test_findAll_returns_list(repo):
    result = repo.findAll()
    assert isinstance(result, list)


# ── create ────────────────────────────────────────────────────────────────────

def test_create_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("integrity error")
    mock_user = MagicMock()
    with pytest.raises(NoHarmException) as exc:
        repo.create(mock_user)
    assert exc.value.statusCode == 500
    session.rollback.assert_called_once()


def test_create_success_returns_user(repo, session):
    result = repo.create(MagicMock())
    assert session.add.called
    assert session.commit.called


# ── updateStatus ──────────────────────────────────────────────────────────────

def test_updateStatus_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.updateStatus("nonexistent", 1)
    assert exc.value.statusCode == 404


def test_updateStatus_db_error_raises_500(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    session.commit.side_effect = Exception("lock timeout")
    with pytest.raises(NoHarmException) as exc:
        repo.updateStatus("uid", 1)
    assert exc.value.statusCode == 500


# ── softDelete ────────────────────────────────────────────────────────────────

def test_softDelete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.softDelete("nonexistent")
    assert exc.value.statusCode == 404


def test_softDelete_success(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    result = repo.softDelete("uid")
    assert result is True


# ── findByEmail success ───────────────────────────────────────────────────────

def test_findByEmail_success_returns_user(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    result = repo.findByEmail("found@test.com")
    assert result.id is mock_user.id


# ── findByUsername success ────────────────────────────────────────────────────

def test_findByUsername_success_returns_user(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    result = repo.findByUsername("founduser")
    assert result.id is mock_user.id


# ── findAll paginated ─────────────────────────────────────────────────────────

def test_findAll_with_pagination_returns_paginated(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.count.return_value = 5
    session.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    params = PaginationParams(page=1, pageSize=10)
    result = repo.findAll(params)
    assert hasattr(result, "total")
    assert result.total == 5


def test_findAll_without_pagination_returns_list(repo, session):
    mock_users = [MagicMock(), MagicMock()]
    session.query.return_value.all.return_value = mock_users
    result = repo.findAll()
    assert len(result) == len(mock_users)
    assert result[0].id is mock_users[0].id


# ── update ────────────────────────────────────────────────────────────────────

def test_update_success_merges_fields(repo, session):
    existing = MagicMock()
    existing.username = "old"
    existing.email = "old@test.com"
    existing.status = 1
    existing.profile_picture = b""
    session.query.return_value.filter.return_value.first.return_value = existing

    updated = MagicMock()
    updated.username = "new"
    updated.email = None
    updated.status = None
    updated.profile_picture = None

    result = repo.update("uid", updated)
    assert result.username == "new"
    session.commit.assert_called_once()


def test_update_not_found_raises_404(repo):
    updated = MagicMock()
    with pytest.raises(NoHarmException) as exc:
        repo.update("nonexistent", updated)
    assert exc.value.statusCode == 404


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_success_returns_true(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    result = repo.delete("uid")
    assert result is True
    session.delete.assert_called_once_with(mock_user)
    session.commit.assert_called()


def test_delete_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.delete("nonexistent")
    assert exc.value.statusCode == 404


# ── updateStatus success ──────────────────────────────────────────────────────

def test_updateStatus_success_sets_status(repo, session):
    mock_user = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_user
    result = repo.updateStatus("uid", 2)
    assert mock_user.status == 2
    session.commit.assert_called()
