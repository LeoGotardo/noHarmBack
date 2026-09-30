"""Opaque keyset cursors for lists that change while they are read.

`page=2` is the wrong question for a feed. A post published between two requests
pushes everything down by one, and the client sees the last item of page 1 again
at the top of page 2. A keyset cursor asks "what comes after *this* row"
instead, which a new row at the top cannot disturb.

The cursor is `(created_at, id)` — the id breaks ties between rows written in the
same microsecond — packed as url-safe base64 so the client treats it as a token
and never starts building one.
"""

import base64
import binascii

from datetime import datetime
from typing import Optional
from uuid import UUID

from exceptions.baseExceptions import NoHarmException


Cursor = tuple[datetime, UUID]


def encodeCursor(createdAt: datetime, rowId) -> str:
    raw = f"{createdAt.isoformat()}|{rowId}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decodeCursor(cursor: Optional[str]) -> Optional[Cursor]:
    """The position a cursor names, or None for "from the start".

    Anything that does not decode is a 400 rather than a silent restart: a
    client that sent a mangled cursor and got page one back would show the
    reader everything twice without any error to find.
    """
    if not cursor:
        return None

    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        text = base64.urlsafe_b64decode(padded.encode()).decode()
        createdAt, rowId = text.split("|", 1)
        return datetime.fromisoformat(createdAt), UUID(rowId)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise NoHarmException(
            statusCode=400,
            errorCode="INVALID_CURSOR",
            message="Invalid cursor."
        )
