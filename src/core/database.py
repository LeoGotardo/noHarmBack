from exceptions.databaseExceptions import NoEngineException, NoSessionException, NoDatabaseParamterException
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from core.config import Config


class Database:
    def __init__(self):
        self.database_url = Config.DATABASE_URL
        self.database_user = Config.DATABASE_USER
        self.database_password = Config.DATABASE_PASSWORD
        self.database_host = Config.DATABASE_HOST
        self.database_name = Config.DATABASE_NAME
        self._engine = self.setupEngine()
        self._session = self.setupSession()

    
    @property
    def session(self):
        if self._session is None:
            raise NoSessionException()
        return self._session
    
    
    @property
    def engine(self):
        if self._engine is None:
            raise NoEngineException()
        return self._engine
    
    
    @property
    def database_uri(self):
        for key in ["DATABASE_URL", "DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD"]:
            if not Config.__dict__.get(key):
                raise NoDatabaseParamterException(f"Missing database connection parameter: {key}")
        
        return f"{self.database_url}://{self.database_user}:{self.database_password}@{self.database_host}/{self.database_name}"
    
    
    def setupEngine(self):
        return create_engine(self.database_uri, pool_pre_ping=True)
        

    def setupSession(self):
        return sessionmaker(bind=self._engine)()