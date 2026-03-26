from typing import Generator
from sqlalchemy.orm import Session
from core.database import database

def getDb() -> Generator[Session, None, None]:
    yield from database.getDb()