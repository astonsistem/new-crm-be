from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


def _clean_url(v: str) -> str:
    """Strip trailing slash dan validasi skema http/https."""
    v = v.strip().rstrip("/")
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("base_url harus dimulai dengan http:// atau https://")
    return v


class AsisConfigBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Label/nama konfigurasi")
    base_url: str = Field(
        ...,
        min_length=7,
        max_length=500,
        description="Base URL ASIS, contoh: https://api-ast.infoku.asia atau http://192.168.1.1:3002",
    )
    username: str = Field(..., min_length=1, max_length=100, description="Username login ASIS")
    is_active: bool = Field(False, description="Jadikan konfigurasi aktif")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        return _clean_url(v)


class AsisConfigCreate(AsisConfigBase):
    password: str = Field(..., min_length=1, max_length=255, description="Password login ASIS")


class AsisConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    base_url: Optional[str] = Field(None, min_length=7, max_length=500)
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=1, max_length=255)
    is_active: Optional[bool] = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _clean_url(v)


class AsisConfigResponse(AsisConfigBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
