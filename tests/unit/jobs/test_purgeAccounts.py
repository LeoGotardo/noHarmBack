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
def firebaseAuth():
    """Patch the Firebase app and its `auth` module; hand `auth` back."""
    import firebase_admin.auth as realAuth

    with patch("jobs.purgeAccounts.getFirebaseApp", return_value=MagicMock()), \
         patch("firebase_admin.auth.delete_user") as deleteUser:
        yield realAuth, deleteUser


@pytest.fixture
def repository(firebaseAuth):
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


# ── the Firebase sign-in record ──────────────────────────────────────────────


def test_deletes_the_firebase_user_before_the_row(repository, firebaseAuth):
    """The Privacy Policy says an erased account is erased; the email and Google
    identity in our Firebase project are part of that account."""
    from jobs.purgeAccounts import purgeExpiredAccounts

    _, deleteUser = firebaseAuth
    order = []
    deleteUser.side_effect = lambda uid, app=None: order.append(("firebase", uid))
    repository.purge.side_effect = lambda uid: order.append(("row", uid))
    repository.findExpiredDeleted.return_value = ["uid-1"]

    assert purgeExpiredAccounts() == 0
    assert order == [("firebase", "uid-1"), ("row", "uid-1")]


def test_a_firebase_user_already_gone_is_not_a_failure(repository, firebaseAuth):
    """What makes a retry safe: a run that deleted the Firebase user and then
    failed on the row must purge the row the next night."""
    from jobs.purgeAccounts import purgeExpiredAccounts

    auth, deleteUser = firebaseAuth
    deleteUser.side_effect = auth.UserNotFoundError("gone")
    repository.findExpiredDeleted.return_value = ["uid-1"]

    assert purgeExpiredAccounts() == 0
    repository.purge.assert_called_once_with("uid-1")


def test_firebase_refusing_keeps_the_row_for_the_next_run(repository, firebaseAuth):
    """Deleting the row anyway would orphan a Firebase user no run ever finds
    again, since the row is the only list of whom to delete."""
    from jobs.purgeAccounts import purgeExpiredAccounts

    _, deleteUser = firebaseAuth
    deleteUser.side_effect = Exception("503 from Firebase")
    repository.findExpiredDeleted.return_value = ["uid-1"]

    assert purgeExpiredAccounts() == 1
    repository.purge.assert_not_called()


def test_no_firebase_app_does_not_block_the_purge(repository):
    from jobs.purgeAccounts import purgeExpiredAccounts

    repository.findExpiredDeleted.return_value = ["uid-1"]
    with patch("jobs.purgeAccounts.getFirebaseApp", return_value=None):
        assert purgeExpiredAccounts() == 0
    repository.purge.assert_called_once_with("uid-1")
