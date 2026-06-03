import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.userBadgeService import UserBadgeService
    service = UserBadgeService(mock_db)
    service.userBadgeRepository = MagicMock()
    return service


def test_findById_delegates(mock_db):
    service = _make_service(mock_db)
    mock_ub = MagicMock()
    service.userBadgeRepository.findById.return_value = mock_ub
    assert service.findById("ub-001") is mock_ub


def test_findById_not_found_propagates(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.findById.side_effect = NoHarmException(statusCode=404)
    with pytest.raises(NoHarmException) as exc:
        service.findById("ghost")
    assert exc.value.statusCode == 404


def test_findByUserId_delegates(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.findByUserId.return_value = []
    result = service.findByUserId("uid-001")
    service.userBadgeRepository.findByUserId.assert_called_once_with("uid-001", None)
    assert result == []


def test_findByBadgeId_delegates(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.findByBadgeId.return_value = []
    result = service.findByBadgeId("bid-001")
    service.userBadgeRepository.findByBadgeId.assert_called_once_with("bid-001", None)
    assert result == []


def test_existsByUserAndBadge_true(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.existsByUserAndBadge.return_value = True
    assert service.existsByUserAndBadge("uid", "bid") is True


def test_existsByUserAndBadge_false(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.existsByUserAndBadge.return_value = False
    assert service.existsByUserAndBadge("uid", "bid") is False


def test_grant_delegates(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.grant.return_value = True
    dt =datetime.now(timezone.utc)
    result = service.grant("uid", "bid", dt)
    assert result is True
    service.userBadgeRepository.grant.assert_called_once_with("uid", "bid", dt)


def test_revoke_delegates(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.revoke.return_value = True
    assert service.revoke("uid", "bid") is True


def test_updateStatus_delegates(mock_db):
    service = _make_service(mock_db)
    mock_ub = MagicMock()
    service.userBadgeRepository.updateStatus.return_value = mock_ub
    result = service.updateStatus("ub-001", 0)
    assert result is mock_ub


def test_delete_calls_softDelete(mock_db):
    service = _make_service(mock_db)
    service.userBadgeRepository.softDelete.return_value = True
    assert service.delete("ub-001") is True
    service.userBadgeRepository.softDelete.assert_called_once_with("ub-001")
