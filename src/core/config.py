from dynaconf import Dynaconf, Validator

class Config:
    STATUS_CODES: dict
    EMCRYPTION_KEY: str
    DATABASE_URI: str
    DATABASE_NAME: str
    DATABASE_USER: str
    DATABASE_PASSWORD: str
    STORAGE_SERVICE_URI: str
    STORAGE_SERVICE_KEY: str
    EXEC_MODE: str
    DEBUG: bool
    PORT: int
    
    def __init__(self):
        Dynaconf(
            envar_prefix="NOHARMBACK",
            settings_files=["config.toml"],
            validators=[
                Validator("STATUS_CODES", is_type_of=dict),
                Validator("EMCRYPTION_KEY", is_type_of=str),
                Validator("DATABASE_URI", is_type_of=str),
                Validator("DATABASE_NAME", is_type_of=str),
                Validator("DATABASE_USER", is_type_of=str),
                Validator("DATABASE_PASSWORD", is_type_of=str),
                Validator("STORAGE_SERVICE_URI", is_type_of=str),
                Validator("STORAGE_SERVICE_KEY", is_type_of=str),
                Validator("EXEC_MODE", is_type_of=str),
                Validator("DEBUG", is_type_of=bool),
                Validator("PORT", is_type_of=int),
            ],
        )