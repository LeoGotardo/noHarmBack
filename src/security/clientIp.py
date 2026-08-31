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

Every value that leaves this module is a parsed address in canonical form, and
a hop that is not an address is skipped rather than returned. The two rules
close the same hole from opposite sides: without the first, one host spells
itself `1.2.3.4` and `::ffff:1.2.3.4` for two buckets; without the second, a
hop of `AAAA` becomes the bucket key, so rotating junk means a fresh bucket per
request. Neither is reachable while the proxy overwrites the header
(`proxy_set_header X-Forwarded-For $remote_addr`, never
`$proxy_add_x_forwarded_for`) — that is the perimeter, and this is the layer
that survives it being misconfigured.
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
        # `*` believes X-Forwarded-For from any peer, so it is only sound while
        # something else guarantees the request came from our own proxy. Here
        # that guarantee is the network: nginx runs beside this process and
        # uvicorn binds 127.0.0.1, so nothing else can connect. Naming the
        # loopback addresses says the same thing and keeps saying it if the
        # bind ever widens — which is why `*` is not the recommended value even
        # though it is currently equivalent. Get the bind wrong with `*` set
        # and the wildcard silently becomes a full rate-limit bypass: no code
        # change, no deploy, no failing test. Logged so the dependency is
        # visible in the boot log of every instance.
        logger.warning(
            "TRUSTED_PROXIES is '*': X-Forwarded-For is believed from any peer. "
            "This is only safe while the backend is unreachable except through "
            "the proxy. Verify uvicorn is bound to loopback."
        )
        return

    if not networks:
        # Deployed behind any proxy (nginx, the Docker compose bridge) this
        # makes every client share the proxy's bucket, so one caller can
        # rate-limit everyone. Loud on purpose: it looks like a global ban, not
        # a config gap.
        logger.warning(
            "TRUSTED_PROXIES is empty: rate limiting keys on the direct peer. "
            "Behind a proxy, all clients share a single bucket."
        )


TRUST_ALL_PROXIES, TRUSTED_NETWORKS = _parseTrustedProxies(config.TRUSTED_PROXIES)

warnAboutTrustConfig(TRUST_ALL_PROXIES, TRUSTED_NETWORKS)


def _parseIp(value: str | None):
    """Parse an address, or None if it is not one.

    IPv4-mapped IPv6 (`::ffff:1.2.3.4`) is unwrapped to its IPv4 form. Two
    reasons, and both are silent failures without it:

    - As a *key*, `1.2.3.4` and `::ffff:1.2.3.4` are one host with two
      rate-limit buckets. Same for a compressed vs expanded IPv6 literal, which
      `str()` on the parsed address settles.
    - As a *peer*, a dual-stack listener reports the proxy as
      `::ffff:127.0.0.1`, which matches no IPv4 network — so the proxy stops
      being trusted and every client collapses into its single bucket.
    """
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def isTrustedProxy(ip: str | None) -> bool:
    if not ip:
        return False
    if TRUST_ALL_PROXIES:
        return True
    if not TRUSTED_NETWORKS:
        return False
    address = _parseIp(ip)
    if address is None:
        return False
    return any(address in network for network in TRUSTED_NETWORKS)


def extractClientIp(request: Request) -> str:
    """Resolve the client IP for rate-limiting purposes."""
    peer = request.client.host if request.client else None
    peerAddress = _parseIp(peer)
    peerKey = str(peerAddress) if peerAddress else "unknown"

    if not isTrustedProxy(peer):
        return peerKey

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return peerKey

    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if isTrustedProxy(hop):
            continue
        # "not a trusted proxy" is not the same as "is the client". Anything
        # that is not an address at all is skipped rather than returned:
        # returning it made the header's content the rate-limit key, so a
        # caller rotating garbage got a fresh bucket on every request.
        address = _parseIp(hop)
        if address is not None:
            return str(address)

    # Every hop is a trusted proxy: the request started inside the perimeter,
    # and the leftmost hop is the closest thing to an origin it has.
    origin = _parseIp(hops[0]) if hops else None
    return str(origin) if origin else peerKey
