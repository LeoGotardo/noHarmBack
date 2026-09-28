"""Unit tests for ConsentService."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.consentService import ConsentService
    service = ConsentService(mock_db)
    service.consentRepository = MagicMock()
    service.streakRepository = MagicMock()
    service.userRepository = MagicMock()
    service.auditRepository = MagicMock()
    return service


def _consent(document="terms", version=None, withdrawn_at=None):
    from domain.services.consentService import ConsentService
    c = MagicMock()
    c.document = document
    c.version = version if version is not None else ConsentService.currentVersion(document)
    c.withdrawn_at = withdrawn_at
    c.active = withdrawn_at is None
    return c


def _current(**documents):
    return {document: consent for document, consent in documents.items()}


# ── pending ───────────────────────────────────────────────────────────────────

def test_an_account_that_agreed_to_nothing_owes_both_binding_documents(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = {}

    assert service.pending("uid-001") == ["terms", "privacy"]


def test_current_versions_of_both_leaves_nothing_pending(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = _current(
        terms=_consent("terms"),
        privacy=_consent("privacy"),
    )

    assert service.pending("uid-001") == []


def test_an_out_of_date_version_is_pending_again(mock_db):
    """Republishing is a config change and nothing else.

    The stored row names the revision that was live when it was signed, so
    bumping TERMS_VERSION makes every existing row stale by comparison. A
    boolean would mean the account had agreed, once, to a text since rewritten.
    """
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = _current(
        terms=_consent("terms", version="0.9-ancient"),
        privacy=_consent("privacy"),
    )

    assert service.pending("uid-001") == ["terms"]


def test_health_data_never_given_is_not_pending(mock_db):
    """Declining is an answer. Blocking on it would make the choice fake."""
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = _current(
        terms=_consent("terms"),
        privacy=_consent("privacy"),
    )

    assert service.pending("uid-001") == []
    assert service.hasHealthDataConsent("uid-001") is False


def test_health_data_withdrawn_is_not_pending(mock_db):
    """Withdrawing must not put the user back in front of the same question."""
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = _current(
        terms=_consent("terms"),
        privacy=_consent("privacy"),
        health_data=_consent("health_data", withdrawn_at=datetime.now(timezone.utc)),
    )

    assert service.pending("uid-001") == []
    assert service.hasHealthDataConsent("uid-001") is False


def test_health_data_active_but_stale_is_pending(mock_db):
    """Still using the feature, so still owes an answer on the current text."""
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = _current(
        terms=_consent("terms"),
        privacy=_consent("privacy"),
        health_data=_consent("health_data", version="0.9-ancient"),
    )

    assert service.pending("uid-001") == ["health_data"]


def test_a_withdrawn_binding_consent_reads_as_owing_an_answer(mock_db):
    """Nothing offers this today; the gate must not unlock if something does."""
    service = _make_service(mock_db)
    service.consentRepository.findCurrent.return_value = _current(
        terms=_consent("terms", withdrawn_at=datetime.now(timezone.utc)),
        privacy=_consent("privacy"),
    )

    assert service.pending("uid-001") == ["terms"]


# ── accept ────────────────────────────────────────────────────────────────────

def test_accept_stamps_the_version_from_config_not_the_caller(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.createMany.return_value = []

    service.accept("uid-001", ["terms"])

    written = service.consentRepository.createMany.call_args[0][0]
    assert len(written) == 1
    assert written[0].document == "terms"
    assert written[0].version == config.TERMS_VERSION


def test_accept_writes_in_document_order_whatever_order_was_asked(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.createMany.return_value = []

    service.accept("uid-001", ["health_data", "privacy", "terms"])

    written = service.consentRepository.createMany.call_args[0][0]
    assert [c.document for c in written] == ["terms", "privacy", "health_data"]


def test_accept_deduplicates(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.createMany.return_value = []

    service.accept("uid-001", ["terms", "terms"])

    written = service.consentRepository.createMany.call_args[0][0]
    assert len(written) == 1


def test_accept_unknown_document_raises_400(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.accept("uid-001", ["cookies"])

    assert exc.value.statusCode == 400
    service.consentRepository.createMany.assert_not_called()


def test_accept_nothing_raises_400(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.accept("uid-001", [])

    assert exc.value.statusCode == 400


def test_registration_consents_omit_health_data_when_declined(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.createMany.return_value = []

    service.recordRegistrationConsents("uid-001", healthData=False)

    written = service.consentRepository.createMany.call_args[0][0]
    assert [c.document for c in written] == ["terms", "privacy"]


def test_registration_consents_include_health_data_when_given(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.createMany.return_value = []

    service.recordRegistrationConsents("uid-001", healthData=True)

    written = service.consentRepository.createMany.call_args[0][0]
    assert [c.document for c in written] == ["terms", "privacy", "health_data"]


# ── withdrawal ────────────────────────────────────────────────────────────────

def test_withdrawing_health_data_deletes_every_streak(mock_db):
    """Withdrawal that leaves the data in place is not withdrawal.

    All of them — the active one, the closed history, the personal record.
    """
    service = _make_service(mock_db)
    service.consentRepository.withdraw.return_value = _consent("health_data")
    service.streakRepository.findAllByOwnerId.return_value = [
        MagicMock(id="streak-1"), MagicMock(id="streak-2"), MagicMock(id="streak-3")
    ]

    result = service.withdrawHealthData("uid-001")

    assert result == {"withdrawn": True, "streaksDeleted": 3}
    assert service.streakRepository.delete.call_count == 3


def test_withdrawing_nothing_in_force_deletes_nothing(mock_db):
    """Idempotent, and it must not take the streaks of an account that never
    consented in the first place."""
    service = _make_service(mock_db)
    service.consentRepository.withdraw.return_value = None

    result = service.withdrawHealthData("uid-001")

    assert result == {"withdrawn": False, "streaksDeleted": 0}
    service.streakRepository.delete.assert_not_called()


def test_one_failed_delete_does_not_strand_the_rest(mock_db):
    service = _make_service(mock_db)
    service.consentRepository.withdraw.return_value = _consent("health_data")
    service.streakRepository.findAllByOwnerId.return_value = [
        MagicMock(id="streak-1"), MagicMock(id="streak-2"), MagicMock(id="streak-3")
    ]
    service.streakRepository.delete.side_effect = [None, Exception("boom"), None]

    result = service.withdrawHealthData("uid-001")

    assert result["withdrawn"] is True
    assert result["streaksDeleted"] == 2
    assert service.streakRepository.delete.call_count == 3
