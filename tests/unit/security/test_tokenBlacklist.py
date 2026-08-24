import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


@pytest.fixture
def mock_redis_client():
    return MagicMock()


@pytest.fixture
def blacklist(mock_redis_client):
    with patch("security.tokenBlacklist.redis") as mock_redis_mod:
        mock_redis_mod.from_url.return_value = mock_redis_client
        from security.tokenBlacklist import TokenBlacklist
        bl = TokenBlacklist()
    return bl


class TestTokenBlacklist:
    def test_add_valid_ttl_calls_setex(self, blacklist, mock_redis_client):
        future =datetime.now(timezone.utc) + timedelta(seconds=300)
        blacklist.add("test-jti", future)
        mock_redis_client.setex.assert_called_once()
        key, ttl, val = mock_redis_client.setex.call_args[0]
        assert key.startswith("jti:")
        assert ttl > 0
        assert val == "1"

    def test_add_past_expiry_does_not_call_setex(self, blacklist, mock_redis_client):
        past =datetime.now(timezone.utc) - timedelta(seconds=10)
        blacklist.add("test-jti", past)
        mock_redis_client.setex.assert_not_called()

    def test_add_uses_hashed_jti_as_key(self, blacklist, mock_redis_client):
        future =datetime.now(timezone.utc) + timedelta(seconds=60)
        blacklist.add("my-jti", future)
        key_used = mock_redis_client.setex.call_args[0][0]
        expected_hash = blacklist._hash("my-jti")
        assert key_used == f"jti:{expected_hash}"

    def test_isBlacklisted_true_when_redis_exists_returns_1(self, blacklist, mock_redis_client):
        mock_redis_client.exists.return_value = 1
        assert blacklist.isBlacklisted("some-jti") is True

    def test_isBlacklisted_false_when_redis_exists_returns_0(self, blacklist, mock_redis_client):
        mock_redis_client.exists.return_value = 0
        assert blacklist.isBlacklisted("some-jti") is False

    def test_isBlacklisted_checks_hashed_key(self, blacklist, mock_redis_client):
        mock_redis_client.exists.return_value = 0
        blacklist.isBlacklisted("my-jti")
        expected_key = "jti:" + blacklist._hash("my-jti")
        mock_redis_client.exists.assert_called_once_with(expected_key)

    def test_different_jtis_produce_different_hashes(self, blacklist):
        assert blacklist._hash("jti-1") != blacklist._hash("jti-2")

    def test_same_jti_always_produces_same_hash(self, blacklist):
        assert blacklist._hash("abc") == blacklist._hash("abc")

    def test_add_zero_ttl_does_not_call_setex(self, blacklist, mock_redis_client):
        exactly_now =datetime.now(timezone.utc)
        blacklist.add("test-jti", exactly_now)
        mock_redis_client.setex.assert_not_called()

    def test_add_stores_value_one(self, blacklist, mock_redis_client):
        future =datetime.now(timezone.utc) + timedelta(hours=1)
        blacklist.add("jti", future)
        val = mock_redis_client.setex.call_args[0][2]
        assert val == "1"


class TestTokenBlacklistOverRealRedis:
    """The tests above drive a MagicMock, so they check the calls but never the
    round trip: `isBlacklisted` returns whatever the test told `exists` to
    return. fakeredis makes add → isBlacklisted an actual read-back, and covers
    the naive-datetime branch that `JwtHandler.revokeToken` always takes."""

    @pytest.fixture
    def blacklist(self):
        import fakeredis
        from security.tokenBlacklist import TokenBlacklist
        bl = TokenBlacklist.__new__(TokenBlacklist)
        bl._redis = fakeredis.FakeStrictRedis(decode_responses=True)
        return bl

    def test_added_jti_reads_back_as_blacklisted(self, blacklist):
        blacklist.add("jti-abc", datetime.now(timezone.utc) + timedelta(minutes=15))
        assert blacklist.isBlacklisted("jti-abc") is True

    def test_unknown_jti_is_not_blacklisted(self, blacklist):
        blacklist.add("jti-abc", datetime.now(timezone.utc) + timedelta(minutes=15))
        assert blacklist.isBlacklisted("jti-other") is False

    def test_expired_entry_is_never_written(self, blacklist):
        blacklist.add("jti-old", datetime.now(timezone.utc) - timedelta(minutes=1))
        assert blacklist.isBlacklisted("jti-old") is False

    def test_naive_expiry_is_treated_as_utc(self, blacklist):
        """JwtHandler.revokeToken strips tzinfo before calling add. Without the
        naive branch tagging it UTC, the subtraction under a non-UTC local clock
        would produce a wrong (often negative) TTL and revocation would silently
        do nothing."""
        naive = (datetime.now(timezone.utc) + timedelta(minutes=15)).replace(tzinfo=None)
        blacklist.add("jti-naive", naive)
        assert blacklist.isBlacklisted("jti-naive") is True

    def test_ttl_tracks_the_expiry_that_was_passed(self, blacklist):
        blacklist.add("jti-ttl", datetime.now(timezone.utc) + timedelta(seconds=600))
        ttl = blacklist._redis.ttl("jti:" + blacklist._hash("jti-ttl"))
        assert 590 <= ttl <= 600

    def test_entry_is_stored_under_the_hash_not_the_raw_jti(self, blacklist):
        """The raw JTI must not be recoverable from a dump of the store."""
        blacklist.add("jti-secret", datetime.now(timezone.utc) + timedelta(minutes=15))
        keys = blacklist._redis.keys("*")
        assert keys == ["jti:" + blacklist._hash("jti-secret")]
        assert "jti-secret" not in keys[0]
