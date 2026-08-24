"""Shared slowapi limiter — the per-route ceilings.

Two things used to be wrong here and both are corrected:

1. The key function trusted `X-Forwarded-For` blindly, so the tight limits on
   register/login were bypassable by rotating the header. It now uses the same
   `extractClientIp` as the global middleware, which validates the proxy chain.
2. Storage defaulted to `MemoryStorage`, which on serverless means one counter
   per instance, reset on every cold start. It is now Redis-backed, so the
   ceilings hold across instances.
"""

import logging

from slowapi import Limiter

from core.config import config
from security.clientIp import extractClientIp

logger = logging.getLogger(__name__)


def _buildLimiter() -> Limiter:
    """Redis-backed limiter, falling back to per-process memory if Redis is down.

    A rate limiter that cannot reach its store must not take the API down with
    it: degrading to a local counter still limits abuse, just not across
    instances.
    """
    try:
        limiterInstance = Limiter(key_func=extractClientIp, storage_uri=config.REDIS_URL)
        # slowapi/limits connect lazily — force it so a bad URL surfaces here
        # instead of on the first request.
        limiterInstance.limiter.storage.check()
        return limiterInstance
    except Exception:
        logger.exception(
            "per-route rate limiting could not reach Redis at startup; "
            "falling back to in-memory storage (limits become per-instance)"
        )
        return Limiter(key_func=extractClientIp)


limiter = _buildLimiter()
