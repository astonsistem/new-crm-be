from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class RoleScope(str, Enum):
    ADMIN = "ADMIN"
    SALES = "SALES"
    CUSTOMER = "CUSTOMER"


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    permissions: List[str] = []
    scope: RoleScope


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    permissions: Optional[List[str]] = None
    scope: Optional[RoleScope] = None


class RoleResponse(RoleBase):
    id: UUID

    model_config = {"from_attributes": True}
