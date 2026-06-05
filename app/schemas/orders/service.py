from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.utils.datetime_utils import NaiveDatetime


# Asset Response Schema (nested)
class AssetDetailResponse(BaseModel):
    id: UUID
    asset_name: str
    
    class Config:
        from_attributes = True


# Serial Number Response Schema (nested)
class SerialNumberDetailResponse(BaseModel):
    id: UUID
    serial_code: str
    asset_id: UUID
    status: str
    asset: AssetDetailResponse
    
    class Config:
        from_attributes = True


# Status Service Response Schema (nested)
class StatusServiceResponse(BaseModel):
    id: UUID
    name: str
    
    class Config:
        from_attributes = True


# MOU Response Schema (nested)
class MOUBasicResponse(BaseModel):
    id: UUID
    no_mou: str
    
    class Config:
        from_attributes = True


# User Response Schema (nested)
class UserBasicResponse(BaseModel):
    id: UUID
    username: str
    name: str
    
    class Config:
        from_attributes = True


# MOU Device Response Schema (nested)
class MOUDeviceDetailResponse(BaseModel):
    id: UUID
    status: str
    serial_number: SerialNumberDetailResponse
    
    class Config:
        from_attributes = True


# Service Activity Log Response
class ServiceActivityLogResponse(BaseModel):
    id: UUID
    service_id: UUID
    status: str
    description: Optional[str] = None
    created_at: datetime
    user: Optional[UserBasicResponse] = None

    class Config:
        from_attributes = True


# Order Service Response
class OrderServiceResponse(BaseModel):
    id: UUID
    service_number: str
    mou_id: UUID
    mou_device_id: UUID
    status_service_id: UUID
    description: Optional[str] = None
    service_date: Optional[datetime] = None
    service_date_description: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    created_by: UUID
    service_days: Optional[int] = None
    
    # Nested relationships
    mou: MOUBasicResponse
    status_service: StatusServiceResponse
    mou_device: MOUDeviceDetailResponse
    created_user: UserBasicResponse
    activity_logs: List[ServiceActivityLogResponse] = []
    
    class Config:
        from_attributes = True


# Create Order Service
class OrderServiceCreate(BaseModel):
    mou_id: UUID
    mou_device_id: UUID
    description: Optional[str] = Field(None, max_length=512)


# Schedule Service Request (sales sets service date)
class ServiceScheduleRequest(BaseModel):
    service_date: NaiveDatetime
    service_date_description: Optional[str] = Field(None, max_length=512)


# Process Service Request (sales starts processing service)
class ServiceProcessRequest(BaseModel):
    description: Optional[str] = Field(None, max_length=512)


# Complete Service Request (sales completes service)
class ServiceCompleteRequest(BaseModel):
    description: Optional[str] = Field(None, max_length=512)


# My Customers Services Response (wrapper with total count)
class MyCustomersServicesResponse(BaseModel):
    data: List[OrderServiceResponse]
    total_services: int
