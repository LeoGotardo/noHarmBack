import pytest
from pydantic import ValidationError
from uuid import uuid4
from datetime import datetime, timezone


class TestAuthSchemas:
    def test_register_valid(self):
        from schemas.authSchemas import AuthRegisterRequest
        r = AuthRegisterRequest(idToken="id-token", username="validuser")
        assert r.idToken == "id-token"
        assert r.username == "validuser"

    def test_register_username_too_short(self):
        from schemas.authSchemas import AuthRegisterRequest
        with pytest.raises(ValidationError):
            AuthRegisterRequest(idToken="id-token", username="ab")

    def test_register_username_too_long(self):
        from schemas.authSchemas import AuthRegisterRequest
        with pytest.raises(ValidationError):
            AuthRegisterRequest(idToken="id-token", username="x" * 51)

    def test_register_missing_id_token(self):
        from schemas.authSchemas import AuthRegisterRequest
        with pytest.raises(ValidationError):
            AuthRegisterRequest(username="user")

    def test_register_ignores_client_supplied_identity(self):
        from schemas.authSchemas import AuthRegisterRequest
        # These four used to be the account's identity. They are read from the
        # token's claims now, so anything sent here is dead weight, not input.
        r = AuthRegisterRequest(
            idToken="id-token", username="validuser",
            uid="someone-else", email="victim@test.com",
            emailVerified=True, photoURL="https://evil",
        )
        assert not hasattr(r, "uid")
        assert not hasattr(r, "emailVerified")

    def test_login_valid(self):
        from schemas.authSchemas import AuthLoginRequest
        r = AuthLoginRequest(idToken="id-token")
        assert r.idToken == "id-token"

    def test_login_missing_id_token(self):
        from schemas.authSchemas import AuthLoginRequest
        with pytest.raises(ValidationError):
            AuthLoginRequest(uid="uid1", email="u@t.com")

    def test_refresh_valid(self):
        from schemas.authSchemas import AuthRefreshRequest
        r = AuthRefreshRequest(refreshToken="tok")
        assert r.refreshToken == "tok"

    def test_refresh_missing_token(self):
        from schemas.authSchemas import AuthRefreshRequest
        with pytest.raises(ValidationError):
            AuthRefreshRequest()

    def test_auth_response_default_token_type(self):
        from schemas.authSchemas import AuthResponse
        r = AuthResponse(accessToken="a", refreshToken="r")
        assert r.tokenType == "Bearer"


class TestUserSchemas:
    def test_user_update_all_optional(self):
        from schemas.userSchemas import UserUpdate
        r = UserUpdate()
        assert r.username is None
        assert r.email is None

    def test_user_update_username_too_short(self):
        from schemas.userSchemas import UserUpdate
        with pytest.raises(ValidationError):
            UserUpdate(username="ab")

    def test_user_update_invalid_email(self):
        from schemas.userSchemas import UserUpdate
        with pytest.raises(ValidationError):
            UserUpdate(email="not-email")

    def test_user_base_valid(self):
        from schemas.userSchemas import UserBase
        r = UserBase(username="validuser", email="u@test.com")
        assert r.status == 1


class TestPaginationSchemas:
    def test_pagination_defaults(self):
        from schemas.paginationSchemas import PaginationParams
        p = PaginationParams()
        assert p.page == 1
        assert p.pageSize == 20

    def test_pagination_page_ge_1(self):
        from schemas.paginationSchemas import PaginationParams
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_pagination_pagesize_le_100(self):
        from schemas.paginationSchemas import PaginationParams
        with pytest.raises(ValidationError):
            PaginationParams(pageSize=101)

    def test_create_paginated_response_math(self):
        from schemas.paginationSchemas import createPaginatedResponse
        r = createPaginatedResponse(items=["a", "b"], total=50, page=2, pageSize=20)
        assert r.totalPages == 3
        assert r.hasNext is True
        assert r.hasPrevious is True
        assert r.page == 2

    def test_create_paginated_first_page(self):
        from schemas.paginationSchemas import createPaginatedResponse
        r = createPaginatedResponse(items=[], total=10, page=1, pageSize=20)
        assert r.hasPrevious is False
        assert r.hasNext is False

    def test_create_paginated_last_page(self):
        from schemas.paginationSchemas import createPaginatedResponse
        r = createPaginatedResponse(items=[], total=40, page=2, pageSize=20)
        assert r.hasNext is False
        assert r.hasPrevious is True

    def test_create_paginated_empty(self):
        from schemas.paginationSchemas import createPaginatedResponse
        r = createPaginatedResponse(items=[], total=0, page=1, pageSize=20)
        assert r.totalPages == 0
        assert r.hasNext is False
        assert r.hasPrevious is False

    def test_calculate_offset(self):
        from schemas.paginationSchemas import calculateOffset
        assert calculateOffset(1, 20) == 0
        assert calculateOffset(2, 20) == 20
        assert calculateOffset(3, 10) == 20


class TestMessageSchemas:
    def test_message_create_valid(self):
        from schemas.messageSchemas import MessageCreate
        r = MessageCreate(chat=uuid4(), sender="abc123XYZ", message="hello")
        assert r.status == 7
        assert r.message == "hello"

    def test_message_create_missing_fields(self):
        from schemas.messageSchemas import MessageCreate
        with pytest.raises(ValidationError):
            MessageCreate(message="hello")


class TestStreakSchemas:
    def test_streak_create_defaults(self):
        from schemas.streakSchemas import StreakCreate
        r = StreakCreate(owner_id="abc123XYZ", start_at=datetime.now(timezone.utc))
        assert r.status == 1
        assert r.is_record is False


class TestFriendshipSchemas:
    def test_friendship_update_all_optional(self):
        from schemas.friendshipSchemas import FriendshipUpdate
        r = FriendshipUpdate(sender="uid-sender", reciver="uid-receiver", sendAt=datetime.now(timezone.utc), recivedAt=datetime.now(timezone.utc))
        assert r.status is None

    def test_friendship_create_required_fields(self):
        from schemas.friendshipSchemas import FriendshipCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FriendshipCreate()

    def test_friendship_create_valid(self):
        from schemas.friendshipSchemas import FriendshipCreate
        now = datetime.now(timezone.utc)
        r = FriendshipCreate(sender="uid-sender", reciver="uid-receiver", sendAt=now, recivedAt=now)
        assert r.status == 1

    def test_friendship_list_response(self):
        from schemas.friendshipSchemas import FriendshipListResponse
        r = FriendshipListResponse(friendships=[], total=0)
        assert r.total == 0


class TestUserSchemasFull:
    def test_user_create_with_picture(self):
        from schemas.userSchemas import UserCreate
        r = UserCreate(username="validuser", email="u@test.com", profile_picture="img_url")
        assert r.profile_picture == "img_url"

    def test_user_list_response(self):
        from schemas.userSchemas import UserListResponse
        r = UserListResponse(users=[], total=0)
        assert r.total == 0

    def test_user_update_valid_email(self):
        from schemas.userSchemas import UserUpdate
        r = UserUpdate(email="new@example.com")
        assert r.email == "new@example.com"

    def test_user_update_status(self):
        from schemas.userSchemas import UserUpdate
        r = UserUpdate(status=2)
        assert r.status == 2


class TestStreakSchemasFull:
    def test_streak_create_with_status(self):
        from schemas.streakSchemas import StreakCreate
        r = StreakCreate(owner_id="abc123XYZ", start_at=datetime.now(timezone.utc), status=1)
        assert r.status == 1

    def test_streak_update_all_optional(self):
        from schemas.streakSchemas import StreakUpdate
        r = StreakUpdate()
        assert r.start_at is None
        assert r.end_at is None
        assert r.last_checkin is None
        assert r.status is None
        assert r.is_record is None

    def test_streak_list_response(self):
        from schemas.streakSchemas import StreakListResponse
        r = StreakListResponse(streaks=[], total=5)
        assert r.total == 5


class TestBadgeSchemas:
    def test_badge_base_required_fields(self):
        from schemas.badgeSchemas import BadgeBase
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BadgeBase()

    def test_badge_base_valid(self):
        from schemas.badgeSchemas import BadgeBase
        now = datetime.now(timezone.utc)
        r = BadgeBase(
            name="First Step",
            description="Achieve 1 day clean",
            milestone=1,
            icon="https://example.com/icon.png",
        )
        assert r.status == 1

    def test_badge_create_does_not_ask_for_timestamps(self):
        """A client cannot know them, and must not be able to choose them."""
        from schemas.badgeSchemas import BadgeCreate
        b = BadgeCreate(
            name="First Step",
            description="Achieve 1 day clean",
            milestone=1,
            icon="https://example.com/icon.png",
        )
        assert not hasattr(b, "created_at")
        assert not hasattr(b, "updated_at")

    def test_badge_update_partial_override(self):
        from schemas.badgeSchemas import BadgeUpdate
        r = BadgeUpdate(icon=b"x")
        assert r.name is None
        assert r.description is None
        assert r.status is None

    def test_badge_name_too_short_raises(self):
        from schemas.badgeSchemas import BadgeBase
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BadgeBase(name="ab", description="ok", milestone=datetime.now(timezone.utc), icon=b"x")

    def test_badge_list_response(self):
        from schemas.badgeSchemas import BadgeListResponse
        r = BadgeListResponse(badges=[], total=0)
        assert r.total == 0


class TestAuditLogSchemas:
    def test_audit_log_base_valid(self):
        from schemas.auditLogsSchemas import AuditLogsBase
        r = AuditLogsBase(
            type=1,
            catalist=uuid4(),
            description="User logged in",
            timestamps=datetime.now(timezone.utc),
        )
        assert r.type == 1

    def test_audit_log_base_missing_fields_raises(self):
        from schemas.auditLogsSchemas import AuditLogsBase
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AuditLogsBase()

    def test_audit_log_update_all_optional(self):
        from schemas.auditLogsSchemas import AuditLogsUpdate
        r = AuditLogsUpdate()
        assert r.type is None
        assert r.description is None

    def test_audit_log_list_response(self):
        from schemas.auditLogsSchemas import AuditLogsListResponse
        r = AuditLogsListResponse(audit_logs=[], total=0)
        assert r.total == 0


class TestChatSchemas:
    def test_chat_base_valid(self):
        from schemas.chatSchemas import ChatBase
        now = datetime.now(timezone.utc)
        r = ChatBase(sender="uid-sender", reciver="uid-receiver", started_at=now, ended_at=now)
        assert r.status == 1

    def test_chat_base_missing_fields_raises(self):
        from schemas.chatSchemas import ChatBase
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ChatBase()

    def test_chat_update_fields_optional(self):
        from schemas.chatSchemas import ChatUpdate
        r = ChatUpdate()
        assert r.ended_at is None
        assert r.status is None

    def test_chat_list_response(self):
        from schemas.chatSchemas import ChatListResponse
        r = ChatListResponse(chats=[], total=3)
        assert r.total == 3
