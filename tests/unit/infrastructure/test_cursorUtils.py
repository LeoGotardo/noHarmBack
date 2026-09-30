"""The feed's keyset cursor: opaque to the client, exact on the way back."""

from datetime import datetime
from uuid import uuid4

import pytest

from exceptions.baseExceptions import NoHarmException
from infrastructure.database.cursorUtils import decodeCursor, encodeCursor


def test_a_cursor_round_trips_to_the_microsecond():
    createdAt = datetime(2026, 10, 1, 12, 0, 0, 123456)
    rowId = uuid4()

    assert decodeCursor(encodeCursor(createdAt, rowId)) == (createdAt, rowId)


def test_no_cursor_means_from_the_start():
    assert decodeCursor(None) is None
    assert decodeCursor("") is None


@pytest.mark.parametrize("mangled", ["not-a-cursor!", "Zm9v", encodeCursor(datetime(2026, 1, 1), uuid4())[:-4]])
def test_a_mangled_cursor_is_a_400_not_a_silent_restart(mangled):
    with pytest.raises(NoHarmException) as exc:
        decodeCursor(mangled)

    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "INVALID_CURSOR"
