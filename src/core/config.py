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

def _optional(key: str, default: str) -> str:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw

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
            self.EXEC_MODE: str = _require("EXEC_MODE")
            self.DEBUG: bool = _require_bool("DEBUG")
            self.PORT: int = _require_int("PORT")
            self.STATUS_CODES: dict = _require_json("STATUS_CODES")
            self.JWT_SECRET_KEY: str = _require("JWT_SECRET_KEY")
            self.JWT_REFRESH_SECRET_KEY: str = _require("JWT_REFRESH_SECRET_KEY")
            self.JWT_ALGORITHM: str = _require("JWT_ALGORITHM")
            self.ACCESS_TOKEN_EXPIRE_MINUTES: int = _require_int("ACCESS_TOKEN_EXPIRE_MINUTES")
            self.REFRESH_TOKEN_EXPIRE_DAYS: int = _require_int("REFRESH_TOKEN_EXPIRE_DAYS")
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

            # ── consent ───────────────────────────────────────────────────────
            # The version of each document the account is currently asked to
            # accept. A consent record stores the version that was live when it
            # was given, and `ConsentService.pending` compares the two — so
            # bumping one of these is what makes every account re-accept, and
            # nothing else has to change.
            #
            # Strings, not numbers: "1.0" and "2026-09-16" are both reasonable
            # ways to name a revision and the code never does arithmetic on it.
            # Keep them in step with the documents actually served, or the app
            # asks for a signature on a text nobody edited.
            self.TERMS_VERSION: str = _optional("TERMS_VERSION", "1.0")
            self.PRIVACY_VERSION: str = _optional("PRIVACY_VERSION", "1.0")
            # Tracked clean days are health data, and health data needs its own
            # explicit, separately given consent — never one bundled into "I
            # agree to the terms". It carries its own version for the same
            # reason it carries its own checkbox: what it covers can change
            # without the terms changing.
            self.HEALTH_CONSENT_VERSION: str = _optional("HEALTH_CONSENT_VERSION", "1.0")

            # Measured from a fault's last sighting, not its birth: a bug first
            # seen in January and still firing today is current.
            self.ERROR_LOG_RETENTION_DAYS: int = _optional_int("ERROR_LOG_RETENTION_DAYS", 90)

            # Suspicious traffic. Counted per client address, failures only, in
            # a window that refreshes while the burst continues. A flag is a
            # prompt to look and never an action: an automatic block driven by
            # these numbers is a denial of service anyone can aim at a shared
            # mobile NAT.
            self.SUSPICIOUS_WINDOW_SECONDS: int = _optional_int("SUSPICIOUS_WINDOW_SECONDS", 600)
            self.SUSPICIOUS_NOT_FOUND_THRESHOLD: int = _optional_int("SUSPICIOUS_NOT_FOUND_THRESHOLD", 40)
            self.SUSPICIOUS_AUTH_THRESHOLD: int = _optional_int("SUSPICIOUS_AUTH_THRESHOLD", 20)
            self.SUSPICIOUS_SERVER_ERROR_THRESHOLD: int = _optional_int("SUSPICIOUS_SERVER_ERROR_THRESHOLD", 25)
            self.SUSPICIOUS_CLIENT_ERROR_THRESHOLD: int = _optional_int("SUSPICIOUS_CLIENT_ERROR_THRESHOLD", 80)
            self.SUSPICIOUS_MAX_KEYS: int = _optional_int("SUSPICIOUS_MAX_KEYS", 5000)

            # Minimum age to hold an account, in years, checked against the
            # birth date given at registration. Self-declared — no identity
            # provider this app uses carries an age claim (Firebase's ID token
            # does not, and Sign in with Apple has no equivalent), so what this
            # buys is the record that the question was asked and answered, not
            # proof.
            self.MINIMUM_AGE_YEARS: int = _optional_int("MINIMUM_AGE_YEARS", 18)

            # How long the copied evidence behind a report is kept after a
            # moderator closed it. The report itself is permanent — it is the
            # record of what was decided about an account — but the evidence is
            # other people's private messages, copied for one purpose, and
            # keeping it past that purpose is a liability rather than a record.
            # Open reports are never swept, however old: nobody has read them.
            self.REPORT_EVIDENCE_RETENTION_DAYS: int = _optional_int("REPORT_EVIDENCE_RETENTION_DAYS", 180)

            # How long a moderator's claim on a report holds before anyone may
            # take it. An expiring lock is the difference between a queue that
            # heals itself and one that fills with reports parked by someone
            # who closed the tab.
            self.REPORT_LOCK_MINUTES: int = _optional_int("REPORT_LOCK_MINUTES", 30)

            # ── report abuse ceilings ─────────────────────────────────────────
            # Filing a report is free, unauthenticated by anything but a login,
            # and invisible to its target — which is exactly what makes it a
            # harassment tool as well as a safety one. Everything below caps
            # the volume one account can put into the queue, and nothing below
            # ever refuses a *first* report about someone.

            # Per-reporter quota, counted only on reports that were actually
            # filed. The per-IP ceiling on the route is the other half: it stops
            # one host hammering the endpoint, this stops one account filing
            # against a hundred different people from a hundred hosts.
            self.REPORT_MAX_PER_HOUR: int = _optional_int("REPORT_MAX_PER_HOUR", 10)
            self.REPORT_MAX_PER_DAY: int = _optional_int("REPORT_MAX_PER_DAY", 30)

            # How many of one account's reports may sit unreviewed at once.
            # A quota limits the rate; this limits the standing backlog, so a
            # single reporter cannot occupy the queue while moderators work
            # through it.
            self.REPORT_MAX_OPEN: int = _optional_int("REPORT_MAX_OPEN", 5)

            # After a moderator dismisses a report, how long before the same
            # reporter may file about the same person again. Without it,
            # "dismissed" is a round trip: refile, and the queue carries the
            # same complaint for ever. A report that was *actioned* is not
            # cooled down at all — repeat offending is the case you want to
            # hear about again immediately.
            self.REPORT_DISMISSED_COOLDOWN_DAYS: int = _optional_int("REPORT_DISMISSED_COOLDOWN_DAYS", 30)

            # How many open reports by distinct accounts against one user make
            # the queue say "this looks coordinated". A flag for a human, never
            # an automatic action: acting on a count is precisely what a
            # brigade is buying.
            self.REPORT_BRIGADING_THRESHOLD: int = _optional_int("REPORT_BRIGADING_THRESHOLD", 5)

            # Longest suspension `PUT /users/{id}/suspend` will set. Past this
            # the honest action is a permanent ban, chosen deliberately rather
            # than arrived at by typing a large number of days.
            self.MAX_SUSPENSION_DAYS: int = _optional_int("MAX_SUSPENSION_DAYS", 365)

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
