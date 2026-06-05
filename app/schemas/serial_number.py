from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from enum import Enum


class SerialNumberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SERVICE = "SERVICE"


class AssetDetailResponse(BaseModel):
    id: UUID
    asset_name: str
    asset_type: str
    
    class Config:
        from_attributes = True


class SerialNumberBase(BaseModel):
    serial_code: str = Field(..., max_length=100)
    asset_id: UUID
    status: SerialNumberStatus


class SerialNumberCreate(BaseModel):
    serial_code: str = Field(..., max_length=100)
    asset_id: UUID


class SerialNumberUpdate(BaseModel):
    serial_code: Optional[str] = Field(None, max_length=100)
    asset_id: Optional[UUID] = None
    status: Optional[SerialNumberStatus] = None


class SerialNumberResponse(SerialNumberBase):
    id: UUID
    asset: Optional[AssetDetailResponse] = None

    class Config:
        from_attributes = True
