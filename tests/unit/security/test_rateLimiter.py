"""Unit tests for LoginRateLimiter and IpRateLimiter."""

import pytest
from datetime import datetime, timedelta, timezone
from security.rateLimiter import LoginRateLimiter, IpRateLimiter


# ── LoginRateLimiter ──────────────────────────────────────────────────────────

@pytest.fixture
def login_limiter():
    return LoginRateLimiter()


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


def test_login_window_cleanup_removes_old_attempts(login_limiter):
    uid = "user-uid-window"
    # Inject old timestamps directly
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LoginRateLimiter._WINDOW_MINUTES + 1)
    login_limiter._attempts[uid] = [cutoff, cutoff, cutoff]
    # After cleanup, those attempts vanish
    login_limiter._cleanWindow(uid)
    assert len(login_limiter._attempts[uid]) == 0


def test_login_lock_expires_after_window(login_limiter):
    uid = "user-uid-expired-lock"
    # Manually set expired lock
    login_limiter._locked[uid] = datetime.now(timezone.utc) - timedelta(seconds=1)
    # isLocked should auto-clear expired lock
    allowed, _ = login_limiter.check(uid)
    assert allowed is True


# ── IpRateLimiter ─────────────────────────────────────────────────────────────

@pytest.fixture
def ip_limiter():
    return IpRateLimiter()


def test_ip_first_request_allowed(ip_limiter):
    allowed, reason = ip_limiter.check("192.168.1.1")
    assert allowed is True
    assert reason is None


def test_ip_under_limit_allowed(ip_limiter):
    ip = "10.0.0.1"
    for _ in range(IpRateLimiter._MAX_REQUESTS - 1):
        allowed, _ = ip_limiter.check(ip)
        assert allowed is True


def test_ip_over_limit_blocked(ip_limiter):
    ip = "10.0.0.99"
    for _ in range(IpRateLimiter._MAX_REQUESTS + 1):
        ip_limiter.check(ip)
    allowed, reason = ip_limiter.check(ip)
    assert allowed is False


def test_ip_blocked_returns_message(ip_limiter):
    ip = "10.0.1.1"
    # Force block
    ip_limiter._blocked[ip] = datetime.now(timezone.utc) + timedelta(minutes=60)
    allowed, reason = ip_limiter.check(ip)
    assert allowed is False
    assert "blocked" in reason.lower()


def test_ip_block_expires(ip_limiter):
    ip = "10.0.2.1"
    ip_limiter._blocked[ip] = datetime.now(timezone.utc) - timedelta(seconds=1)
    # Expired block → allowed
    allowed, _ = ip_limiter.check(ip)
    assert allowed is True


def test_ip_window_cleanup(ip_limiter):
    ip = "10.0.3.1"
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=IpRateLimiter._WINDOW_SECONDS + 5)
    ip_limiter._windows[ip] = [cutoff] * 10
    ip_limiter._cleanWindow(ip)
    assert len(ip_limiter._windows[ip]) == 0
