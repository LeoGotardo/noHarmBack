from datetime import datetime, timedelta, timezone
from typing import Optional


class IpRateLimiter:
    """
    IP-based rate limiter using a sliding window.

    Limits the number of requests per IP within a time window
    and temporarily blocks IPs that exceed the limit.

    Usage:
        limiter = IpRateLimiter()

        allowed, reason = limiter.check("192.168.1.1")
        if not allowed:
            raise HTTPException(429, reason)
    """

    _WINDOW_SECONDS = 60
    _MAX_REQUESTS   = 60
    _BLOCK_MINUTES  = 60


    def __init__(self):
        self._windows: dict[str, list[datetime]] = {}
        self._blocked: dict[str, datetime]       = {}


    # ── Public interface ──────────────────────────────────────────────────────

    def check(self, ip: str) -> tuple[bool, Optional[str]]:
        """
        Checks whether the IP is allowed to make a request.
        Records the attempt internally.

        Args:
            ip: client IP address

        Returns:
            (True, None)       if allowed
            (False, message)   if blocked or limit exceeded
        """
        if self._isBlocked(ip):
            remaining = self._blockedSecondsRemaining(ip)
            return False, f"IP blocked. Try again in {remaining}s"

        self._cleanWindow(ip)
        self._windows.setdefault(ip, []).append(datetime.now(timezone.utc))

        if len(self._windows[ip]) > self._MAX_REQUESTS:
            self._block(ip)
            return False, f"Too many requests. IP blocked for {self._BLOCK_MINUTES} minutes"

        return True, None


    # ── Internal ──────────────────────────────────────────────────────────────

    def _isBlocked(self, ip: str) -> bool:
        if ip not in self._blocked:
            return False

        if datetime.now(timezone.utc) >= self._blocked[ip]:
            del self._blocked[ip]
            return False

        return True


    def _blockedSecondsRemaining(self, ip: str) -> int:
        return int((self._blocked[ip] - datetime.now(timezone.utc)).total_seconds())


    def _block(self, ip: str) -> None:
        self._blocked[ip] = datetime.now(timezone.utc) + timedelta(minutes=self._BLOCK_MINUTES)
        self._windows.pop(ip, None)


    def _cleanWindow(self, ip: str) -> None:
        """Removes timestamps that fall outside the current time window."""
        if ip not in self._windows:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._WINDOW_SECONDS)
        self._windows[ip] = [ts for ts in self._windows[ip] if ts > cutoff]


class LoginRateLimiter:
    """
    Per-username rate limiter for brute-force protection.

    After 5 failed attempts within 15 minutes, the account is locked
    for 30 minutes. Successful attempts clear the attempt history.

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


    def __init__(self):
        self._attempts: dict[str, list[datetime]] = {}
        self._locked:   dict[str, datetime]       = {}


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
        if self._isLocked(username):
            remaining = self._lockedSecondsRemaining(username)
            return False, f"Account locked. Try again in {remaining}s"

        self._cleanWindow(username)
        self._attempts.setdefault(username, []).append(datetime.now(timezone.utc))

        attempts = len(self._attempts[username])

        if attempts >= self._MAX_ATTEMPTS:
            self._lock(username)
            return False, f"Account locked after {self._MAX_ATTEMPTS} attempts. Try again in {self._LOCKOUT_MINUTES} minutes"

        return True, None


    def onSuccess(self, username: str) -> None:
        """
        Clears the attempt history after a successful login.
        Must be called by authService after authenticating the user.

        Args:
            username: account identifier
        """
        self._attempts.pop(username, None)


    def attemptsRemaining(self, username: str) -> int:
        """
        Returns how many attempts remain before lockout.
        Useful for authService to include in error responses.

        Args:
            username: account identifier
        """
        self._cleanWindow(username)
        attempts = len(self._attempts.get(username, []))
        return max(0, self._MAX_ATTEMPTS - attempts)


    # ── Internal ──────────────────────────────────────────────────────────────

    def _isLocked(self, username: str) -> bool:
        if username not in self._locked:
            return False

        if datetime.now(timezone.utc) >= self._locked[username]:
            del self._locked[username]
            self._attempts.pop(username, None)
            return False

        return True


    def _lockedSecondsRemaining(self, username: str) -> int:
        return int((self._locked[username] - datetime.now(timezone.utc)).total_seconds())


    def _lock(self, username: str) -> None:
        self._locked[username] = datetime.now(timezone.utc) + timedelta(minutes=self._LOCKOUT_MINUTES)
        self._attempts.pop(username, None)


    def _cleanWindow(self, username: str) -> None:
        """Removes attempts that fall outside the current time window."""
        if username not in self._attempts:
            return

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._WINDOW_MINUTES)
        self._attempts[username] = [ts for ts in self._attempts[username] if ts > cutoff]