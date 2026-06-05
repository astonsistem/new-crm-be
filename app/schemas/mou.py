from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from app.utils.datetime_utils import NaiveDatetime, OptionalNaiveDatetime
from decimal import Decimal
from app.schemas.status import StatusMOUCreate, StatusMOUUpdate, StatusMOUResponse


class StatusDetail(BaseModel):
    code: str
    name: Optional[str] = None

    class Config:
        from_attributes = True


class CustomerDetail(BaseModel):
    id: UUID
    type: Optional[str] = None
    name: str
    PIC: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    class Config:
        from_attributes = True


class MOUBase(BaseModel):
    customer_id: UUID
    status_mou_id: UUID
    start_date: NaiveDatetime
    end_date: NaiveDatetime
    description: Optional[str] = Field(None, description="MOU description")
    contract_file: Optional[str] = Field(None, max_length=255)


class MOUCreate(MOUBase):
    pass


class MOUUpdate(BaseModel):
    no_mou: Optional[str] = Field(None, min_length=1, max_length=100)
    customer_id: Optional[UUID] = None
    status_mou_id: Optional[UUID] = None
    start_date: OptionalNaiveDatetime = None
    end_date: OptionalNaiveDatetime = None
    description: Optional[str] = Field(None, description="MOU description")
    contract_file: Optional[str] = Field(None, max_length=255)


class MOUResponse(MOUBase):
    id: UUID
    no_mou: str
    created_by: UUID
    created_by_name: Optional[str] = None
    customer: Optional[CustomerDetail] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None
    status_mou: Optional[StatusDetail] = None
    contract_file_base64: Optional[str] = Field(
        None,
        description="Base64-encoded contract file content (only populated on GET /mou/{id} when contract_file exists)",
    )

    class Config:
        from_attributes = True



class ProductDetail(BaseModel):
    id: UUID
    product_name: str
    category_id: UUID
    category_name: Optional[str] = None
    default_price: Decimal
    unit: str
    image: Optional[str] = None

    class Config:
        from_attributes = True



class MOUProductBase(BaseModel):
    mou_id: UUID
    product_id: UUID
    contract_price: Decimal = Field(..., ge=0, max_digits=15, decimal_places=2)
    active: bool = True


class MOUProductCreate(BaseModel):
    product_id: UUID
    contract_price: Decimal = Field(..., ge=0, max_digits=15, decimal_places=2)
    active: bool = True


class MOUProductUpdate(BaseModel):
    contract_price: Optional[Decimal] = Field(None, ge=0, max_digits=15, decimal_places=2)
    active: Optional[bool] = None


class MOUProductResponse(MOUProductBase):
    id: UUID
    product: Optional[ProductDetail] = None
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None

    class Config:
        from_attributes = True


class MOUFileUploadResponse(BaseModel):
    message: str
    filename: str
    file_path: str
    mou_id: str
