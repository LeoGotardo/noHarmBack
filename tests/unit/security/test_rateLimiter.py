"""Unit tests for LoginRateLimiter, IpRateLimiter and ReportQuotaLimiter.

Both limiters are Redis-backed, so these run against fakeredis — no live server
needed, and the Lua scripts are exercised for real rather than mocked away.
"""

import fakeredis
import fakeredis.aioredis
import pytest

from security.rateLimiter import IpRateLimiter, LoginRateLimiter, ReportQuotaLimiter


# ── LoginRateLimiter ──────────────────────────────────────────────────────────

@pytest.fixture
def login_limiter():
    return LoginRateLimiter(client=fakeredis.FakeStrictRedis(decode_responses=True))


def test_login_first_attempt_allowed(login_limiter):
    allowed, reason = login_limiter.check("user@example.com")
    assert allowed is True
    assert reason is None


def test_login_under_limit_allowed(login_limiter):
    uid = "user-uid-1"
    for _ in range(4):
        allowed, _ = login_limiter.check(uid)
        assert allowed is True


def test_login_fifth_attempt_triggers_lockout(login_limiter):
    uid = "user-uid-lockout"
    for _ in range(4):
        login_limiter.check(uid)
    # 5th attempt → lockout
    allowed, reason = login_limiter.check(uid)
    assert allowed is False
    assert reason is not None
    assert "locked" in reason.lower()


def test_login_locked_after_lockout(login_limiter):
    uid = "user-uid-locked"
    for _ in range(5):
        login_limiter.check(uid)
    # Now locked — further attempts blocked
    allowed, reason = login_limiter.check(uid)
    assert allowed is False


def test_login_on_success_clears_attempts(login_limiter):
    uid = "user-uid-clear"
    for _ in range(3):
        login_limiter.check(uid)
    login_limiter.onSuccess(uid)
    # Attempts cleared — should be allowed again
    allowed, _ = login_limiter.check(uid)
    assert allowed is True


def test_login_attempts_remaining_decrements(login_limiter):
    uid = "user-uid-remaining"
    assert login_limiter.attemptsRemaining(uid) == LoginRateLimiter._MAX_ATTEMPTS
    login_limiter.check(uid)
    assert login_limiter.attemptsRemaining(uid) == LoginRateLimiter._MAX_ATTEMPTS - 1


def test_login_lockout_is_shared_between_instances(login_limiter):
    """The whole point of moving to Redis: a second worker sees the same lockout."""
    uid = "user-uid-shared"
    for _ in range(5):
        login_limiter.check(uid)

    otherWorker = LoginRateLimiter(client=login_limiter._redis)
    allowed, _ = otherWorker.check(uid)
    assert allowed is False


def test_login_store_down_fails_open():
    """A blind login limiter must not lock everyone out of the API."""
    class DeadRedis:
        def eval(self, *a, **k):
            raise ConnectionError("redis is down")

    limiter = LoginRateLimiter(client=DeadRedis())
    allowed, reason = limiter.check("user-uid-x")
    assert allowed is True
    assert reason is None


# ── IpRateLimiter ─────────────────────────────────────────────────────────────

_IP_MAX_REQUESTS = 10
_IP_WINDOW_SECONDS = 60
_IP_BLOCK_SECONDS = 60


@pytest.fixture
def ip_limiter():
    return IpRateLimiter(
        windowSeconds=_IP_WINDOW_SECONDS,
        maxRequests=_IP_MAX_REQUESTS,
        blockSeconds=_IP_BLOCK_SECONDS,
        maxBlockSeconds=900,
        client=fakeredis.aioredis.FakeRedis(decode_responses=True),
    )


async def test_ip_first_request_allowed(ip_limiter):
    allowed, reason, retryAfter = await ip_limiter.check("192.168.1.1")
    assert allowed is True
    assert reason is None
    assert retryAfter == 0


async def test_ip_under_limit_allowed(ip_limiter):
    ip = "10.0.0.1"
    for _ in range(_IP_MAX_REQUESTS - 1):
        allowed, _, _ = await ip_limiter.check(ip)
        assert allowed is True


async def test_ip_over_limit_blocked(ip_limiter):
    ip = "10.0.0.99"
    for _ in range(_IP_MAX_REQUESTS + 1):
        await ip_limiter.check(ip)
    allowed, reason, retryAfter = await ip_limiter.check(ip)
    assert allowed is False
    assert retryAfter > 0


async def test_ip_blocked_returns_message(ip_limiter):
    ip = "10.0.1.1"
    for _ in range(_IP_MAX_REQUESTS + 1):
        await ip_limiter.check(ip)

    allowed, reason, retryAfter = await ip_limiter.check(ip)
    assert allowed is False
    assert "blocked" in reason.lower()
    # Retry-After reflects the real remaining block, not a fixed window
    assert retryAfter == _IP_BLOCK_SECONDS


async def test_ip_reset_clears_block(ip_limiter):
    ip = "10.0.2.1"
    for _ in range(_IP_MAX_REQUESTS + 1):
        await ip_limiter.check(ip)
    assert (await ip_limiter.check(ip))[0] is False

    await ip_limiter.reset(ip)
    allowed, _, _ = await ip_limiter.check(ip)
    assert allowed is True


async def test_ip_repeat_offence_escalates_block(ip_limiter):
    ip = "10.0.4.1"

    async def trip():
        for _ in range(_IP_MAX_REQUESTS + 1):
            await ip_limiter.check(ip)
        return (await ip_limiter.check(ip))[2]

    first = await trip()
    # Drop only the block; strikes must survive for escalation to apply.
    await ip_limiter._redis.delete(f"{IpRateLimiter._PREFIX}block:{ip}")
    second = await trip()

    assert second > first


async def test_ip_block_is_capped(ip_limiter):
    """Escalation doubles but must stop at maxBlockSeconds."""
    ip = "10.0.5.1"
    for _ in range(6):
        for _ in range(_IP_MAX_REQUESTS + 1):
            await ip_limiter.check(ip)
        await ip_limiter._redis.delete(f"{IpRateLimiter._PREFIX}block:{ip}")

    for _ in range(_IP_MAX_REQUESTS + 1):
        await ip_limiter.check(ip)
    retryAfter = (await ip_limiter.check(ip))[2]
    assert retryAfter == 900


async def test_ip_buckets_are_isolated_per_ip(ip_limiter):
    """One abusive IP must never block a different one."""
    abuser, bystander = "10.0.6.1", "10.0.6.2"
    for _ in range(_IP_MAX_REQUESTS + 1):
        await ip_limiter.check(abuser)

    assert (await ip_limiter.check(abuser))[0] is False
    assert (await ip_limiter.check(bystander))[0] is True


async def test_ip_state_is_shared_between_instances(ip_limiter):
    """A second serverless instance must see the same window, not a fresh one."""
    ip = "10.0.7.1"
    for _ in range(_IP_MAX_REQUESTS + 1):
        await ip_limiter.check(ip)

    otherInstance = IpRateLimiter(
        windowSeconds=_IP_WINDOW_SECONDS,
        maxRequests=_IP_MAX_REQUESTS,
        blockSeconds=_IP_BLOCK_SECONDS,
        maxBlockSeconds=900,
        client=ip_limiter._redis,
    )
    allowed, _, _ = await otherInstance.check(ip)
    assert allowed is False


async def test_ip_store_down_fails_open():
    """Redis blinking must not turn every request into a 429."""
    class DeadRedis:
        async def eval(self, *a, **k):
            raise ConnectionError("redis is down")

    limiter = IpRateLimiter(client=DeadRedis())
    allowed, reason, retryAfter = await limiter.check("10.0.8.1")
    assert allowed is True
    assert reason is None
    assert retryAfter == 0


# ── ReportQuotaLimiter ────────────────────────────────────────────────────────

_REPORT_HOUR_MAX = 3
_REPORT_DAY_MAX = 5


@pytest.fixture
def report_limiter():
    return ReportQuotaLimiter(
        client=fakeredis.FakeStrictRedis(decode_responses=True),
        shortMax=_REPORT_HOUR_MAX,
        longMax=_REPORT_DAY_MAX,
    )


def test_report_first_filing_allowed(report_limiter):
    allowed, reason = report_limiter.check("uid-1")
    assert allowed is True
    assert reason is None


def test_report_checking_does_not_spend(report_limiter):
    """Checking is free — otherwise every refused request costs the user a unit."""
    for _ in range(20):
        allowed, _ = report_limiter.check("uid-1")
        assert allowed is True

    assert report_limiter.remaining("uid-1") == (_REPORT_HOUR_MAX, _REPORT_DAY_MAX)


def test_report_hourly_ceiling_refuses_the_next_one(report_limiter):
    for _ in range(_REPORT_HOUR_MAX):
        assert report_limiter.check("uid-1")[0] is True
        report_limiter.spend("uid-1")

    allowed, reason = report_limiter.check("uid-1")
    assert allowed is False
    assert reason is not None
    assert "hour" in reason


def test_report_daily_ceiling_refuses_past_the_hourly_one(report_limiter):
    """Spend the day's allowance without the hour ever filling up.

    Only the hourly zset is rolled forward, so each burst starts a fresh hour
    while the day's tally keeps accumulating — which is the drip an hourly cap
    alone would never catch.
    """
    redis = report_limiter._redis

    for _ in range(2):
        for _ in range(_REPORT_HOUR_MAX):
            report_limiter.spend("uid-1")
        redis.delete("rl:report:hour:uid-1")

    allowed, reason = report_limiter.check("uid-1")
    assert allowed is False
    assert reason is not None
    assert "day" in reason


def test_report_quota_is_per_account(report_limiter):
    for _ in range(_REPORT_HOUR_MAX):
        report_limiter.spend("uid-1")

    assert report_limiter.check("uid-1")[0] is False
    assert report_limiter.check("uid-2")[0] is True


def test_report_remaining_counts_down_with_spending(report_limiter):
    report_limiter.spend("uid-1")
    report_limiter.spend("uid-1")

    assert report_limiter.remaining("uid-1") == (_REPORT_HOUR_MAX - 2, _REPORT_DAY_MAX - 2)


def test_report_refusal_says_when_the_window_frees_up(report_limiter):
    for _ in range(_REPORT_HOUR_MAX):
        report_limiter.spend("uid-1")

    _, reason = report_limiter.check("uid-1")
    assert reason is not None
    assert "Try again in" in reason


def test_report_quota_is_shared_between_instances(report_limiter):
    """Two app instances must not each hand out a full allowance."""
    other = ReportQuotaLimiter(
        client=report_limiter._redis,
        shortMax=_REPORT_HOUR_MAX,
        longMax=_REPORT_DAY_MAX,
    )

    for _ in range(_REPORT_HOUR_MAX):
        report_limiter.spend("uid-1")

    assert other.check("uid-1")[0] is False


def test_report_store_down_fails_open():
    """Redis blinking must not stop someone reporting harassment."""
    class DeadRedis:
        def eval(self, *a, **k):
            raise ConnectionError("redis is down")

    limiter = ReportQuotaLimiter(client=DeadRedis())
    allowed, reason = limiter.check("uid-1")
    assert allowed is True
    assert reason is None


def test_report_spend_swallows_a_dead_store():
    """The report is already filed; losing its accounting must not raise."""
    class DeadRedis:
        def eval(self, *a, **k):
            raise ConnectionError("redis is down")

    ReportQuotaLimiter(client=DeadRedis()).spend("uid-1")
