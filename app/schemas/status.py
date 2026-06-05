from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


# Status MOU Schemas
class StatusMOUBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: Optional[str] = Field(None, max_length=100)


class StatusMOUCreate(StatusMOUBase):
    pass


class StatusMOUUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=30)
    name: Optional[str] = Field(None, max_length=100)


class StatusMOUResponse(StatusMOUBase):
    id: UUID

    class Config:
        from_attributes = True


# Status Service Schemas
class StatusServiceBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: Optional[str] = Field(None, max_length=100)


class StatusServiceCreate(StatusServiceBase):
    pass


class StatusServiceUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=30)
    name: Optional[str] = Field(None, max_length=100)


class StatusServiceResponse(StatusServiceBase):
    id: UUID

    class Config:
        from_attributes = True
