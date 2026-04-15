from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class AuditLogsBase(BaseModel):
    type: int = Field(..., description="Audit log type (ex: 1 login, 2 password change, etc.)")
    catalist: UUID = Field(..., description="User ID")
    description: str = Field(..., description="Audit log description")
    timestamps: datetime = Field(..., description="Start time")
    
    
class AuditLogsCreate(AuditLogsBase):
    pass


class AuditLogsUpdate(AuditLogsBase):
    type: Optional[int] = Field(None, description="Audit log type (ex: 1 login, 2 password change, etc.)")
    catalist: Optional[UUID] = Field(None, description="User ID")
    description: Optional[str] = Field(None, description="Audit log description")
    timestamps: Optional[datetime] = Field(None, description="Start time")
    
    
class AuditLogsResponse(AuditLogsBase):
    id: UUID
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")
    
    model_config = ConfigDict(from_attributes=True)
        
        
class AuditLogsListResponse(BaseModel):
    auditLogs: list[AuditLogsResponse]
    total: int
