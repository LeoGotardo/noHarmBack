from pydantic import BaseModel, ConfigDict, Field, model_validator
from core.roles import RoleField, publicRole
from schemas.types import Email
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    """
    Schema base for the commun fields of the User.
    """
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: Email = Field(..., description="Valid email address")
    status: int = Field(default=1, description="Account status (ex: 1 enabled, 0 disabled)")

class UserCreate(UserBase):
    """
    Creation schema for a new user.
    All fields are optional here.
    """
    profile_picture: Optional[str] = Field(None, description="Profile picture in binary format")

class UserUpdate(BaseModel):
    """
    Schema for update user.
    All fields are optional here.
    """
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[Email] = None
    status: Optional[int] = None
    profile_picture: Optional[str] = None
    
class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    profile_picture: Optional[str] = None

class UserResponse(UserBase):
    """
    Schema for the client response.
    Has the fields created by the database (ID and timestamps).
    """
    id: str
    profile_picture: Optional[str]
    created_at: datetime
    updated_at: datetime
    role: RoleField = Field(
        None,
        description=(
            "The mark beside the name: `official` for NoHarm's own accounts, "
            "`admin` for moderators, null for everyone else. Derived from the "
            "allowlists on every response; anything a client sends is ignored."
        )
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @model_validator(mode="after")
    def _deriveRole(self):
        self.role = publicRole(self.id)
        return self


class MeResponse(UserResponse):
    """The signed-in account's own profile.

    Separate from `UserResponse` because that one also answers
    `GET /users/{id}` and the directory: whether an account is under a
    moderation sanction is its owner's business and nobody else's. A flag
    visible on a public profile would turn every sanction into a label other
    users could read.
    """
    must_change_username: bool = Field(
        False,
        description=(
            "Moderation reset the username. The account keeps working but the "
            "app asks for a new name before anything else — choosing one is "
            "what lifts it."
        )
    )
    picture_blocked: bool = Field(
        False,
        description=(
            "Moderation removed the profile picture and a new one is refused "
            "until an admin lifts the block."
        )
    )
    pending_consents: list[str] = Field(
        default_factory=list,
        description=(
            "Documents this account owes an answer on — `terms`, `privacy`, "
            "`health_data`. Non-empty means the app shows the consent screen "
            "and nothing else, the same way `must_change_username` does. "
            "Derived server-side from the versions in force, so a client cannot "
            "decide it has already agreed."
        )
    )
    health_data_consent: bool = Field(
        False,
        description=(
            "Whether consent to hold recovery data is currently in force. False "
            "means the streak tracker is off for this account — either never "
            "consented to, or withdrawn."
        )
    )


class SanctionRequest(BaseModel):
    """Why a name or a picture was taken down.

    Shaped like `WarnRequest` on purpose: both write a notice, and the same two
    rules apply — the reason is one of the report codes so the action can be
    traced back to the complaint, and `message` must never name the reporter.
    """
    reason: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "The conduct, as one of the report reason codes. Anything "
            "unrecognised is stored as `other`."
        )
    )
    message: Optional[str] = Field(
        None,
        max_length=500,
        description=(
            "The moderator's own words, shown to the user. Never name the "
            "reporter here."
        )
    )

    model_config = ConfigDict(extra="forbid")


class SanctionResponse(BaseModel):
    """What a moderator gets back after acting on a name or a picture.

    Deliberately not `UserResponse`: an e-mail address is not part of the
    answer to "did the sanction land".
    """
    id: str
    username: str = Field(..., description="The name the account now carries")
    must_change_username: bool = Field(..., description="True while the account owes a new name")
    picture_blocked: bool = Field(..., description="True while the picture is blocked")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserStatsResponse(BaseModel):
    """Public activity numbers for a profile other than your own.

    Visible to friends only: the screen offers "Add to see activity", and a
    streak is recovery data, not a public counter. For everyone else the fields
    come back None and the UI keeps showing its placeholder.
    """
    visible: bool = Field(..., description="False when the viewer is not a friend")
    day_streak: Optional[int] = Field(None, description="Days of the active streak, or 0 when there is none")
    badges_earned: Optional[int] = Field(None, description="How many badges the user holds")


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class SuspendRequest(BaseModel):
    """How long an account is suspended for.

    `days: null` is a permanent ban, and has to be written out — a missing
    field cannot mean "for ever" by accident. The cap lives in
    `MAX_SUSPENSION_DAYS`; the service enforces it, so a change there does not
    need a schema edit.
    """
    days: Optional[int] = Field(
        ...,
        description="Days the suspension lasts; null bans permanently"
    )
    reason: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "The conduct, as one of the report reason codes. It becomes the "
            "suspension notice the user sees; anything unrecognised is stored "
            "as `other`."
        )
    )
    message: Optional[str] = Field(
        None,
        max_length=500,
        description=(
            "The moderator's own words, shown to the suspended user. Never "
            "name the reporter here."
        )
    )

    model_config = ConfigDict(extra="forbid")


class SuspensionResponse(BaseModel):
    """What a moderator gets back after suspending an account.

    Deliberately not `UserResponse`: that carries a username and e-mail, and
    the answer to "is this account banned, until when" needs neither.
    """
    id: str
    status: int = Field(..., description="9 while the ban is in force")
    banned_until: Optional[datetime] = Field(
        None,
        description="When the suspension ends; null when the ban is permanent"
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")
