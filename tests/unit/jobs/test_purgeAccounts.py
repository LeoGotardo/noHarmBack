"""Unit tests for the account purge job.

The job is the only thing that ever hard-deletes a user, so what is asserted
here is mostly what it must *not* do: never touch an account inside its grace
window, never stop early because one row failed, never report success when
something was left behind.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.config import config


@pytest.fixture
def repository():
    """Patch the repository the job builds, and hand the mock back."""
    with patch("jobs.purgeAccounts.UserRepository") as MockRepository, \
         patch("jobs.purgeAccounts.database") as mockDatabase:
        mockDatabase.session = MagicMock()
        yield MockRepository.return_value


def test_purges_every_expired_account(repository):
    from jobs.purgeAccounts import purgeExpiredAccounts

    repository.findExpiredDeleted.return_value = ["uid-1", "uid-2"]

    failures = purgeExpiredAccounts()

    assert failures == 0
    repository.findExpiredDeleted.assert_called_once_with(config.ACCOUNT_DELETION_GRACE_DAYS)
    assert [call.args[0] for call in repository.purge.call_args_list] == ["uid-1", "uid-2"]


def test_nothing_to_purge_is_not_a_failure(repository):
    from jobs.purgeAccounts import purgeExpiredAccounts

    repository.findExpiredDeleted.return_value = []

    assert purgeExpiredAccounts() == 0
    repository.purge.assert_not_called()


def test_one_bad_row_does_not_stop_the_queue(repository):
    """A single account that cannot be deleted must not keep the rest waiting.

    Otherwise one poisoned row postpones every other user's deletion, night
    after night, and the promise made on the delete screen quietly stops being
    kept for everybody.
    """
    from jobs.purgeAccounts import purgeExpiredAccounts

    repository.findExpiredDeleted.return_value = ["uid-1", "uid-bad", "uid-3"]
    repository.purge.side_effect = [True, Exception("FK violation"), True]

    failures = purgeExpiredAccounts()

    assert failures == 1
    assert repository.purge.call_count == 3


def test_main_exit_code_reports_failures(repository):
    from jobs.purgeAccounts import main

    repository.findExpiredDeleted.return_value = ["uid-bad"]
    repository.purge.side_effect = Exception("boom")

    assert main() == 1


def test_main_exit_code_is_zero_on_a_clean_run(repository):
    from jobs.purgeAccounts import main

    repository.findExpiredDeleted.return_value = []

    assert main() == 0
