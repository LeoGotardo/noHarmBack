import os
import json

class Config:
    def __init__(self):
        def require(key: str) -> str:
            val = os.environ.get(key)
            if val is None:
                raise RuntimeError(f"Missing required environment variable: {key}")
            return val

        self.ENCRYPTION_KEY: str              = require("ENCRYPTION_KEY")
        self.DATABASE_URL: str                = require("DATABASE_URL")
        self.DATABASE_HOST: str               = require("DATABASE_HOST")
        self.DATABASE_NAME: str               = require("DATABASE_NAME")
        self.DATABASE_USER: str               = require("DATABASE_USER")
        self.DATABASE_PASSWORD: str           = require("DATABASE_PASSWORD")
        self.DATABASE_URL_UNPOOLED: str       = require("DATABASE_URL_UNPOOLED")
        self.STORAGE_SERVICE_URI: str         = require("STORAGE_SERVICE_URI")
        self.STORAGE_SERVICE_KEY: str         = require("STORAGE_SERVICE_KEY")
        self.EXEC_MODE: str                   = require("EXEC_MODE")
        self.DEBUG: bool                      = os.environ.get("DEBUG", "false").lower() == "true"
        self.PORT: int                        = int(os.environ.get("PORT", "8080"))
        self.JWT_SECRET_KEY: str              = require("JWT_SECRET_KEY")
        self.JWT_REFRESH_SECRET_KEY: str      = require("JWT_REFRESH_SECRET_KEY")
        self.JWT_ALGORITHM: str               = os.environ.get("JWT_ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
        self.REFRESH_TOKEN_EXPIRE_DAYS: int   = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        self.STORAGE_PATH: str                = os.environ.get("STORAGE_PATH", "/tmp")
        self.ALLOWED_ORIGINS: list            = json.loads(os.environ.get("ALLOWED_ORIGINS", '["*"]'))
        self.STATUS_CODES: dict               = json.loads(require("STATUS_CODES"))

        # Suporte local via .env
        self._loadDotEnvIfLocal()

    def _loadDotEnvIfLocal(self):
        """Carrega .secrets.toml localmente se existir — não faz nada no Vercel."""
        try:
            from dotenv import load_dotenv
            load_dotenv(".env.local", override=False)
        except Exception:
            pass


config = Config()