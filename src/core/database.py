from exceptions.databaseExceptions import NoEngineException, NoSessionException
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from core.config import config
from typing import Generator

# Registers every model with SQLAlchemy. The package imports all ten — the
# relationships are declared as strings and only resolve once the classes they
# name have been imported (see models/__init__.py).
import infrastructure.database.models  # noqa: F401

# Schema creation is Alembic's, not this module's. `Base.metadata.create_all`
# used to run here on import, which was quietly dangerous once the row level
# security policies landed: create_all makes tables and knows nothing about
# policies, so a database built that way came up with RLS switched off and
# looked entirely normal. `alembic upgrade head` is the only path that produces
# a correct schema — the dev container runs it before starting, and deployed it
# is its own ECS task.




class Database:
    def __init__(self):
        self._engine       = self._setupEngine()
        self._SessionLocal = self._setupSession()


    @property
    def session(self) -> Session:
        if self._SessionLocal is None:
            raise NoSessionException()
        return self._SessionLocal()


    @property
    def engine(self):
        if self._engine is None:
            raise NoEngineException()
        return self._engine


    def _setupEngine(self):
        # SQLAlchemy 2.x requires "postgresql://", not "postgres://"
        dbUrl = config.DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        return create_engine(
            dbUrl,
            pool_pre_ping=True,
        )


    def _setupSession(self):
        return sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False
        )


    def getDb(self) -> Generator[Session, None, None]:
        db = self._SessionLocal()
        try:
            yield db
        finally:
            db.close()



database = Database()