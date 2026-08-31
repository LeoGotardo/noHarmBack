"""Row Level Security (RLS) context manager for PostgreSQL.

This module provides utilities to set the current user ID in the PostgreSQL
session, enabling Row Level Security policies to filter data appropriately.

The policies that read it live in migration 20260831_02. They treat "no context
set" as "no restriction", because several server-internal paths legitimately
touch rows belonging to other users — the push fan-out, the auth routes — and
none of them has a user to scope to. Setting this variable is therefore what
*turns RLS on* for a request, not what unlocks it.
"""

from sqlalchemy.orm import Session
from sqlalchemy import event, text
from typing import Optional


# Where the session remembers its user between transactions. `Session.info` is
# a plain dict SQLAlchemy carries for exactly this kind of thing and never
# touches itself.
_USER_ID_KEY = "rlsUserId"


@event.listens_for(Session, "after_begin")
def _applyRlsContext(session: Session, transaction, connection) -> None:
    """Stamp the session's user onto every transaction it opens.

    This listener is what makes the context outlive a commit. Two facts make it
    necessary, and neither is obvious:

    1. Repositories commit inside a request — 47 call sites do. A
       transaction-local setting dies with that commit.
    2. A Session releases its connection back to the pool when a transaction
       ends, so the *next* statement may run on a different connection
       entirely. Setting the variable at session scope does not survive that
       either; it was tried, and the value was simply gone.

    So the only thing that reliably holds is re-applying it whenever a
    transaction begins, which is what happens here.

    The variable stays transaction-local (`set_config(..., true)`), which is
    also what makes a leak impossible: it cannot outlive the transaction that
    set it, so a pooled connection can never hand one request's user to the
    next. A session with no user stamps the empty string, which the policies in
    migration 20260831_02 read as "no context" — the same state a fresh
    connection is in.
    """
    connection.execute(
        text("SELECT set_config('app.current_user_id', :userId, true)"),
        {"userId": session.info.get(_USER_ID_KEY) or ""},
    )


class RLSContext:
    """Manages PostgreSQL Row Level Security session context.

    This class sets the app.current_user_id configuration parameter in PostgreSQL,
    which is used by RLS policies to filter rows based on the authenticated user.
    """

    # Records the user on the session and applies it to the transaction in
    # progress. Every later transaction gets it from the listener above, which
    # is what carries the context across the commits a request makes.
    @staticmethod
    def setUserId(db: Session, userId: Optional[str]) -> None:
        db.info[_USER_ID_KEY] = userId or None

        db.execute(
            text("SELECT set_config('app.current_user_id', :userId, true)"),
            {"userId": userId or ""}
        )

    @staticmethod
    def clearUserId(db: Session) -> None:
        db.info.pop(_USER_ID_KEY, None)
        db.execute(text("SELECT set_config('app.current_user_id', '', true)"))


class RLSQueryFilter:
    """Alternative approach: SQLAlchemy query filter mixin.

    This can be used when RLS is not enabled at the database level,
    providing application-level filtering for the same rules.
    """

    @staticmethod
    def filterByOwner(query, userId: str, ownerColumn: str = "owner_id"):
        """Filter a query to only return rows owned by the user.

        Args:
            query: SQLAlchemy query object
            userId: The user's UUID as string
            ownerColumn: The column name containing the owner reference

        Returns:
            Filtered query
        """
        return query.filter_by(**{ownerColumn: userId})

    @staticmethod
    def filterByParticipant(query, userId: str, senderColumn: str = "sender", receiverColumn: str = "reciver"):
        """Filter a query to return rows where user is sender OR receiver.

        Used for friendships and chats.

        Args:
            query: SQLAlchemy query object
            userId: The user's UUID as string
            senderColumn: The column name for sender
            receiverColumn: The column name for receiver

        Returns:
            Filtered query
        """
        from sqlalchemy import or_
        return query.filter(
            or_(
                getattr(query.column_descriptions[0]['entity'], senderColumn) == userId,
                getattr(query.column_descriptions[0]['entity'], receiverColumn) == userId
            )
        )
