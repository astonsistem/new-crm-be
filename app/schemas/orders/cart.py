from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class CartItemBase(BaseModel):
    mou_product_id: UUID
    quantity: int = Field(..., gt=0, description="Quantity must be greater than 0")


class CartItemCreate(CartItemBase):
    pass


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0, description="Quantity must be greater than 0")


class ProductDetail(BaseModel):
    product_id: UUID
    product_name: str
    category_name: str
    contract_price: Decimal


class CartItemResponse(BaseModel):
    id: UUID
    customer_id: UUID
    mou_product_id: UUID
    quantity: int
    added_at: datetime
    product: Optional[ProductDetail] = None
    subtotal: Optional[Decimal] = None

    class Config:
        from_attributes = True


class CartSummary(BaseModel):
    total_items: int
    total_amount: Decimal
    items: list[CartItemResponse]
