from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class AssetBase(BaseModel):
    asset_name: str = Field(..., max_length=150)
    asset_type: str = Field(..., max_length=50)
    category_id: UUID


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    asset_name: Optional[str] = Field(None, max_length=150)
    asset_type: Optional[str] = Field(None, max_length=50)
    category_id: Optional[UUID] = None


class AssetResponse(AssetBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    category_name: Optional[str] = None
    serial_number_count: int = 0

    class Config:
        from_attributes = True
