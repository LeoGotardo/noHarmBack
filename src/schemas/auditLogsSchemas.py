from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class AuditLogsBase(BaseModel):
    type: int = Field(..., description="Audit log type (ex: 1 login, 2 password change, etc.)")
    catalyst_id: Optional[UUID] = Field(None, description="User ID of the catalyst")
    catalyst: Optional[int] = Field(None, description="Catalyst action code")
    description: str = Field(..., description="Audit log description")


class AuditLogsCreate(AuditLogsBase):
    pass


class AuditLogsUpdate(BaseModel):
    type: Optional[int] = Field(None, description="Audit log type (ex: 1 login, 2 password change, etc.)")
    catalyst_id: Optional[UUID] = Field(None, description="User ID of the catalyst")
    catalyst: Optional[int] = Field(None, description="Catalyst action code")
    description: Optional[str] = Field(None, description="Audit log description")


class AuditLogsResponse(AuditLogsBase):
    id: UUID
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AuditLogsListResponse(BaseModel):
    audit_logs: list[AuditLogsResponse]
    total: int
