"""Row Level Security (RLS) context manager for PostgreSQL.

This module provides utilities to set the current user ID in the PostgreSQL
session, enabling Row Level Security policies to filter data appropriately.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import uuid


class RLSContext:
    """Manages PostgreSQL Row Level Security session context.

    This class sets the app.current_user_id configuration parameter in PostgreSQL,
    which is used by RLS policies to filter rows based on the authenticated user.
    """

    @staticmethod
    def setUserId(db: Session, userId: Optional[str]) -> None:
        """Set the current user ID in the PostgreSQL session.

        This must be called after getting a database session and before
        executing any queries that should be filtered by RLS.

        Args:
            db: SQLAlchemy session
            userId: The authenticated user's UUID as string, or None for anonymous

        Example:
            >>> db = next(getDb())
            >>> RLSContext.setUserId(db, "550e8400-e29b-41d4-a716-446655440000")
            >>> # Now all queries will be filtered by RLS
        """
        if userId:
            # Validate UUID format
            try:
                uuid.UUID(userId)
            except ValueError:
                raise ValueError(f"Invalid UUID format: {userId}")

            db.execute(
                text("SELECT set_current_user_id(:userId)"),
                {"userId": userId}
            )
        else:
            # Clear the user context for anonymous requests
            db.execute(text("SELECT set_current_user_id(NULL)"))

    @staticmethod
    def clearUserId(db: Session) -> None:
        """Clear the current user ID from the PostgreSQL session.

        Args:
            db: SQLAlchemy session
        """
        db.execute(text("SELECT set_current_user_id(NULL)"))


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
