from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# Auth Schemas
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# User Schemas
class UserBase(BaseModel):
    name: str
    username: str
    phone: Optional[str] = Field(None, max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    role_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    
    @field_validator('role_id')
    def validate_role_customer_exclusivity(cls, v, info):
        customer_id = info.data.get('customer_id')
        # Both cannot be set or both cannot be None
        if v is not None and customer_id is not None:
            raise ValueError('User cannot have both role_id and customer_id')
        if v is None and customer_id is None:
            raise ValueError('User must have either role_id or customer_id')
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    password: Optional[str] = Field(None, min_length=6)
    role_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    customer_id: Optional[UUID] = None
    asis_company_id: Optional[UUID] = None
    asis_branch_id: Optional[UUID] = None
    asis_warehouse_id: Optional[UUID] = None


class ProvinceDetail(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class DistrictDetail(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class CustomerDetail(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    PIC: Optional[str] = None
    pic_phone: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    province_id: Optional[UUID] = None
    province: Optional[ProvinceDetail] = None
    district_id: Optional[UUID] = None
    district: Optional[DistrictDetail] = None
    region_id: Optional[UUID] = None
    sales_id: Optional[UUID] = None
    pusat_id: Optional[UUID] = None


class AsisEntityBrief(BaseModel):
    """Ringkasan entity ASIS (company / branch / warehouse) untuk embedding di UserResponse."""
    id: UUID
    asis_id: str
    asis_code: str
    name: str

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    id: UUID
    role_id: Optional[UUID] = None
    role_name: Optional[str] = None
    role_scope: Optional[str] = None
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    customer: Optional[CustomerDetail] = None
    asis_company_id: Optional[UUID] = None
    asis_company: Optional[AsisEntityBrief] = None
    asis_branch_id: Optional[UUID] = None
    asis_branch: Optional[AsisEntityBrief] = None
    asis_warehouse_id: Optional[UUID] = None
    asis_warehouse: Optional[AsisEntityBrief] = None

    class Config:
        from_attributes = True


class UserInDB(UserBase):
    id: UUID
    password: str
    role_id: UUID
    is_active: bool

    class Config:
        from_attributes = True


# Role Schemas
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleResponse(RoleBase):
    id: UUID
    scope: str
    permissions: List[str] = []

    class Config:
        from_attributes = True
