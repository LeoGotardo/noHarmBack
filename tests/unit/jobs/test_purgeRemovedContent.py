"""Unit tests for the removed-content retention sweep."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.config import config


@pytest.fixture
def repositories():
    with patch("jobs.purgeRemovedContent.PostRepository") as Posts, \
         patch("jobs.purgeRemovedContent.PostCommentRepository") as Comments, \
         patch("jobs.purgeRemovedContent.database") as mockDatabase:
        mockDatabase.session = MagicMock()
        yield Posts.return_value, Comments.return_value


def test_sweeps_both_tables_with_the_configured_window(repositories):
    from jobs.purgeRemovedContent import purgeRemovedContent

    posts, comments = repositories
    posts.deleteRemovedBefore.return_value = 2
    comments.deleteRemovedBefore.return_value = 5

    assert purgeRemovedContent() == (2, 5)

    cutoff = posts.deleteRemovedBefore.call_args[0][0]
    expected = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=config.REMOVED_CONTENT_RETENTION_DAYS)
    assert abs((cutoff - expected).total_seconds()) < 5
    assert comments.deleteRemovedBefore.call_args[0][0] == cutoff


def test_a_failure_is_a_non_zero_exit(repositories):
    from jobs.purgeRemovedContent import main

    repositories[0].deleteRemovedBefore.side_effect = Exception("database unreachable")

    assert main() == 1


def test_nothing_to_delete_is_a_clean_run(repositories):
    from jobs.purgeRemovedContent import main

    repositories[0].deleteRemovedBefore.return_value = 0
    repositories[1].deleteRemovedBefore.return_value = 0

    assert main() == 0
