import pytest
from unittest.mock import MagicMock, patch
from exceptions.baseExceptions import NoHarmException
from datetime import datetime, timezone, timedelta


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    s.query.return_value.all.return_value = []
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
    with patch("infrastructure.database.repositories.auditLogsRepository.AuditLogsModel"):
        from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
        return AuditLogsRepository(db)


def test_findById_not_found_raises_404(repo):
    with pytest.raises(NoHarmException) as exc:
        repo.findById("nonexistent")
    assert exc.value.statusCode == 404


def test_findById_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findById("aid")
    assert exc.value.statusCode == 500


def test_findById_success(repo, session):
    mock_log = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = mock_log
    assert repo.findById("aid").id is mock_log.id


def test_findAll_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findAll()
    assert exc.value.statusCode == 500


def test_create_success(repo, session):
    mock_log = MagicMock()
    result = repo.create(mock_log)
    assert result is mock_log
    session.commit.assert_called_once()


def test_create_db_error_raises_500(repo, session):
    session.add.side_effect = Exception("constraint error")
    with pytest.raises(NoHarmException) as exc:
        repo.create(MagicMock())
    assert exc.value.statusCode == 500
    session.rollback.assert_called_once()




# ── findAll success ───────────────────────────────────────────────────────────

def test_findAll_returns_list(repo, session):
    session.query.return_value.all.return_value = []
    assert isinstance(repo.findAll(), list)


def test_findAll_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.count.return_value = 7
    session.query.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findAll(PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")
    assert result.total == 7


# ── findByType ────────────────────────────────────────────────────────────────

def test_findByType_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findByType(1), list)


def test_findByType_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 3
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findByType(1, PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")


def test_findByType_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findByType(1)
    assert exc.value.statusCode == 500


# ── findByCatalystId ──────────────────────────────────────────────────────────

def test_findByCatalystId_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    assert isinstance(repo.findByCatalystId("uid"), list)


def test_findByCatalystId_with_pagination(repo, session):
    from schemas.paginationSchemas import PaginationParams
    session.query.return_value.filter.return_value.count.return_value = 1
    session.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = repo.findByCatalystId("uid", PaginationParams(page=1, pageSize=10))
    assert hasattr(result, "total")


# ── findByDateRange ───────────────────────────────────────────────────────────

def test_findByDateRange_returns_list(repo, session):
    session.query.return_value.filter.return_value.all.return_value = []
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)
    assert isinstance(repo.findByDateRange(start, end), list)


def test_findByDateRange_db_error_raises_500(repo, session):
    session.query.side_effect = Exception("db error")
    with pytest.raises(NoHarmException) as exc:
        repo.findByDateRange(datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc))
    assert exc.value.statusCode == 500


