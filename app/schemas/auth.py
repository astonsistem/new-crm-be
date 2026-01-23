from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


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


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    role_id: int


class UserResponse(UserBase):
    id: int
    role_id: int
    role_name: Optional[str] = None
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserInDB(UserBase):
    id: int
    password: str
    role_id: int
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
    id: int

    class Config:
        from_attributes = True
