from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import date


class AuthRegisterRequest(BaseModel):
    # Identity comes from the token, never from the body: `uid`, `email` and
    # `emailVerified` used to be client-supplied, which made both invented
    # accounts and a bypass of email verification a matter of typing.
    idToken: str = Field(..., description="Firebase ID token from the sign-in flow")
    username: str = Field(..., min_length=3, max_length=50, description="Username (alphanumeric, _ and - only)")
    birthDate: date = Field(
        ...,
        description=(
            "Date of birth, self-declared. The account is refused below "
            "MINIMUM_AGE_YEARS. No identity provider this app uses carries an "
            "age claim, so this is what the user typed — what it buys is the "
            "record that the question was asked, not proof."
        )
    )
    # Three separate answers, not one "I agree". The terms and the privacy
    # policy are a condition of having an account; consent to hold recovery
    # data is a condition of the tracker and nothing else, and has to be
    # askable, refusable and withdrawable on its own.
    acceptedTerms: bool = Field(
        ...,
        description="The user accepted the terms of use. Registration is refused without it."
    )
    acceptedPrivacy: bool = Field(
        ...,
        description="The user accepted the privacy policy. Registration is refused without it."
    )
    healthDataConsent: bool = Field(
        False,
        description=(
            "Explicit consent to hold streak data, which is health data. "
            "Optional: declining creates the account without the tracker, and "
            "it can be given or taken back later from the app."
        )
    )


class AuthLoginRequest(BaseModel):
    idToken: str = Field(..., description="Firebase ID token from the sign-in flow")


class AuthReactivateRequest(BaseModel):
    # Same proof as login: the caller has to hold a Firebase ID token for the
    # UID being restored. The UID itself is public — it shows up in friend
    # lists and search — so accepting one in the body would let anyone undo
    # anyone else's deletion.
    idToken: str = Field(..., description="Firebase ID token for the account being restored")


class AuthRefreshRequest(BaseModel):
    refreshToken: str = Field(..., description="Valid refresh token")


class AuthResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "Bearer"

    model_config = ConfigDict(from_attributes=True, extra="forbid")
