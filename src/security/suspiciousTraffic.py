"""Counts of requests that did not succeed, per client address.

## Why only failures

A counter on every request is a write on every request, and this runs on a
913 MB instance where Postgres already shares memory with Redis and the app. A
counter on every *failure* is a write on a small fraction of them — and the
failures are the whole signal anyway. Nobody scans for `/.env` and gets a 200.

## What it can and cannot see

It answers "one address is producing a lot of a particular kind of refusal",
which catches path scanning, credential probing and a client stuck in a retry
loop. It cannot tell you what they asked for, when, or in what order: there is
no request log here and deliberately so.

**A flag is a prompt to look, never an action.** Nothing here blocks anything —
the rate limiter already does that on its own terms, and an automatic block
driven by these numbers would be a denial-of-service anyone could aim at a
shared mobile NAT by sending rubbish through it.

## Shape

One key per (address, kind), expiring on its own:

    nh:sus:<kind>:<ip>   ->   an integer, TTL SUSPICIOUS_WINDOW_SECONDS

The window is a coarse bucket rather than a sliding one: the question is "is
this happening now", and a sorted set per address to answer it more precisely
would cost more memory than the thing it measures.
"""

import logging
from typing import Optional

import redis

from core.config import config

logger = logging.getLogger(__name__)

_PREFIX = "nh:sus:"

# The kinds worth separating. A 404 flood and a 401 flood are different
# intentions — one is mapping the surface, the other is trying keys — and a
# single "errors" counter would merge them into a number that means neither.
NOT_FOUND = "notfound"
UNAUTHORISED = "auth"
SERVER_ERROR = "server"
OTHER_CLIENT = "client"


def classify(statusCode: int, path: str) -> Optional[str]:
    """Which counter a response belongs to, or None when it is not counted."""
    if statusCode < 400:
        return None
    if statusCode == 404:
        return NOT_FOUND
    if statusCode in (401, 403):
        return UNAUTHORISED
    if statusCode >= 500:
        return SERVER_ERROR
    # 429 is already the rate limiter's own answer and counting it again would
    # double-report the same event under a second name.
    if statusCode == 429:
        return None
    return OTHER_CLIENT


class SuspiciousTraffic:
    """Records refusals and reads back the addresses producing them."""

    def __init__(self, client: Optional[redis.Redis] = None):
        self._redis = client
        if self._redis is None:
            try:
                self._redis = redis.from_url(config.REDIS_URL, decode_responses=True)
            except Exception:
                # No counter is a missing panel. A failed connection here must
                # never be a failed request.
                logger.warning("suspicious traffic counter unavailable", exc_info=True)
                self._redis = None

    def record(self, ip: str, kind: str) -> None:
        """Count one refusal. Never raises, never blocks the response."""
        if self._redis is None or not ip or not kind:
            return
        try:
            key = f"{_PREFIX}{kind}:{ip}"
            pipe = self._redis.pipeline()
            pipe.incr(key)
            # Refreshed on every hit, so the window is "since they stopped"
            # rather than "since they started". A burst that keeps going keeps
            # its count; one that stops ages out on its own.
            pipe.expire(key, config.SUSPICIOUS_WINDOW_SECONDS)
            pipe.execute()
        except Exception:
            logger.warning("could not record suspicious traffic", exc_info=True)

    def flagged(self) -> list[dict]:
        """Addresses past a threshold, worst first.

        Scans the counter keyspace, which is bounded by how many addresses have
        failed inside the window — small by construction, and read once a
        minute behind the board's cache. Capped anyway: a scan that finds tens
        of thousands of keys is itself the thing to report, not a list to
        render.
        """
        if self._redis is None:
            return []

        thresholds = {
            NOT_FOUND: config.SUSPICIOUS_NOT_FOUND_THRESHOLD,
            UNAUTHORISED: config.SUSPICIOUS_AUTH_THRESHOLD,
            SERVER_ERROR: config.SUSPICIOUS_SERVER_ERROR_THRESHOLD,
            OTHER_CLIENT: config.SUSPICIOUS_CLIENT_ERROR_THRESHOLD,
        }

        try:
            byIp: dict[str, dict[str, int]] = {}
            seen = 0

            for key in self._redis.scan_iter(match=f"{_PREFIX}*", count=500):
                seen += 1
                if seen > config.SUSPICIOUS_MAX_KEYS:
                    logger.warning(
                        "suspicious traffic scan stopped at %s keys",
                        config.SUSPICIOUS_MAX_KEYS,
                    )
                    break

                _, _, rest = key.partition(_PREFIX)
                kind, _, ip = rest.partition(":")
                if not kind or not ip:
                    continue

                value = self._redis.get(key)
                if value is None:
                    continue
                byIp.setdefault(ip, {})[kind] = int(value)

            flagged = []
            for ip, counts in byIp.items():
                reasons = [
                    kind
                    for kind, total in counts.items()
                    if total >= thresholds.get(kind, 10**9)
                ]
                if reasons:
                    flagged.append(
                        {"ip": ip, "counts": counts, "reasons": sorted(reasons)}
                    )

            flagged.sort(key=lambda entry: sum(entry["counts"].values()), reverse=True)
            return flagged
        except Exception:
            logger.warning("could not read suspicious traffic", exc_info=True)
            return []
