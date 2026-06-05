from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from decimal import Decimal


class CategoryBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=512)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=512)


class CategoryResponse(CategoryBase):
    id: UUID

    class Config:
        from_attributes = True
