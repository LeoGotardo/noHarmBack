"""Row Level Security (RLS) context manager for PostgreSQL.

This module provides utilities to set the current user ID in the PostgreSQL
session, enabling Row Level Security policies to filter data appropriately.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional


class RLSContext:
    """Manages PostgreSQL Row Level Security session context.

    This class sets the app.current_user_id configuration parameter in PostgreSQL,
    which is used by RLS policies to filter rows based on the authenticated user.
    """

    @staticmethod
    def setUserId(db: Session, userId: Optional[str]) -> None:
        if userId:
            db.execute(
                text("SELECT set_config('app.current_user_id', :userId, true)"),
                {"userId": userId}
            )
        else:
            db.execute(text("SELECT set_config('app.current_user_id', '', true)"))

    @staticmethod
    def clearUserId(db: Session) -> None:
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
