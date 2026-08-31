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

def _optional_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default

def _optional_json(key: str, default):
    raw = os.environ.get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default

try:
    import tomllib
    _toml_path = os.path.join(os.path.dirname(__file__), "..", "..", ".secrets.toml")
    _enviroment = os.environ.get("APP_ENV", 'prod')
    
    if os.path.exists(_toml_path):
        with open(_toml_path, "rb") as f:
            _toml = tomllib.load(f)
            
        _toml_default = _toml.get("default", {})
        _toml_enviroment = _toml.get(_enviroment, {})
        
        _toml = {**_toml_default, **_toml_enviroment}
        
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
            self.DATABASE_ENCRYPTION_KEY: str = _require("DATABASE_ENCRYPTION_KEY")
            # Optional, and read by nothing today: file uploads and profile
            # pictures are still unimplemented (`storageService.py` holds the
            # declarative Base and no storage code). They were `_require`d,
            # which meant every deployment had to invent a value for a service
            # that does not exist yet — a dummy string in the task definition
            # standing in for configuration. They become required again on the
            # day something reads them.
            self.STORAGE_SERVICE_URI: str = os.environ.get("STORAGE_SERVICE_URI", "")
            self.STORAGE_SERVICE_KEY: str = os.environ.get("STORAGE_SERVICE_KEY", "")
            self.EXEC_MODE: str = _require("EXEC_MODE")
            self.DEBUG: bool = _require_bool("DEBUG")
            self.PORT: int = _require_int("PORT")
            self.STATUS_CODES: dict = _require_json("STATUS_CODES")
            self.JWT_SECRET_KEY: str = _require("JWT_SECRET_KEY")
            self.JWT_REFRESH_SECRET_KEY: str = _require("JWT_REFRESH_SECRET_KEY")
            self.JWT_ALGORITHM: str = _require("JWT_ALGORITHM")
            self.ACCESS_TOKEN_EXPIRE_MINUTES: int = _require_int("ACCESS_TOKEN_EXPIRE_MINUTES")
            self.REFRESH_TOKEN_EXPIRE_DAYS: int = _require_int("REFRESH_TOKEN_EXPIRE_DAYS")
            # Where `security/persistentHashTable.py` would write its
            # append-only log. Nothing imports that module: the JWT blacklist
            # lives in Redis (`security/tokenBlacklist.py`), which is what makes
            # revocation work across more than one instance. Kept with a default
            # rather than removed, so the module still has a path if it is ever
            # wired back in.
            self.STORAGE_PATH: str = os.environ.get("STORAGE_PATH", "tmp/blacklist.jsonl")
            self.ALLOWED_ORIGINS: list = _require_json("ALLOWED_ORIGINS")
            self.REDIS_URL: str = _require("REDIS_URL")
            self.FIREBASE_SERVICE_ACCOUNT: str | None = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
            self.FIREBASE_SERVICE_ACCOUNT_PATH: str | None = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH")
            # Only needed when there is no service account to read it from —
            # i.e. the emulator path used by the test suites. Verification
            # matches the token's "aud" and "iss" against this.
            self.FIREBASE_PROJECT_ID: str | None = os.environ.get("FIREBASE_PROJECT_ID")

            self.IS_DEV: bool = self.EXEC_MODE.lower() in ("dev", "development")

            # Peers allowed to set X-Forwarded-For. Plain IPs or CIDR blocks.
            # Deployed, this is the loopback pair and nothing else: nginx runs
            # beside the app in the container and uvicorn binds 127.0.0.1, so
            # the proxy is the only peer that can ever appear.
            # ["*"] trusts every peer and is a full rate-limit bypass unless
            # something outside this process guarantees the request came from
            # our own proxy. Prefer naming the loopback addresses.
            self.TRUSTED_PROXIES: list = _optional_json("TRUSTED_PROXIES", [])

            # Global IP floor. Per-route slowapi limits are the real ceilings.
            self.RATE_LIMIT_MAX_REQUESTS: int = _optional_int("RATE_LIMIT_MAX_REQUESTS", 240)
            self.RATE_LIMIT_WINDOW_SECONDS: int = _optional_int("RATE_LIMIT_WINDOW_SECONDS", 60)
            self.RATE_LIMIT_BLOCK_SECONDS: int = _optional_int("RATE_LIMIT_BLOCK_SECONDS", 60)
            self.RATE_LIMIT_MAX_BLOCK_SECONDS: int = _optional_int("RATE_LIMIT_MAX_BLOCK_SECONDS", 900)
        except Exception as e:
            # Mirrors the _require calls above — the storage keys are absent
            # from both, deliberately.
            missing = [k for k in ["ENCRYPTION_KEY","DATABASE_URL","DATABASE_HOST","DATABASE_NAME","DATABASE_USER","DATABASE_PASSWORD","DATABASE_URL_UNPOOLED","DATABASE_ENCRYPTION_KEY","EXEC_MODE","DEBUG","PORT","STATUS_CODES","JWT_SECRET_KEY","JWT_REFRESH_SECRET_KEY","JWT_ALGORITHM","ACCESS_TOKEN_EXPIRE_MINUTES","REFRESH_TOKEN_EXPIRE_DAYS","ALLOWED_ORIGINS","REDIS_URL"] if not os.environ.get(k)]
            raise Exception(f"Configuration error: {e} | Missing keys: {missing}")

config = Config()
