"""Single source of truth for "which client is this request from?".

Both rate-limiting layers key on the client IP, and they used to disagree: the
global middleware validated the proxy chain while slowapi's key_func took
`X-Forwarded-For.split(",")[0]` unconditionally. A spoofed header therefore
still bought a fresh bucket on the per-route ceilings — the tight ones guarding
register and login. Both now call `extractClientIp`.

X-Forwarded-For is client-controlled unless the peer is a proxy we trust, so an
untrusted peer is keyed by its own address. Trusted peers are read
right-to-left: the rightmost hop that is not itself a trusted proxy is the real
client.
"""

import ipaddress
import logging

from fastapi import Request

from core.config import config

logger = logging.getLogger(__name__)


def _parseTrustedProxies(entries) -> tuple[bool, list]:
    """Return (trustAll, networks) from the configured TRUSTED_PROXIES list."""
    trustAll = False
    networks = []
    for entry in entries or []:
        text = str(entry).strip()
        if text == "*":
            trustAll = True
            continue
        try:
            networks.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            logger.warning("ignoring invalid TRUSTED_PROXIES entry: %r", entry)
    return trustAll, networks


def warnAboutTrustConfig(trustAll: bool, networks: list) -> None:
    """Log whichever way the proxy-trust config is dangerous.

    Both extremes are silent failures without this, and they fail in opposite
    directions — one denies service, the other forges identity — so neither is
    a safe default to leave unannounced.
    """
    if trustAll:
        # `*` believes X-Forwarded-For from any peer. That is only sound while
        # something else guarantees the request came from our own proxy —
        # Vercel Deployment Protection with Trusted Sources. Turn that off and
        # the wildcard silently becomes a full rate-limit bypass: no code
        # change, no deploy, no failing test. Logged so the dependency is
        # visible in the boot log of every instance.
        logger.warning(
            "TRUSTED_PROXIES is '*': X-Forwarded-For is believed from any peer. "
            "This is only safe while the backend is unreachable except through "
            "the proxy. Verify Deployment Protection is enabled."
        )
        return

    if not networks:
        # Deployed behind any proxy (Docker bridge, Vercel edge, nginx) this
        # makes every client share the proxy's bucket, so one caller can
        # rate-limit everyone. Loud on purpose: it looks like a global ban, not
        # a config gap.
        logger.warning(
            "TRUSTED_PROXIES is empty: rate limiting keys on the direct peer. "
            "Behind a proxy, all clients share a single bucket."
        )


TRUST_ALL_PROXIES, TRUSTED_NETWORKS = _parseTrustedProxies(config.TRUSTED_PROXIES)

warnAboutTrustConfig(TRUST_ALL_PROXIES, TRUSTED_NETWORKS)


def isTrustedProxy(ip: str | None) -> bool:
    if not ip:
        return False
    if TRUST_ALL_PROXIES:
        return True
    if not TRUSTED_NETWORKS:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in TRUSTED_NETWORKS)


def extractClientIp(request: Request) -> str:
    """Resolve the client IP for rate-limiting purposes."""
    peer = request.client.host if request.client else None

    if not isTrustedProxy(peer):
        return peer or "unknown"

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return peer or "unknown"

    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not isTrustedProxy(hop):
            return hop

    return hops[0] if hops else (peer or "unknown")
