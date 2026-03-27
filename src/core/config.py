# src/core/config.py
from dynaconf import Dynaconf, Validator

class Config:
    def __init__(self):
        self._settings = Dynaconf(
            envar_prefix="NOHARMBACK",
            settings_files=["config.toml", ".secrets.toml"],
            environments=True,
            load_dotenv=True,
            validators=[
                Validator("ENCRYPTION_KEY", must_exist=True, is_type_of=str),
                Validator("DATABASE_URL", must_exist=True, is_type_of=str),
                Validator("DATABASE_HOST", must_exist=True, is_type_of=str),
                Validator("DATABASE_NAME", must_exist=True, is_type_of=str),
                Validator("DATABASE_USER", must_exist=True, is_type_of=str),
                Validator("DATABASE_PASSWORD", must_exist=True, is_type_of=str),
                Validator("DATABASE_URL_UNPOOLED", must_exist=True, is_type_of=str),
                Validator("STORAGE_SERVICE_URI", must_exist=True, is_type_of=str),
                Validator("STORAGE_SERVICE_KEY", must_exist=True, is_type_of=str),
                Validator("EXEC_MODE", must_exist=True, is_type_of=str),
                Validator("DEBUG", must_exist=True, is_type_of=bool),
                Validator("PORT", must_exist=True, is_type_of=int),
                Validator("STATUS_CODES", must_exist=True, is_type_of=dict),
                Validator("JWT_SECRET_KEY", must_exist=True, is_type_of=str),
                Validator("JWT_REFRESH_SECRET_KEY", must_exist=True, is_type_of=str),
                Validator("JWT_ALGORITHM", must_exist=True, is_type_of=str),
                Validator("ACCESS_TOKEN_EXPIRE_MINUTES", must_exist=True, is_type_of=int),
                Validator("REFRESH_TOKEN_EXPIRE_DAYS", must_exist=True, is_type_of=int),
                Validator("STORAGE_PATH", must_exist=True, is_type_of=str),
                Validator("ALLOWED_ORIGINS", must_exist=True, is_type_of=list),
            ],
        )

        self._settings.validators.validate_all()

        # Atributos tipados e acessíveis diretamente
        self.ENCRYPTION_KEY: str = self._settings.ENCRYPTION_KEY
        self.DATABASE_URL: str = self._settings.DATABASE_URL
        self.DATABASE_HOST: str = self._settings.DATABASE_HOST
        self.DATABASE_NAME: str = self._settings.DATABASE_NAME
        self.DATABASE_USER: str = self._settings.DATABASE_USER
        self.DATABASE_URL_UNPOOLED: str = self._settings.DATABASE_URL_UNPOOLED
        self.DATABASE_PASSWORD: str = self._settings.DATABASE_PASSWORD
        self.STORAGE_SERVICE_URI: str = self._settings.STORAGE_SERVICE_URI
        self.STORAGE_SERVICE_KEY: str = self._settings.STORAGE_SERVICE_KEY
        self.EXEC_MODE: str = self._settings.EXEC_MODE
        self.DEBUG: bool = self._settings.DEBUG
        self.PORT: int = self._settings.PORT
        self.STATUS_CODES: dict = self._settings.STATUS_CODES
        self.JWT_SECRET_KEY: str = self._settings.JWT_SECRET_KEY
        self.JWT_REFRESH_SECRET_KEY: str = self._settings.JWT_REFRESH_SECRET_KEY
        self.JWT_ALGORITHM: str = self._settings.JWT_ALGORITHM
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = self._settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = self._settings.REFRESH_TOKEN_EXPIRE_DAYS
        self.STORAGE_PATH: str = self._settings.STORAGE_PATH
        self.ALLOWED_ORIGINS: list = self._settings.ALLOWED_ORIGINS


config = Config()