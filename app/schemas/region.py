from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ProvinceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Province name")


class ProvinceCreate(ProvinceBase):
    pass


class ProvinceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Province name")


class ProvinceResponse(ProvinceBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DistrictBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="District/Regency name")
    province_id: UUID = Field(..., description="Province ID that this district belongs to")


class DistrictCreate(DistrictBase):
    pass


class DistrictUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="District/Regency name")
    province_id: Optional[UUID] = Field(None, description="Province ID that this district belongs to")


class DistrictResponse(DistrictBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    province: Optional[ProvinceResponse] = None

    class Config:
        from_attributes = True


# Response model for province with districts
class ProvinceWithDistrictsResponse(ProvinceResponse):
    districts: List[DistrictResponse] = []

    class Config:
        from_attributes = True