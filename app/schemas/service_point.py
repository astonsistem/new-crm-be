from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class ServicePointBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None


class ServicePointCreate(ServicePointBase):
    pass


class ServicePointUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None


class ServicePointResponse(ServicePointBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ServicePointListResponse(BaseModel):
    data: List[ServicePointResponse]
    total: int


class ServicePointBriefResponse(BaseModel):
    id: UUID
    name: str
    address: Optional[str] = None

    class Config:
        from_attributes = True
