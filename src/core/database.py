from exceptions.databaseExceptions import NoEngineException, NoSessionException, NoDatabaseParamterException
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from core.config import config
from typing import Generator


class Database:
    def __init__(self):
        self.database_url      = config.DATABASE_URL
        self.database_user     = config.DATABASE_USER
        self.database_password = config.DATABASE_PASSWORD
        self.database_host     = config.DATABASE_HOST
        self.database_name     = config.DATABASE_NAME
        self._engine           = self._setupEngine()
        self._SessionLocal     = self._setupSession()


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


    @property
    def _database_uri(self) -> str:
        missing = [
            key for key in ["database_url", "database_host", "database_name", "database_user", "database_password"]
            if not getattr(self, key, None)
        ]
        if missing:
            raise NoDatabaseParamterException(f"Missing: {', '.join(missing)}")

        return f"{self.database_url}://{self.database_user}:{self.database_password}@{self.database_host}/{self.database_name}"


    def _setupEngine(self):
        return create_engine(self._database_uri, pool_pre_ping=True)


    def _setupSession(self):
        return sessionmaker(bind=self._engine, autocommit=False, autoflush=False)


    def getDb(self) -> Generator[Session, None, None]:
        
        """
        Dependency do FastAPI.
        Uso nas rotas: db: Session = Depends(database.getDb)
        """
        db = self._SessionLocal()
        try:
            yield db
        finally:
            db.close()


database = Database()