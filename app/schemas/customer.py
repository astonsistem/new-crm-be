from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Literal, Optional
from datetime import datetime
from uuid import UUID


# Nested schemas for region information
class ProvinceInfo(BaseModel):
    id: UUID
    name: str
    
    class Config:
        from_attributes = True

class SalesInfo(BaseModel):
    id: UUID
    name: str
    phone: Optional[str] = None
    
    class Config:
        from_attributes = True

class DistrictInfo(BaseModel):
    id: UUID
    name: str
    
    class Config:
        from_attributes = True


class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    PIC: Optional[str] = Field(None, max_length=100, description="Person in Charge")
    pic_phone: Optional[str] = Field(None, max_length=20, description="PIC phone number")
    email: Optional[EmailStr] = Field(None, description="Email address (optional)")
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=512)
    province_id: Optional[UUID] = Field(None, description="Province ID")
    district_id: Optional[UUID] = Field(None, description="District ID")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class CustomerCreate(CustomerBase):
    type: Literal["COMPANY", "REGION", "BRANCH"] = Field(..., description="Customer type")
    sales_id: UUID = Field(..., description="Sales user ID responsible for this customer")
    pusat_id: Optional[UUID] = Field(None, description="Company ID (required for REGION and BRANCH)")
    region_id: Optional[UUID] = Field(None, description="Region ID (required for BRANCH)")
    
    @field_validator('pusat_id')
    def validate_pusat_id(cls, v, info):
        customer_type = info.data.get('type')
        if customer_type == "COMPANY" and v is not None:
            raise ValueError("COMPANY type cannot have pusat_id")
        if customer_type in ["REGION", "BRANCH"] and v is None:
            raise ValueError(f"{customer_type} type must have pusat_id")
        return v
    
    @field_validator('region_id')
    def validate_region_id(cls, v, info):
        customer_type = info.data.get('type')
        if customer_type in ["COMPANY", "REGION"] and v is not None:
            raise ValueError(f"{customer_type} type cannot have region_id")
        if customer_type == "BRANCH" and v is None:
            raise ValueError("BRANCH type must have region_id")
        return v
    
    @field_validator('district_id')
    def validate_district_id(cls, v, info):
        province_id = info.data.get('province_id')
        if v is not None and province_id is None:
            raise ValueError("district_id requires province_id to be set")
        return v


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    PIC: Optional[str] = Field(None, max_length=100, description="Person in Charge")
    pic_phone: Optional[str] = Field(None, max_length=20, description="PIC phone number")
    email: Optional[EmailStr] = Field(None, description="Email address (optional)")
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=512)
    type: Optional[Literal["COMPANY", "REGION", "BRANCH"]] = None
    pusat_id: Optional[UUID] = None
    region_id: Optional[UUID] = None
    sales: Optional[SalesInfo] = None
    province: Optional[ProvinceInfo] = None
    district: Optional[DistrictInfo] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class CustomerResponse(CustomerBase):
    id: UUID
    type: str
    pusat_id: Optional[UUID] = None
    region_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    sales: Optional[SalesInfo] = None
    province: Optional[ProvinceInfo] = None
    district: Optional[DistrictInfo] = None
    username: Optional[str] = Field(None, description="Login username of linked customer user, if any")
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        # Map the sales_user relationship to sales field
        populate_by_name = True
        
    @classmethod
    def model_validate(cls, customer):
        # Handle the sales_user -> sales mapping
        if hasattr(customer, 'sales_user') and customer.sales_user:
            customer_dict = {
                **{k: v for k, v in customer.__dict__.items() if not k.startswith('_')},
                'sales': {
                    'id': customer.sales_user.id,
                    'name': customer.sales_user.name,
                    'phone': customer.sales_user.phone,
                } if customer.sales_user else None
            }
            return super().model_validate(customer_dict)
        return super().model_validate(customer)


class CustomerListResponse(BaseModel):
    data: List[CustomerResponse]
    total: int


class CustomerDetailResponse(CustomerBase):
    id: UUID
    type: str
    pusat_id: Optional[UUID] = None
    region_id: Optional[UUID] = None
    province_id: Optional[UUID] = None
    district_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    sales: Optional[SalesInfo] = None
    province: Optional[ProvinceInfo] = None
    district: Optional[DistrictInfo] = None

    class Config:
        from_attributes = True
        
    @classmethod
    def model_validate(cls, customer):
        # Handle the sales_user -> sales mapping
        if hasattr(customer, 'sales_user') and customer.sales_user:
            customer_dict = {
                **{k: v for k, v in customer.__dict__.items() if not k.startswith('_')},
                'sales': {
                    'id': customer.sales_user.id,
                    'name': customer.sales_user.name,
                    'phone': customer.sales_user.phone,
                } if customer.sales_user else None
            }
            return super().model_validate(customer_dict)
        return super().model_validate(customer)
