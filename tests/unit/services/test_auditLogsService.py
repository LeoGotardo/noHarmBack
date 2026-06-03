import pytest
from unittest.mock import MagicMock
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.auditLogsService import AuditLogsService
    service = AuditLogsService(mock_db)
    service.auditLogsRepository = MagicMock()
    return service


def test_getAll_delegates(mock_db):
    service = _make_service(mock_db)
    service.auditLogsRepository.findAll.return_value = []
    assert service.getAll() == []
    service.auditLogsRepository.findAll.assert_called_once_with(None)


def test_get_success(mock_db):
    service = _make_service(mock_db)
    mock_log = MagicMock()
    service.auditLogsRepository.findById.return_value = mock_log
    assert service.get("log-001") is mock_log


def test_get_not_found_propagates(mock_db):
    service = _make_service(mock_db)
    service.auditLogsRepository.findById.side_effect = NoHarmException(statusCode=404)
    with pytest.raises(NoHarmException) as exc:
        service.get("ghost")
    assert exc.value.statusCode == 404


def test_create_delegates(mock_db):
    service = _make_service(mock_db)
    mock_log = MagicMock()
    service.auditLogsRepository.create.return_value = mock_log
    assert service.create(mock_log) is mock_log


def test_getByCatalyst_delegates(mock_db):
    service = _make_service(mock_db)
    service.auditLogsRepository.findByCatalystId.return_value = []
    service.getByCatalyst("uid-001")
    service.auditLogsRepository.findByCatalystId.assert_called_once_with("uid-001", None)


def test_getByType_delegates(mock_db):
    service = _make_service(mock_db)
    service.auditLogsRepository.findByType.return_value = []
    service.getByType(1)
    service.auditLogsRepository.findByType.assert_called_once_with(1, None)


def test_getByDateRange_valid(mock_db):
    service = _make_service(mock_db)
    service.auditLogsRepository.findByDateRange.return_value = []
    service.getByDateRange("2024-01-01", "2024-12-31")
    service.auditLogsRepository.findByDateRange.assert_called_once()


def test_getByDateRange_invalid_format_raises(mock_db):
    service = _make_service(mock_db)
    with pytest.raises(ValueError):
        service.getByDateRange("not-a-date", "2024-12-31")


