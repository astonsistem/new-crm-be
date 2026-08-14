from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class AsisEntityBrief(BaseModel):
    id: UUID
    name: str
    asis_code: Optional[str] = None

    class Config:
        from_attributes = True


class BankAccountBase(BaseModel):
    bank_name: str = Field(..., min_length=1, max_length=100)
    account_number: str = Field(..., min_length=1, max_length=50)
    account_holder: str = Field(..., min_length=1, max_length=150)
    bank_branch: Optional[str] = Field(None, max_length=150)
    is_active: bool = True
    is_default: bool = Field(
        False,
        description="Tampil di invoice sebagai opsi transfer; boleh true pada lebih dari satu rekening",
    )
    asis_company_id: Optional[UUID] = None
    asis_branch_id: Optional[UUID] = None
    asis_warehouse_id: Optional[UUID] = None

    @field_validator("bank_name", "account_number", "account_holder", "bank_branch", mode="before")
    @classmethod
    def normalize_text(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class BankAccountCreate(BankAccountBase):
    pass


class BankAccountUpdate(BaseModel):
    bank_name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_number: Optional[str] = Field(None, min_length=1, max_length=50)
    account_holder: Optional[str] = Field(None, min_length=1, max_length=150)
    bank_branch: Optional[str] = Field(None, max_length=150)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = Field(
        None,
        description="Tampil di invoice sebagai opsi transfer; boleh true pada lebih dari satu rekening",
    )
    asis_company_id: Optional[UUID] = None
    asis_branch_id: Optional[UUID] = None
    asis_warehouse_id: Optional[UUID] = None

    @field_validator("bank_name", "account_number", "account_holder", "bank_branch", mode="before")
    @classmethod
    def normalize_text(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class BankAccountResponse(BankAccountBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    asis_company: Optional[AsisEntityBrief] = None
    asis_branch: Optional[AsisEntityBrief] = None
    asis_warehouse: Optional[AsisEntityBrief] = None

    class Config:
        from_attributes = True


class BankAccountListResponse(BaseModel):
    data: List[BankAccountResponse]
    total: int


class BankAccountBriefResponse(BaseModel):
    id: UUID
    bank_name: str
    account_number: str
    account_holder: str
    bank_branch: Optional[str] = None
    is_default: bool = False

    class Config:
        from_attributes = True
