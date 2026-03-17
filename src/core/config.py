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
                Validator("DATABASE_URI", must_exist=True, is_type_of=str),
                Validator("DATABASE_NAME", must_exist=True, is_type_of=str),
                Validator("DATABASE_USER", must_exist=True, is_type_of=str),
                Validator("DATABASE_PASSWORD", must_exist=True, is_type_of=str),
                Validator("STORAGE_SERVICE_URI", must_exist=True, is_type_of=str),
                Validator("STORAGE_SERVICE_KEY", must_exist=True, is_type_of=str),
                Validator("EXEC_MODE", must_exist=True, is_type_of=str),
                Validator("DEBUG", must_exist=True, is_type_of=bool),
                Validator("PORT", must_exist=True, is_type_of=int),
                Validator("STATUS_CODES", must_exist=True, is_type_of=dict),
            ],
        )

        self._settings.validators.validate_all()

        # Atributos tipados e acessíveis diretamente
        self.ENCRYPTION_KEY: str = self._settings.ENCRYPTION_KEY
        self.DATABASE_URI: str = self._settings.DATABASE_URI
        self.DATABASE_NAME: str = self._settings.DATABASE_NAME
        self.DATABASE_USER: str = self._settings.DATABASE_USER
        self.DATABASE_PASSWORD: str = self._settings.DATABASE_PASSWORD
        self.STORAGE_SERVICE_URI: str = self._settings.STORAGE_SERVICE_URI
        self.STORAGE_SERVICE_KEY: str = self._settings.STORAGE_SERVICE_KEY
        self.EXEC_MODE: str = self._settings.EXEC_MODE
        self.DEBUG: bool = self._settings.DEBUG
        self.PORT: int = self._settings.PORT
        self.STATUS_CODES: dict = self._settings.STATUS_CODES


config = Config()