"""Client-IP resolution shared by both rate-limiting layers."""

from unittest.mock import MagicMock, patch

from security.clientIp import extractClientIp


def _request(peer="203.0.113.1", forwarded=None):
    request = MagicMock()
    request.client.host = peer
    request.headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return request


def test_untrusted_peer_ignores_forwarded_header():
    with patch("security.clientIp.isTrustedProxy", lambda ip: False):
        ip = extractClientIp(_request(peer="203.0.113.1", forwarded="1.2.3.4"))
    assert ip == "203.0.113.1"


def test_trusted_peer_returns_rightmost_untrusted_hop():
    trusted = {"10.0.0.1", "10.0.0.2"}
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip in trusted):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="1.2.3.4, 9.9.9.9, 10.0.0.2"))
    assert ip == "9.9.9.9"


def test_trusted_peer_without_header_falls_back_to_peer():
    with patch("security.clientIp.isTrustedProxy", lambda ip: True):
        ip = extractClientIp(_request(peer="10.0.0.1"))
    assert ip == "10.0.0.1"


def test_all_hops_trusted_returns_first():
    with patch("security.clientIp.isTrustedProxy", lambda ip: True):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="10.0.0.5, 10.0.0.6"))
    assert ip == "10.0.0.5"


def test_missing_client_returns_unknown():
    request = MagicMock()
    request.client = None
    request.headers = {}
    with patch("security.clientIp.isTrustedProxy", lambda ip: False):
        assert extractClientIp(request) == "unknown"


def test_both_rate_limit_layers_share_one_extractor():
    """Regression guard.

    slowapi's key_func used to take X-Forwarded-For.split(",")[0] with no proxy
    validation, so the per-route ceilings on register/login were bypassable by
    rotating the header while the global middleware was not. If these two ever
    diverge again, the tight limits silently stop holding.
    """
    from security.limiter import limiter
    from security.middleware import RateLimitMiddleware

    assert limiter._key_func is extractClientIp

    with patch("security.clientIp.isTrustedProxy", lambda ip: False):
        request = _request(peer="203.0.113.9", forwarded="1.2.3.4")
        # Spoofed header, untrusted peer: both layers must key on the peer.
        assert limiter._key_func(request) == "203.0.113.9"
        # _extractIp never touches the wrapped app; a no-op ASGI callable keeps
        # the constructor honest instead of passing None.
        async def _noopApp(scope, receive, send):  # pragma: no cover
            return None

        assert RateLimitMiddleware(app=_noopApp)._extractIp(request) == "203.0.113.9"


# ── isTrustedProxy / _parseTrustedProxies ─────────────────────────────────────
#
# Every test above stubs isTrustedProxy out, so the trust decision itself — the
# part that decides whether a client-controlled header is believed — was never
# executed. TRUST_ALL_PROXIES and TRUSTED_NETWORKS are module globals resolved
# at import from config, so they are patched directly here.

import pytest
from contextlib import contextmanager

import security.clientIp as clientIp


@contextmanager
def _trusted(entries):
    """Reload the trust config from a TRUSTED_PROXIES list."""
    trustAll, networks = clientIp._parseTrustedProxies(entries)
    with patch.object(clientIp, "TRUST_ALL_PROXIES", trustAll), \
         patch.object(clientIp, "TRUSTED_NETWORKS", networks):
        yield


def test_empty_config_trusts_nobody():
    with _trusted([]):
        assert clientIp.isTrustedProxy("10.0.0.1") is False
        assert clientIp.isTrustedProxy("127.0.0.1") is False


def test_wildcard_trusts_every_peer():
    with _trusted(["*"]):
        assert clientIp.isTrustedProxy("203.0.113.9") is True


def test_single_address_is_trusted_exactly():
    with _trusted(["10.0.0.1"]):
        assert clientIp.isTrustedProxy("10.0.0.1") is True
        assert clientIp.isTrustedProxy("10.0.0.2") is False


def test_cidr_range_covers_its_members_only():
    with _trusted(["10.0.0.0/24"]):
        assert clientIp.isTrustedProxy("10.0.0.1") is True
        assert clientIp.isTrustedProxy("10.0.0.255") is True
        assert clientIp.isTrustedProxy("10.0.1.1") is False


def test_multiple_ranges_are_all_honoured():
    with _trusted(["10.0.0.0/24", "192.168.1.0/24"]):
        assert clientIp.isTrustedProxy("10.0.0.5") is True
        assert clientIp.isTrustedProxy("192.168.1.5") is True
        assert clientIp.isTrustedProxy("172.16.0.5") is False


def test_ipv6_range_is_supported():
    with _trusted(["2001:db8::/32"]):
        assert clientIp.isTrustedProxy("2001:db8::1") is True
        assert clientIp.isTrustedProxy("2001:db9::1") is False


def test_none_and_empty_peer_are_never_trusted():
    with _trusted(["*"]):
        assert clientIp.isTrustedProxy(None) is False
        assert clientIp.isTrustedProxy("") is False


def test_non_ip_peer_is_never_trusted():
    """TestClient's peer is the literal string 'testclient'."""
    with _trusted(["10.0.0.0/8"]):
        assert clientIp.isTrustedProxy("testclient") is False
        assert clientIp.isTrustedProxy("not-an-ip") is False


def test_invalid_entries_are_dropped_not_fatal():
    """A typo in TRUSTED_PROXIES must not take the process down, and must not
    silently widen trust either."""
    trustAll, networks = clientIp._parseTrustedProxies(["10.0.0.0/24", "nonsense", ""])
    assert trustAll is False
    assert len(networks) == 1
    with _trusted(["10.0.0.0/24", "nonsense"]):
        assert clientIp.isTrustedProxy("10.0.0.1") is True


def test_entries_are_whitespace_tolerant():
    with _trusted([" 10.0.0.0/24 "]):
        assert clientIp.isTrustedProxy("10.0.0.1") is True


def test_host_bits_in_a_cidr_are_accepted():
    """strict=False — '10.0.0.7/24' is a config style, not an error."""
    trustAll, networks = clientIp._parseTrustedProxies(["10.0.0.7/24"])
    assert len(networks) == 1


def test_none_config_yields_no_trust():
    trustAll, networks = clientIp._parseTrustedProxies(None)
    assert trustAll is False and networks == []


# ── the two pieces together ───────────────────────────────────────────────────

def test_spoofed_header_from_untrusted_peer_is_ignored_end_to_end():
    """No stubbing anywhere: config says trust 10.0.0.0/24, peer is outside it."""
    with _trusted(["10.0.0.0/24"]):
        ip = extractClientIp(_request(peer="203.0.113.9", forwarded="10.0.0.1"))
    assert ip == "203.0.113.9"


def test_real_client_is_read_through_a_trusted_chain_end_to_end():
    with _trusted(["10.0.0.0/24"]):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="198.51.100.7, 10.0.0.2"))
    assert ip == "198.51.100.7"


def test_wildcard_config_believes_the_first_hop():
    """Trusting every proxy means every hop is trusted, so the chain head wins."""
    with _trusted(["*"]):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="198.51.100.7, 10.0.0.2"))
    assert ip == "198.51.100.7"


# ── boot-time warnings ────────────────────────────────────────────────────────
#
# Both extremes of TRUSTED_PROXIES are silent failures, and they fail in
# opposite directions: empty denies service to everyone behind a proxy, `*`
# hands out identity to anyone who asks. The warning is the only thing that
# makes either visible in a boot log.

def test_wildcard_is_announced(caplog):
    clientIp.warnAboutTrustConfig(True, [])
    assert "TRUSTED_PROXIES is '*'" in caplog.text


def test_wildcard_warning_names_its_precondition(caplog):
    """The wildcard is sound only while the perimeter holds. Someone reading
    the log during an incident needs to know what to check — and the thing to
    check is now the bind: uvicorn on loopback is what makes nginx the only
    peer that can reach it."""
    clientIp.warnAboutTrustConfig(True, [])
    assert "bound to loopback" in caplog.text


def test_empty_config_is_announced(caplog):
    clientIp.warnAboutTrustConfig(False, [])
    assert "TRUSTED_PROXIES is empty" in caplog.text


def test_a_scoped_config_warns_about_nothing(caplog):
    import ipaddress
    clientIp.warnAboutTrustConfig(False, [ipaddress.ip_network("10.0.0.0/24")])
    assert caplog.text == ""


def test_wildcard_wins_over_the_empty_network_list(caplog):
    """`["*"]` parses to trustAll with no networks. Reporting that as "empty"
    would describe the opposite of what is configured."""
    clientIp.warnAboutTrustConfig(True, [])
    assert "TRUSTED_PROXIES is empty" not in caplog.text


# --- Hop validation and normalisation -------------------------------------
#
# "Not a trusted proxy" was being read as "is the client", so a hop that was
# not an address at all became the rate-limit key. Rotating junk therefore
# bought a fresh bucket on every request — the same bypass the trusted-proxy
# check exists to prevent, reached from a different direction.


def test_junk_hop_is_skipped_not_returned():
    """A hop that is not an address must never become the bucket key."""
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip == "10.0.0.1"):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="9.9.9.9, AAAA"))
    assert ip == "9.9.9.9"


def test_chain_of_only_junk_falls_back_to_peer():
    """With nothing usable in the header, key on the address the socket saw."""
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip == "10.0.0.1"):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="AAAA, BBBB"))
    assert ip == "10.0.0.1"


def test_rotating_junk_cannot_mint_new_buckets():
    """The whole point: N junk values must not produce N keys."""
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip == "10.0.0.1"):
        keys = {
            extractClientIp(_request(peer="10.0.0.1", forwarded=f"junk-{n}"))
            for n in range(50)
        }
    assert keys == {"10.0.0.1"}


def test_ipv4_mapped_ipv6_keys_the_same_as_plain_ipv4():
    """One host, one bucket — regardless of how it spells itself."""
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip == "10.0.0.1"):
        plain = extractClientIp(_request(peer="10.0.0.1", forwarded="1.2.3.4"))
        mapped = extractClientIp(_request(peer="10.0.0.1", forwarded="::ffff:1.2.3.4"))
    assert plain == mapped == "1.2.3.4"


def test_ipv6_is_returned_in_canonical_form():
    """Compressed and expanded literals are the same address, so one key."""
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip == "10.0.0.1"):
        short = extractClientIp(_request(peer="10.0.0.1", forwarded="2001:db8::1"))
        long = extractClientIp(
            _request(peer="10.0.0.1", forwarded="2001:0db8:0000:0000:0000:0000:0000:0001")
        )
    assert short == long == "2001:db8::1"


def test_bidi_override_does_not_reorder_the_chain():
    """Unicode bidi marks are rendering, not data — the parser reads bytes."""
    with patch("security.clientIp.isTrustedProxy", lambda ip: ip == "10.0.0.1"):
        ip = extractClientIp(_request(peer="10.0.0.1", forwarded="9.9.9.9, ‮1.2.3.4"))
    # The RLO-prefixed hop is not an address, so it is skipped like any junk.
    assert ip == "9.9.9.9"
