"""Unit tests for push fan-out and the categories a device can switch off."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def query():
    """The query `sendPushToUser` builds, with its devices."""
    session = MagicMock()
    q = session.query.return_value.filter.return_value
    device = MagicMock(device_fcm="tok-1")
    q.all.return_value = [device]
    q.filter.return_value.all.return_value = [device]
    with patch("core.database.database") as database, \
         patch("infrastructure.external.fcmService.sendPush") as sendPush:
        database.session = session
        yield q, sendPush


def test_a_category_filters_on_its_column(query):
    from infrastructure.external.fcmService import sendPushToUser

    q, sendPush = query
    sendPushToUser("uid-1", "New message", "hi", category="messages")

    q.filter.assert_called_once()
    sendPush.assert_called_once_with(["tok-1"], "New message", "hi")


def test_no_category_goes_to_every_enabled_device(query):
    from infrastructure.external.fcmService import sendPushToUser

    q, sendPush = query
    sendPushToUser("uid-1", "Badge unlocked!", "You earned 7 days")

    q.filter.assert_not_called()
    sendPush.assert_called_once_with(["tok-1"], "Badge unlocked!", "You earned 7 days")


def test_an_unknown_category_is_refused():
    """A typo must not quietly push to everyone, or to no one."""
    from infrastructure.external.fcmService import sendPushToUser

    with pytest.raises(ValueError):
        sendPushToUser("uid-1", "t", "b", category="message")


def test_every_category_is_a_column():
    from infrastructure.database.models.notificationModel import NotificationModel
    from infrastructure.external.fcmService import CATEGORIES

    for name in CATEGORIES:
        assert hasattr(NotificationModel, name)
