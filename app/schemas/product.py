from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from decimal import Decimal


class ProductBase(BaseModel):
    product_name: str = Field(..., max_length=100)
    category_id: UUID
    default_price: Decimal = Field(..., ge=0, decimal_places=2)
    unit: str = Field(..., max_length=50)
    image: Optional[str] = Field(None, max_length=255)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    product_name: Optional[str] = Field(None, max_length=100)
    category_id: Optional[UUID] = None
    default_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    unit: Optional[str] = Field(None, max_length=50)
    image: Optional[str] = Field(None, max_length=255)


class ProductResponse(ProductBase):
    id: UUID
    category_name: Optional[str] = None

    class Config:
        from_attributes = True
