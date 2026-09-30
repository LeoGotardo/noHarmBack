"""The mark beside a name: derived from the allowlists, never from input."""
from datetime import datetime, timezone

import pytest

from core.config import config


@pytest.fixture
def allowlists():
    admins, officials = list(config.ADMIN_USER_IDS), list(config.OFFICIAL_USER_IDS)
    config.ADMIN_USER_IDS = ["admin-uid", "both-uid"]
    config.OFFICIAL_USER_IDS = ["official-uid", "both-uid"]
    yield
    config.ADMIN_USER_IDS, config.OFFICIAL_USER_IDS = admins, officials


def _user(uid, **extra):
    from schemas.userSchemas import UserResponse
    now = datetime.now(timezone.utc)
    return UserResponse(
        id=uid, username="someone", email="someone@example.com", status=1,
        profile_picture=None, created_at=now, updated_at=now, **extra,
    )


@pytest.mark.parametrize("uid,role", [
    ("admin-uid", "admin"),
    ("official-uid", "official"),
    ("both-uid", "official"),  # the app speaking outranks who runs it
    ("plain-uid", None),
])
def test_role_follows_the_allowlists(allowlists, uid, role):
    assert _user(uid).role == role


def test_a_claimed_role_is_overwritten(allowlists):
    assert _user("plain-uid", role="official").role is None


def test_survives_a_round_trip(allowlists):
    """FastAPI re-validates the dumped model; extra="forbid" must not trip on it."""
    from schemas.userSchemas import UserResponse
    assert UserResponse.model_validate(_user("admin-uid").model_dump()).role == "admin"


def test_me_and_friend_info_carry_it(allowlists):
    from schemas.friendshipSchemas import FriendUserInfo
    from schemas.userSchemas import MeResponse
    assert MeResponse.model_validate(_user("official-uid").model_dump()).role == "official"
    assert FriendUserInfo(id="admin-uid", username="x").role == "admin"
