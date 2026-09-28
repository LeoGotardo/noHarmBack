from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from datetime import datetime


# The closed set. `health_data` is one of them rather than a flag on the user
# because a streak is health data and that consent has to be separately given
# and separately withdrawable — see ConsentService.
ConsentDocument = Literal["terms", "privacy", "health_data"]


class ConsentAcceptRequest(BaseModel):
    """Which documents the user just agreed to.

    Deliberately no `version` field. The server stamps the version that is
    live at the moment of writing: a client able to name the version it was
    agreeing to could record agreement to a text it never showed anyone, which
    is the one statement a consent record must not be able to make.
    """
    documents: list[ConsentDocument] = Field(
        ...,
        min_length=1,
        description="Documents being accepted, at whatever version is current."
    )

    model_config = ConfigDict(extra="forbid")


class ConsentRecord(BaseModel):
    """One act of agreeing, as stored."""
    document: str
    version: str = Field(..., description="The revision that was live when it was given")
    accepted_at: datetime
    withdrawn_at: Optional[datetime] = Field(
        None,
        description="When it was taken back. The record survives the withdrawal."
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ConsentStatusResponse(BaseModel):
    versions: dict[str, str] = Field(
        ...,
        description="The version of each document an account is asked to accept today"
    )
    consents: list[ConsentRecord] = Field(
        ...,
        description="Everything this account ever agreed to, oldest first, withdrawals included"
    )
    pending: list[str] = Field(
        ...,
        description=(
            "Documents owed an answer. Non-empty means the app shows the consent "
            "screen and nothing else. Health data appears here only when an "
            "active consent has gone out of date — never given and withdrawn are "
            "both answers."
        )
    )
    health_data_consent: bool = Field(
        ...,
        description="Whether consent to hold recovery data is currently in force"
    )

    model_config = ConfigDict(extra="forbid")


class ConsentWithdrawResponse(BaseModel):
    """What happened when health-data consent was taken back."""
    withdrawn: bool = Field(
        ...,
        description="False when there was nothing in force to withdraw"
    )
    streaks_deleted: int = Field(
        ...,
        description=(
            "How many streaks were destroyed with it — all of them, history and "
            "personal record included. There is no grace window: a shadow copy "
            "of data someone asked to be rid of is the thing they asked to be "
            "rid of."
        )
    )

    model_config = ConfigDict(extra="forbid")
