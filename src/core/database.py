from exceptions.databaseExceptions import NoEngineException, NoSessionException
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from core.config import config
from typing import Generator
from infrastructure.external.storageService import Base


class Database:
    def __init__(self):
        self._engine       = self._setupEngine()
        self._SessionLocal = self._setupSession()
        
        self._createTables()


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
        # SQLAlchemy 2.x não aceita "postgres://", só "postgresql://"
        dbUrl = config.DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        return create_engine(
            dbUrl,
            pool_pre_ping=True,
            connect_args={"sslmode": "require"}
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
            
            
    def _createTables(self):
        Base.metadata.create_all(self._engine)


database = Database()