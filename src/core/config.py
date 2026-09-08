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
            # Key for the blind indexes (`cl_0b_h`, `cl_0c_h`, `cl_9c_h`) — the
            # lookup columns that make an encrypted username/email/FCM token
            # searchable by exact match.
            #
            # It has to be a *separate* secret from DATABASE_ENCRYPTION_KEY, and
            # the reason is the whole point of the column: an attacker who reads
            # the database holds the ciphertext and the index side by side. With
            # an unkeyed digest the index is the weaker of the two by a wide
            # margin — a wordlist of e-mail addresses recovers the column
            # outright, and a username matching ^[a-zA-Z0-9_-]{3,30}$ falls to
            # plain enumeration. Keying it means the index is worth nothing
            # without a secret the database never holds.
            #
            # Storing it beside the encryption key would undo that the moment
            # both leak together, which for a single Secrets Manager entry is
            # the only way they leak at all — but they are separate values, so a
            # future split (index key in the app, column key in a KMS) stays
            # possible without a re-hash.
            #
            # Rotating it requires re-running the 20260902_01 migration: every
            # stored index has to be recomputed or every lookup misses.
            self.BLIND_INDEX_KEY: str = _require("BLIND_INDEX_KEY")
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

            # Deleting an account is a soft delete plus a clock: the row is
            # kept for this many days so the user can sign in again and undo
            # it, and `purge-accounts` destroys it for good once the window
            # closes. The window is disclosed in the delete confirmation UI —
            # undisclosed retention is the thing users object to, not the
            # window itself. Setting this to 0 makes the purge eligible
            # immediately, which is a hard delete on the next cron run.
            self.ACCOUNT_DELETION_GRACE_DAYS: int = _optional_int("ACCOUNT_DELETION_GRACE_DAYS", 30)

            # UIDs allowed to call the admin endpoints — today that is
            # `PUT /users/{id}/status/{status}`, which can ban, unban and
            # undelete anyone. There is no role column and no admin UI, so an
            # allowlist is the whole authorisation model. Empty (the default)
            # means nobody can reach those routes, which is the right posture
            # for an environment that has no administrators.
            self.ADMIN_USER_IDS: list = _optional_json("ADMIN_USER_IDS", [])

            # Global IP floor. Per-route slowapi limits are the real ceilings.
            self.RATE_LIMIT_MAX_REQUESTS: int = _optional_int("RATE_LIMIT_MAX_REQUESTS", 240)
            self.RATE_LIMIT_WINDOW_SECONDS: int = _optional_int("RATE_LIMIT_WINDOW_SECONDS", 60)
            self.RATE_LIMIT_BLOCK_SECONDS: int = _optional_int("RATE_LIMIT_BLOCK_SECONDS", 60)
            self.RATE_LIMIT_MAX_BLOCK_SECONDS: int = _optional_int("RATE_LIMIT_MAX_BLOCK_SECONDS", 900)
        except Exception as e:
            # Mirrors the _require calls above — the storage keys are absent
            # from both, deliberately.
            missing = [k for k in ["ENCRYPTION_KEY","DATABASE_URL","DATABASE_HOST","DATABASE_NAME","DATABASE_USER","DATABASE_PASSWORD","DATABASE_URL_UNPOOLED","DATABASE_ENCRYPTION_KEY","BLIND_INDEX_KEY","EXEC_MODE","DEBUG","PORT","STATUS_CODES","JWT_SECRET_KEY","JWT_REFRESH_SECRET_KEY","JWT_ALGORITHM","ACCESS_TOKEN_EXPIRE_MINUTES","REFRESH_TOKEN_EXPIRE_DAYS","ALLOWED_ORIGINS","REDIS_URL"] if not os.environ.get(k)]
            raise Exception(f"Configuration error: {e} | Missing keys: {missing}")

config = Config()
