"""Unit tests for LoginRateLimiter and IpRateLimiter.

Both limiters are Redis-backed, so these run against fakeredis — no live server
needed, and the Lua scripts are exercised for real rather than mocked away.
"""

import fakeredis
import fakeredis.aioredis
import pytest

from security.rateLimiter import LoginRateLimiter, IpRateLimiter


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
