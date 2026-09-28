"""Unit tests for device-token registration.

The app registers its token on every start, so registration has to be an
upsert: inserting each time left one row per launch, and every row was a copy
of every push (migration 20260928_01).
"""

import pytest
from unittest.mock import MagicMock, patch

from core.config import config


@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    return s


@pytest.fixture
def db(session):
    d = MagicMock()
    d.session = session
    return d


@pytest.fixture
def Model():
    with patch("infrastructure.database.repositories.notificationRepository.NotificationModel") as M:
        yield M


@pytest.fixture
def repo(db, Model):
    from infrastructure.database.repositories.notificationRepository import NotificationRepository
    return NotificationRepository(db)


def test_a_new_token_is_inserted_with_its_preferences(repo, session, Model):
    repo.add("uid-1", "tok-1", messages=False, friends=True)

    Model.assert_called_once_with(user_id="uid-1", device_fcm="tok-1")
    session.add.assert_called_once_with(Model.return_value)
    row = Model.return_value
    assert row.status == config.STATUS_CODES["enabled"]
    assert row.messages is False
    assert row.friends is True
    session.commit.assert_called_once()


def test_a_known_token_is_updated_not_duplicated(repo, session, Model):
    existing = MagicMock()
    existing.status = config.STATUS_CODES["deleted"]
    session.query.return_value.filter.return_value.first.return_value = existing

    repo.add("uid-1", "tok-1", messages=True, friends=False)

    Model.assert_not_called()
    session.add.assert_not_called()
    # An unregistered device that registers again is enabled again.
    assert existing.status == config.STATUS_CODES["enabled"]
    assert existing.messages is True
    assert existing.friends is False


def test_preferences_default_to_everything_on(repo, Model):
    """An older app build sends only the token; it must keep every push."""
    repo.add("uid-1", "tok-1")

    assert Model.return_value.messages is True
    assert Model.return_value.friends is True
