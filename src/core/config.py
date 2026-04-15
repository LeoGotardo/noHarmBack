import os
import json
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise Exception(f"Missing required env var: {key}")
    return val

def _require_int(key: str) -> int:
    return int(_require(key))

def _require_bool(key: str) -> bool:
    return _require(key).lower() in ("true", "1", "yes")

def _require_json(key: str):
    raw = _require(key)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise Exception(f"Env var {key} is not valid JSON: {e}")

# Load .secrets.toml for local development (overrides nothing if already in env)
try:
    import tomllib
    _toml_path = os.path.join(os.path.dirname(__file__), "..", "..", ".secrets.toml")
    if os.path.exists(_toml_path):
        with open(_toml_path, "rb") as f:
            _toml = tomllib.load(f)
        for k, v in _toml.items():
            if k.upper() not in os.environ:
                if isinstance(v, (dict, list)):
                    os.environ[k.upper()] = json.dumps(v)
                else:
                    os.environ[k.upper()] = str(v)
except Exception:
    pass


class Config:
    def __init__(self):
        try:
            self.ENCRYPTION_KEY: str = _require("ENCRYPTION_KEY")
            self.DATABASE_URL: str = _require("DATABASE_URL")
            self.DATABASE_HOST: str = _require("DATABASE_HOST")
            self.DATABASE_NAME: str = _require("DATABASE_NAME")
            self.DATABASE_USER: str = _require("DATABASE_USER")
            self.DATABASE_PASSWORD: str = _require("DATABASE_PASSWORD")
            self.DATABASE_URL_UNPOOLED: str = _require("DATABASE_URL_UNPOOLED")
            self.STORAGE_SERVICE_URI: str = _require("STORAGE_SERVICE_URI")
            self.STORAGE_SERVICE_KEY: str = _require("STORAGE_SERVICE_KEY")
            self.EXEC_MODE: str = _require("EXEC_MODE")
            self.DEBUG: bool = _require_bool("DEBUG")
            self.PORT: int = _require_int("PORT")
            self.STATUS_CODES: dict = _require_json("STATUS_CODES")
            self.JWT_SECRET_KEY: str = _require("JWT_SECRET_KEY")
            self.JWT_REFRESH_SECRET_KEY: str = _require("JWT_REFRESH_SECRET_KEY")
            self.JWT_ALGORITHM: str = _require("JWT_ALGORITHM")
            self.ACCESS_TOKEN_EXPIRE_MINUTES: int = _require_int("ACCESS_TOKEN_EXPIRE_MINUTES")
            self.REFRESH_TOKEN_EXPIRE_DAYS: int = _require_int("REFRESH_TOKEN_EXPIRE_DAYS")
            self.STORAGE_PATH: str = _require("STORAGE_PATH")
            self.ALLOWED_ORIGINS: list = _require_json("ALLOWED_ORIGINS")
        except Exception as e:
            missing = [k for k in ["ENCRYPTION_KEY","DATABASE_URL","DATABASE_HOST","DATABASE_NAME","DATABASE_USER","DATABASE_PASSWORD","DATABASE_URL_UNPOOLED","STORAGE_SERVICE_URI","STORAGE_SERVICE_KEY","EXEC_MODE","DEBUG","PORT","STATUS_CODES","JWT_SECRET_KEY","JWT_REFRESH_SECRET_KEY","JWT_ALGORITHM","ACCESS_TOKEN_EXPIRE_MINUTES","REFRESH_TOKEN_EXPIRE_DAYS","STORAGE_PATH","ALLOWED_ORIGINS"] if not os.environ.get(k)]
            raise Exception(f"Configuration error: {e} | Missing keys: {missing}")

config = Config()
