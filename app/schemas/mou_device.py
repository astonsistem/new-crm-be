from pydantic import BaseModel
from typing import Optional
from uuid import UUID


# Nested schemas for response
class AssetDetailResponse(BaseModel):
    id: UUID
    asset_name: str
    asset_type: str
    
    class Config:
        from_attributes = True


class SerialNumberDetailResponse(BaseModel):
    id: UUID
    serial_code: str
    asset_id: UUID
    status: str
    asset: Optional[AssetDetailResponse] = None
    
    class Config:
        from_attributes = True


class MOUBasicResponse(BaseModel):
    id: UUID
    no_mou: str
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# MOU Device Schemas
class MOUDeviceBase(BaseModel):
    mou_id: UUID
    serial_number_id: UUID


class MOUDeviceCreate(BaseModel):
    serial_number_id: UUID
    location: str


class MOUDeviceUpdate(BaseModel):
    mou_id: Optional[UUID] = None
    serial_number_id: Optional[UUID] = None
    status: Optional[str] = None


class MOUDeviceResponse(MOUDeviceBase):
    id: UUID
    status: str
    mou: Optional[MOUBasicResponse] = None
    serial_number: Optional[SerialNumberDetailResponse] = None
    location: Optional[str] = None
    
    class Config:
        from_attributes = True
