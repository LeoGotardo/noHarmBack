from typing import Generator
from fastapi import Depends
from sqlalchemy.orm import Session
from core.database import database
from infrastructure.database.rlsContext import RLSContext
from api.dependencies.auth import getCurrentUser


class _DbProxy:
    """Wraps a raw SQLAlchemy Session to match the Database interface expected by repositories."""
    def __init__(self, session: Session):
        self._session = session
        self.engine = database.engine

    @property
    def session(self) -> Session:
        return self._session


def getDb() -> Generator[_DbProxy, None, None]:
    """Database session without RLS context. Use for public/admin endpoints."""
    session = database.session
    try:
        yield _DbProxy(session)
    finally:
        session.close()


def getDbWithRLS(
    userId: str = Depends(getCurrentUser)
) -> Generator[_DbProxy, None, None]:
    """Database session with RLS context set for the authenticated user."""
    session = database.session
    try:
        RLSContext.setUserId(session, userId)
        yield _DbProxy(session)
    finally:
        session.close()