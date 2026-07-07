from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class ServicePointBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    pic_name: Optional[str] = Field(None, max_length=100, description="Person in Charge name")
    pic_phone: Optional[str] = Field(None, max_length=20, description="Person in Charge phone")
    user_id: Optional[UUID] = Field(None, description="Assigned user ID")

    @field_validator("pic_name", "pic_phone", mode="before")
    @classmethod
    def normalize_optional_text(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class ServicePointCreate(ServicePointBase):
    pass


class ServicePointUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None
    pic_name: Optional[str] = Field(None, max_length=100, description="Person in Charge name")
    pic_phone: Optional[str] = Field(None, max_length=20, description="Person in Charge phone")
    user_id: Optional[UUID] = Field(None, description="Assigned user ID")

    @field_validator("pic_name", "pic_phone", mode="before")
    @classmethod
    def normalize_optional_text(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class ServicePointResponse(ServicePointBase):
    id: UUID
    user_name: Optional[str] = Field(None, description="Name from linked user")
    user_phone: Optional[str] = Field(None, description="Phone from linked user")
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
    pic_name: Optional[str] = None
    pic_phone: Optional[str] = None
    user_id: Optional[UUID] = None
    user_name: Optional[str] = None
    user_phone: Optional[str] = None

    class Config:
        from_attributes = True
