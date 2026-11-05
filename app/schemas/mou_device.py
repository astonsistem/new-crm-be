from datetime import datetime

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

from app.utils.datetime_utils import OptionalNaiveDatetime


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
    customer_pic: Optional[str] = None
    customer_pic_phone: Optional[str] = None
    customer_phone: Optional[str] = None

    class Config:
        from_attributes = True


# MOU Device Schemas
class MOUDeviceBase(BaseModel):
    mou_id: UUID
    serial_number_id: UUID


class MOUDeviceCreate(BaseModel):
    serial_number_id: UUID
    location: str
    installation_date: OptionalNaiveDatetime = Field(
        None,
        description="Tanggal pemasangan di lokasi customer (opsional, bisa diisi belakangan)",
    )


class MOUDeviceUpdate(BaseModel):
    mou_id: Optional[UUID] = None
    serial_number_id: Optional[UUID] = None
    location: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None
    installation_date: OptionalNaiveDatetime = Field(
        None,
        description="Tanggal pemasangan di lokasi customer",
    )


class MOUDeviceResponse(MOUDeviceBase):
    id: UUID
    status: str
    mou: Optional[MOUBasicResponse] = None
    serial_number: Optional[SerialNumberDetailResponse] = None
    location: Optional[str] = None
    installation_date: Optional[datetime] = None
    
    class Config:
        from_attributes = True
