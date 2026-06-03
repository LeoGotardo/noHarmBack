import pytest
from unittest.mock import MagicMock
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.badgeService import BadgeService
    service = BadgeService(mock_db)
    service.badgeRepository = MagicMock()
    return service


def test_getAll_delegates_to_repo(mock_db):
    service = _make_service(mock_db)
    service.badgeRepository.findAll.return_value = []
    result = service.getAll()
    service.badgeRepository.findAll.assert_called_once_with(None)
    assert result == []


def test_getAll_with_params(mock_db):
    from schemas.paginationSchemas import PaginationParams
    service = _make_service(mock_db)
    params = PaginationParams(page=2, pageSize=10)
    service.badgeRepository.findAll.return_value = []
    service.getAll(params)
    service.badgeRepository.findAll.assert_called_once_with(params)


def test_get_delegates_to_repo(mock_db):
    service = _make_service(mock_db)
    mock_badge = MagicMock()
    service.badgeRepository.findById.return_value = mock_badge
    result = service.get("badge-001")
    assert result is mock_badge
    service.badgeRepository.findById.assert_called_once_with("badge-001")


def test_get_not_found_propagates_404(mock_db):
    service = _make_service(mock_db)
    service.badgeRepository.findById.side_effect = NoHarmException(statusCode=404)
    with pytest.raises(NoHarmException) as exc:
        service.get("nonexistent")
    assert exc.value.statusCode == 404


def test_create_delegates_to_repo(mock_db):
    service = _make_service(mock_db)
    mock_badge = MagicMock()
    service.badgeRepository.create.return_value = mock_badge
    result = service.create(mock_badge)
    assert result is mock_badge
    service.badgeRepository.create.assert_called_once_with(mock_badge)


def test_updateStatus_delegates_to_repo(mock_db):
    service = _make_service(mock_db)
    service.updateStatus("badge-001", 0)
    service.badgeRepository.updateStatus.assert_called_once_with("badge-001", 0)


def test_delete_calls_softDelete(mock_db):
    service = _make_service(mock_db)
    service.delete("badge-001")
    service.badgeRepository.softDelete.assert_called_once_with("badge-001")
