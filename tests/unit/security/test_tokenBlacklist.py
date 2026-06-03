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
