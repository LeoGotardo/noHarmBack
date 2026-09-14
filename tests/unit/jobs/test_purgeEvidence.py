"""Unit tests for the report-evidence retention sweep.

The job deletes copied private messages once the report they belong to has been
closed long enough. What matters here is the split it has to keep: the evidence
goes, the report stays, and an unreviewed report is never touched.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.config import config


@pytest.fixture
def repository():
    with patch("jobs.purgeEvidence.ReportEvidenceRepository") as MockRepository, \
         patch("jobs.purgeEvidence.database") as mockDatabase:
        mockDatabase.session = MagicMock()
        yield MockRepository.return_value


def test_sweeps_with_the_configured_window(repository):
    from jobs.purgeEvidence import purgeExpiredEvidence

    repository.deleteExpired.return_value = 7

    assert purgeExpiredEvidence() == 7
    repository.deleteExpired.assert_called_once_with(config.REPORT_EVIDENCE_RETENTION_DAYS)


def test_nothing_to_delete_is_a_clean_run(repository):
    from jobs.purgeEvidence import purgeExpiredEvidence, main

    repository.deleteExpired.return_value = 0

    assert purgeExpiredEvidence() == 0
    assert main() == 0


def test_a_failure_is_reported_as_a_non_zero_exit(repository):
    """Cron has to be able to tell a quiet night from a broken job."""
    from jobs.purgeEvidence import main

    repository.deleteExpired.side_effect = Exception("database unreachable")

    assert main() == 1
