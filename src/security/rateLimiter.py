"""Redis-backed rate limiters.

`IpRateLimiter` is the global floor, `LoginRateLimiter` the brute-force lockout
on an account, and `ReportQuotaLimiter` the ceiling on how much one account can
put into the moderation queue.

The first two used to hold their state in process memory, which assumed a single
long-lived process. That stopped being true on serverless: every instance kept
its own counters and a cold start wiped them, so the login lockout — the one
control that must not be volatile — was effectively per-instance.

State now lives in Redis, shared across instances, in the same style the
WebSocket limiter already used. Each check is a single Lua script so the
read-decide-write cycle is atomic: two concurrent requests cannot both observe
"under the limit" and both pass, nor double-count a strike.

Redis being unreachable fails *open* (request allowed, warning logged). A rate
limiter that 500s the API when its store blinks causes a worse outage than the
abuse it prevents.
"""

import logging
import time
import uuid

from typing import Any, Optional, cast

import redis
import redis.asyncio as aioredis

from core.config import config

logger = logging.getLogger(__name__)


# ── shared clients ────────────────────────────────────────────────────────────

_asyncRedis: aioredis.Redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)  # type: ignore[assignment]
_syncRedis: redis.Redis = redis.from_url(config.REDIS_URL, decode_responses=True)  # type: ignore[assignment]


# ── Lua ───────────────────────────────────────────────────────────────────────

# Sliding window + escalating block.
#   KEYS: 1=window zset  2=block key  3=strikes key
#   ARGV: 1=now_ms 2=window_ms 3=maxRequests 4=blockSeconds 5=maxBlockSeconds
#         6=strikesTtlSeconds 7=unique member
# Returns: {allowed, retryAfterSeconds}
_SLIDING_WINDOW_LUA = """
local blockTtl = redis.call('TTL', KEYS[2])
if blockTtl > 0 then
    return {0, blockTtl}
end

local now      = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local maxReq   = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - windowMs)
redis.call('ZADD', KEYS[1], now, ARGV[7])
redis.call('PEXPIRE', KEYS[1], windowMs)

local count = redis.call('ZCARD', KEYS[1])
if count > maxReq then
    local strikes = redis.call('INCR', KEYS[3])
    redis.call('EXPIRE', KEYS[3], tonumber(ARGV[6]))

    local blockFor = tonumber(ARGV[4]) * math.pow(2, strikes - 1)
    local maxBlock = tonumber(ARGV[5])
    if blockFor > maxBlock then
        blockFor = maxBlock
    end
    blockFor = math.floor(blockFor)

    redis.call('SET', KEYS[2], '1', 'EX', blockFor)
    redis.call('DEL', KEYS[1])
    return {0, blockFor}
end

return {1, 0}
"""

# Fixed lockout after N failures inside a sliding window.
#   KEYS: 1=attempts zset  2=lock key
#   ARGV: 1=now_ms 2=window_ms 3=maxAttempts 4=lockoutSeconds 5=unique member
# Returns: {allowed, retryAfterSeconds}
_LOCKOUT_LUA = """
local lockTtl = redis.call('TTL', KEYS[2])
if lockTtl > 0 then
    return {0, lockTtl}
end

local now      = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local maxTries = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - windowMs)
redis.call('ZADD', KEYS[1], now, ARGV[5])
redis.call('PEXPIRE', KEYS[1], windowMs)

local count = redis.call('ZCARD', KEYS[1])
if count >= maxTries then
    local lockFor = tonumber(ARGV[4])
    redis.call('SET', KEYS[2], '1', 'EX', lockFor)
    redis.call('DEL', KEYS[1])
    return {0, lockFor}
end

return {1, 0}
"""


# Two-window quota, read-only. Nothing is recorded here: a quota that is spent
# by *asking* would be spent by the duplicate check, the unknown-user 404 and
# every other refusal below it, so the caller records separately once the thing
# being limited actually happened.
#   KEYS: 1=short zset  2=long zset
#   ARGV: 1=now_ms 2=shortMs 3=shortMax 4=longMs 5=longMax
# Returns: {allowed, retryAfterSeconds, scope}   scope: '' | 'short' | 'long'
_QUOTA_PEEK_LUA = """
local now = tonumber(ARGV[1])

local function used(key, windowMs)
    redis.call('ZREMRANGEBYSCORE', key, 0, now - windowMs)
    return redis.call('ZCARD', key)
end

local function waitFor(key, windowMs)
    -- The window frees up when its oldest entry falls out of it.
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if oldest[2] == nil then
        return 1
    end
    local wait = math.ceil((tonumber(oldest[2]) + windowMs - now) / 1000)
    if wait < 1 then
        wait = 1
    end
    return wait
end

if used(KEYS[1], tonumber(ARGV[2])) >= tonumber(ARGV[3]) then
    return {0, waitFor(KEYS[1], tonumber(ARGV[2])), 'short'}
end

if used(KEYS[2], tonumber(ARGV[4])) >= tonumber(ARGV[5]) then
    return {0, waitFor(KEYS[2], tonumber(ARGV[4])), 'long'}
end

return {1, 0, ''}
"""

# The other half of the quota: spend one unit in both windows at once.
#   KEYS: 1=short zset  2=long zset
#   ARGV: 1=now_ms 2=shortMs 3=longMs 4=unique member
_QUOTA_SPEND_LUA = """
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[4])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
redis.call('ZADD', KEYS[2], tonumber(ARGV[1]), ARGV[4])
redis.call('PEXPIRE', KEYS[2], tonumber(ARGV[3]))
return 1
"""


async def _evalAsync(client: aioredis.Redis, script: str, numkeys: int, *args: str) -> list[Any]:
    """Run a Lua script and return its reply.

    redis-py declares `eval(self, script, numkeys, *keys_and_args: list)`, which
    is wrong twice over: each vararg is a single key or value rather than a
    list, and the return is typed `Awaitable[str] | str` for the sync and the
    async client alike. Every call site therefore reported "str is not
    awaitable" plus one error per argument. Both scripts here return a two-item
    array, so the contract is stated once here instead of scattering ignores
    across a dozen argument lines.
    """
    return await client.eval(script, numkeys, *args)  # type: ignore[misc]


def _evalSync(client: redis.Redis, script: str, numkeys: int, *args: str) -> list[Any]:
    """Sync counterpart of _evalAsync — same redis-py annotation problem."""
    return cast(list, client.eval(script, numkeys, *args))  # type: ignore[arg-type]


def _nowMs() -> int:
    return int(time.time() * 1000)


def _member() -> str:
    """Unique zset member — two requests in the same millisecond must both count."""
    return f"{_nowMs()}-{uuid.uuid4().hex[:12]}"


class IpRateLimiter:
    """
    IP-based rate limiter using a sliding window, shared through Redis.

    Acts as a coarse floor for abusive traffic — the tight ceilings live in the
    per-route slowapi limits. A single app screen costs ~10 requests, so the
    window has to leave room for normal navigation, and shared NAT egress means
    several users can sit behind one IP.

    Blocking is proportional: the first breach costs `RATE_LIMIT_BLOCK_SECONDS`,
    and repeated breaches double it up to `RATE_LIMIT_MAX_BLOCK_SECONDS`.

    Usage:
        limiter = IpRateLimiter()

        allowed, reason, retryAfter = await limiter.check("192.168.1.1")
        if not allowed:
            raise HTTPException(429, reason)
    """

    _PREFIX = "rl:ip:"
    _STRIKES_TTL_SECONDS = 86400

    def __init__(
        self,
        windowSeconds: Optional[int] = None,
        maxRequests: Optional[int] = None,
        blockSeconds: Optional[int] = None,
        maxBlockSeconds: Optional[int] = None,
        client: Optional[aioredis.Redis] = None,
    ):
        self._windowSeconds   = windowSeconds   or config.RATE_LIMIT_WINDOW_SECONDS
        self._maxRequests     = maxRequests     or config.RATE_LIMIT_MAX_REQUESTS
        self._blockSeconds    = blockSeconds    or config.RATE_LIMIT_BLOCK_SECONDS
        self._maxBlockSeconds = maxBlockSeconds or config.RATE_LIMIT_MAX_BLOCK_SECONDS
        self._redis           = client or _asyncRedis


    # ── Public interface ──────────────────────────────────────────────────────

    async def check(self, ip: str) -> tuple[bool, Optional[str], int]:
        """
        Checks whether the IP is allowed to make a request.
        Records the attempt internally.

        Args:
            ip: client IP address

        Returns:
            (True, None, 0)                  if allowed
            (False, message, retryAfter)     if blocked or limit exceeded
        """
        try:
            allowed, retryAfter = await _evalAsync(
                self._redis,
                _SLIDING_WINDOW_LUA,
                3,
                f"{self._PREFIX}win:{ip}",
                f"{self._PREFIX}block:{ip}",
                f"{self._PREFIX}strikes:{ip}",
                str(_nowMs()),
                str(self._windowSeconds * 1000),
                str(self._maxRequests),
                str(self._blockSeconds),
                str(self._maxBlockSeconds),
                str(self._STRIKES_TTL_SECONDS),
                _member(),
            )
        except Exception:
            logger.exception("rate limit store unreachable — allowing request for %s", ip)
            return True, None, 0

        if int(allowed) == 1:
            return True, None, 0

        retryAfter = max(1, int(retryAfter))
        return False, f"IP blocked. Try again in {retryAfter}s", retryAfter


    async def reset(self, ip: str) -> None:
        """Clear every counter for an IP. Used by tests and admin tooling."""
        try:
            await self._redis.delete(
                f"{self._PREFIX}win:{ip}",
                f"{self._PREFIX}block:{ip}",
                f"{self._PREFIX}strikes:{ip}",
            )
        except Exception:
            logger.exception("could not reset rate limit state for %s", ip)


class LoginRateLimiter:
    """
    Per-account rate limiter for brute-force protection, shared through Redis.

    After 5 failed attempts within 15 minutes the account is locked for 30
    minutes. Successful attempts clear the attempt history.

    Synchronous on purpose: authService runs in Starlette's threadpool, not on
    the event loop.

    Usage:
        limiter = LoginRateLimiter()

        allowed, reason = limiter.check(username)
        if not allowed:
            raise HTTPException(429, reason)

        # after authenticating successfully:
        limiter.onSuccess(username)
    """

    _WINDOW_MINUTES  = 15
    _MAX_ATTEMPTS    = 5
    _LOCKOUT_MINUTES = 30

    _PREFIX = "rl:login:"


    def __init__(self, client: Optional[redis.Redis] = None):
        self._redis = client or _syncRedis


    # ── Public interface ──────────────────────────────────────────────────────

    def check(self, username: str) -> tuple[bool, Optional[str]]:
        """
        Checks whether the username is allowed to attempt login.
        Records the attempt internally.

        Args:
            username: account identifier (email or username)

        Returns:
            (True, None)       if allowed
            (False, message)   if account is locked or limit exceeded
        """
        try:
            allowed, retryAfter = _evalSync(
                self._redis,
                _LOCKOUT_LUA,
                2,
                f"{self._PREFIX}attempts:{username}",
                f"{self._PREFIX}lock:{username}",
                str(_nowMs()),
                str(self._WINDOW_MINUTES * 60 * 1000),
                str(self._MAX_ATTEMPTS),
                str(self._LOCKOUT_MINUTES * 60),
                _member(),
            )
        except Exception:
            logger.exception("login limit store unreachable — allowing attempt for %s", username)
            return True, None

        if int(allowed) == 1:
            return True, None

        return False, (
            f"Account locked after {self._MAX_ATTEMPTS} attempts. "
            f"Try again in {max(1, int(retryAfter))}s"
        )


    def onSuccess(self, username: str) -> None:
        """
        Clears the attempt history after a successful login.
        Must be called by authService after authenticating the user.

        Args:
            username: account identifier
        """
        try:
            self._redis.delete(f"{self._PREFIX}attempts:{username}")
        except Exception:
            logger.exception("could not clear login attempts for %s", username)


    def attemptsRemaining(self, username: str) -> int:
        """
        Returns how many attempts remain before lockout.
        Useful for authService to include in error responses.

        Args:
            username: account identifier
        """
        key = f"{self._PREFIX}attempts:{username}"
        cutoff = _nowMs() - self._WINDOW_MINUTES * 60 * 1000
        try:
            self._redis.zremrangebyscore(key, 0, cutoff)
            used = cast(int, self._redis.zcard(key))
        except Exception:
            logger.exception("could not read login attempts for %s", username)
            return self._MAX_ATTEMPTS

        return max(0, self._MAX_ATTEMPTS - int(used))


class ReportQuotaLimiter:
    """Per-account ceiling on how many reports one user may file.

    The route already carries `@limiter.limit("5/minute")`, but that is keyed on
    the client IP. One account filing against a different person every twelve
    seconds never trips it, and a reporter behind a shared NAT trips it because
    of strangers. This limiter is keyed on the reporter's UID, which is the
    thing being rationed.

    Two windows rather than one. An hourly cap alone permits 240 reports a day
    at a steady drip; a daily cap alone permits the whole day's allowance in one
    burst. Both together bound the burst and the total.

    **Check and spend are separate calls on purpose.** `check` reads; `spend` is
    called only once a report has actually been created. A user who is told
    "you already reported this person" has learned something the app should have
    known, and charging them for it is punishing the wrong side. Requests that
    are refused before that point are the per-IP limiter's problem, not this
    one's.

    The split means two concurrent filings can both observe the last unit free
    and both spend it. On a quota measured in tens per hour, being off by one is
    not worth an in-flight reservation and the refund path it would need.

    Synchronous, like `LoginRateLimiter`: the service runs in Starlette's
    threadpool.

    Usage:
        limiter = ReportQuotaLimiter()

        allowed, reason = limiter.check(reporterId)
        if not allowed:
            raise NoHarmException(429, reason)

        # ... after the report row exists:
        limiter.spend(reporterId)
    """

    _PREFIX = "rl:report:"

    def __init__(
        self,
        client: Optional[redis.Redis] = None,
        shortMax: Optional[int] = None,
        longMax: Optional[int] = None,
    ):
        self._redis = client or _syncRedis
        self._shortWindowMs = 60 * 60 * 1000
        self._longWindowMs = 24 * 60 * 60 * 1000
        self._shortMax = shortMax or config.REPORT_MAX_PER_HOUR
        self._longMax = longMax or config.REPORT_MAX_PER_DAY

    # ── Public interface ──────────────────────────────────────────────────────

    def check(self, reporterId: str) -> tuple[bool, Optional[str]]:
        """Whether this account may file another report right now.

        Records nothing — see the class docstring.

        Returns:
            (True, None)     when there is room in both windows
            (False, message) naming which window is full and when it frees up
        """
        try:
            allowed, retryAfter, scope = _evalSync(
                self._redis,
                _QUOTA_PEEK_LUA,
                2,
                f"{self._PREFIX}hour:{reporterId}",
                f"{self._PREFIX}day:{reporterId}",
                str(_nowMs()),
                str(self._shortWindowMs),
                str(self._shortMax),
                str(self._longWindowMs),
                str(self._longMax),
            )
        except Exception:
            # Same posture as every other limiter here: a store that blinks must
            # not stop people reporting harassment.
            logger.exception("report quota store unreachable — allowing report by %s", reporterId)
            return True, None

        if int(allowed) == 1:
            return True, None

        window = "hour" if scope == "short" else "day"
        limit = self._shortMax if scope == "short" else self._longMax

        return False, (
            f"You have filed {limit} reports in the last {window}. "
            f"Try again in {max(1, int(retryAfter))}s."
        )

    def spend(self, reporterId: str) -> None:
        """Charge one report against both windows. Call only once one was filed."""
        try:
            _evalSync(
                self._redis,
                _QUOTA_SPEND_LUA,
                2,
                f"{self._PREFIX}hour:{reporterId}",
                f"{self._PREFIX}day:{reporterId}",
                str(_nowMs()),
                str(self._shortWindowMs),
                str(self._longWindowMs),
                _member(),
            )
        except Exception:
            # The report is already filed. Losing the accounting for it is worth
            # less than raising over it.
            logger.exception("could not record report quota for %s", reporterId)

    def remaining(self, reporterId: str) -> tuple[int, int]:
        """(hour, day) allowance left — for a client that wants to say so."""
        now = _nowMs()
        out = []
        for key, windowMs, maximum in (
            (f"{self._PREFIX}hour:{reporterId}", self._shortWindowMs, self._shortMax),
            (f"{self._PREFIX}day:{reporterId}", self._longWindowMs, self._longMax),
        ):
            try:
                self._redis.zremrangebyscore(key, 0, now - windowMs)
                used = cast(int, self._redis.zcard(key))
            except Exception:
                logger.exception("could not read report quota for %s", reporterId)
                used = 0
            out.append(max(0, maximum - int(used)))

        return out[0], out[1]


# One window, read-only — the single-window sibling of _QUOTA_PEEK_LUA.
#   KEYS: 1=zset
#   ARGV: 1=now_ms 2=windowMs 3=max
# Returns: {allowed, retryAfterSeconds}
_DAILY_PEEK_LUA = """
local now = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - windowMs)
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[3]) then
    return {1, 0}
end

local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local wait = 1
if oldest[2] ~= nil then
    wait = math.ceil((tonumber(oldest[2]) + windowMs - now) / 1000)
    if wait < 1 then
        wait = 1
    end
end
return {0, wait}
"""

#   KEYS: 1=zset   ARGV: 1=now_ms 2=windowMs 3=unique member
_DAILY_SPEND_LUA = """
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[3])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""


class ContentQuotaLimiter:
    """Per-account daily ceiling on posts, or on comments — one instance each.

    The same reasoning as `ReportQuotaLimiter`: the per-route limits key on the
    client IP, which one account on many networks never trips and a shared
    mobile NAT trips because of strangers. This keys on the account.

    One 24-hour window rather than two. What it protects is everybody else's
    feed from one account, and the per-minute route limits already bound the
    burst; a second, hourly window would only be a second number to explain.

    Check and spend are separate, and spend is called only once the row
    exists, for the reason given on `ReportQuotaLimiter`.
    """

    _PREFIX = "rl:content:"

    def __init__(self, kind: str, maximum: int, client: Optional[redis.Redis] = None):
        self._redis = client or _syncRedis
        self._kind = kind
        self._windowMs = 24 * 60 * 60 * 1000
        self._max = maximum

    def _key(self, userId: str) -> str:
        return f"{self._PREFIX}{self._kind}:{userId}"

    def check(self, userId: str) -> tuple[bool, int]:
        """(allowed, seconds until a unit frees up). Records nothing."""
        try:
            allowed, retryAfter = _evalSync(
                self._redis,
                _DAILY_PEEK_LUA,
                1,
                self._key(userId),
                str(_nowMs()),
                str(self._windowMs),
                str(self._max),
            )
        except Exception:
            logger.exception("%s quota store unreachable — allowing %s", self._kind, userId)
            return True, 0

        if int(allowed) == 1:
            return True, 0

        return False, max(1, int(retryAfter))

    def spend(self, userId: str) -> None:
        """Charge one unit. Call only once the post or comment was written."""
        try:
            _evalSync(
                self._redis,
                _DAILY_SPEND_LUA,
                1,
                self._key(userId),
                str(_nowMs()),
                str(self._windowMs),
                _member(),
            )
        except Exception:
            logger.exception("could not record %s quota for %s", self._kind, userId)
