from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime


# ── Company ───────────────────────────────────────────────────────────────────

class AsisCompanyResponse(BaseModel):
    id: UUID
    asis_id: str
    asis_code: str
    name: str
    address: Optional[str] = None
    telp: Optional[str] = None
    initial: Optional[str] = None
    pic_name: Optional[str] = None
    pic_phone: Optional[str] = None
    pic_email: Optional[str] = None
    pic_jabatan: Optional[str] = None
    ppn: Optional[str] = None
    logo: Optional[str] = None
    status: bool
    synced_at: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AsisCompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None
    telp: Optional[str] = Field(None, max_length=50)
    initial: Optional[str] = Field(None, max_length=50)
    pic_name: Optional[str] = Field(None, max_length=100)
    pic_phone: Optional[str] = Field(None, max_length=50)
    pic_email: Optional[str] = Field(None, max_length=100)
    pic_jabatan: Optional[str] = Field(None, max_length=100)
    ppn: Optional[str] = Field(None, max_length=50)
    logo: Optional[str] = None
    status: Optional[bool] = None


class AsisCompanyCreate(BaseModel):
    asis_id: str = Field(..., min_length=1, max_length=255, description="ID unik dari ASIS")
    asis_code: str = Field(..., min_length=1, max_length=100, description="Kode unik dari ASIS")
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    telp: Optional[str] = Field(None, max_length=50)
    initial: Optional[str] = Field(None, max_length=50)
    pic_name: Optional[str] = Field(None, max_length=100)
    pic_phone: Optional[str] = Field(None, max_length=50)
    pic_email: Optional[str] = Field(None, max_length=100)
    pic_jabatan: Optional[str] = Field(None, max_length=100)
    ppn: Optional[str] = Field(None, max_length=50)
    logo: Optional[str] = None
    status: bool = True


class AsisCompanyDropdown(BaseModel):
    id: UUID
    asis_id: str
    asis_code: str
    name: str

    model_config = {"from_attributes": True}


class AsisCompanyListResponse(BaseModel):
    data: List[AsisCompanyResponse]
    total: int


class AsisCompanyPreview(BaseModel):
    """Data company dari ASIS sebelum disimpan ke CRM."""
    asis_id: str
    asis_code: str
    name: str
    address: Optional[str] = None
    telp: Optional[str] = None
    initial: Optional[str] = None
    pic_name: Optional[str] = None
    pic_phone: Optional[str] = None
    pic_email: Optional[str] = None
    status: bool
    already_synced: bool = False


# ── Branch ────────────────────────────────────────────────────────────────────

class AsisCompanyBrief(BaseModel):
    id: UUID
    asis_id: str
    name: str

    model_config = {"from_attributes": True}


class AsisBranchResponse(BaseModel):
    id: UUID
    asis_id: str
    asis_code: str
    asis_company_id: Optional[UUID] = None
    company: Optional[AsisCompanyBrief] = None
    name: str
    address: Optional[str] = None
    telp: Optional[str] = None
    initial: Optional[str] = None
    pic_name: Optional[str] = None
    pic_email: Optional[str] = None
    status: bool
    synced_at: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AsisBranchUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None
    telp: Optional[str] = Field(None, max_length=50)
    initial: Optional[str] = Field(None, max_length=50)
    pic_name: Optional[str] = Field(None, max_length=100)
    pic_email: Optional[str] = Field(None, max_length=100)
    status: Optional[bool] = None
    asis_company_id: Optional[UUID] = None


class AsisBranchCreate(BaseModel):
    asis_id: str = Field(..., min_length=1, max_length=255)
    asis_code: str = Field(..., min_length=1, max_length=100)
    asis_company_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    telp: Optional[str] = Field(None, max_length=50)
    initial: Optional[str] = Field(None, max_length=50)
    pic_name: Optional[str] = Field(None, max_length=100)
    pic_email: Optional[str] = Field(None, max_length=100)
    status: bool = True


class AsisBranchDropdown(BaseModel):
    id: UUID
    asis_id: str
    asis_code: str
    name: str
    asis_company_id: Optional[UUID] = None

    model_config = {"from_attributes": True}


class AsisBranchListResponse(BaseModel):
    data: List[AsisBranchResponse]
    total: int


class AsisBranchPreview(BaseModel):
    """Data branch dari ASIS sebelum disimpan ke CRM."""
    asis_id: str
    asis_code: str
    name: str
    address: Optional[str] = None
    telp: Optional[str] = None
    initial: Optional[str] = None
    pic_name: Optional[str] = None
    pic_email: Optional[str] = None
    status: bool
    already_synced: bool = False


class AsisBranchPreviewListResponse(BaseModel):
    data: List[AsisBranchPreview]
    total: int


# ── Warehouse ─────────────────────────────────────────────────────────────────

class AsisBranchBrief(BaseModel):
    id: UUID
    asis_id: str
    name: str

    model_config = {"from_attributes": True}


class AsisWarehouseResponse(BaseModel):
    id: UUID
    asis_id: str
    asis_code: str
    asis_company_id: Optional[UUID] = None
    asis_branch_id: Optional[UUID] = None
    company: Optional[AsisCompanyBrief] = None
    branch: Optional[AsisBranchBrief] = None
    name: str
    location: Optional[str] = None
    pic_name: Optional[str] = None
    pic_email: Optional[str] = None
    status: bool
    is_kongsi: bool
    is_kongsi_vendor: bool
    synced_at: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AsisWarehouseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    location: Optional[str] = None
    pic_name: Optional[str] = Field(None, max_length=100)
    pic_email: Optional[str] = Field(None, max_length=100)
    status: Optional[bool] = None
    is_kongsi: Optional[bool] = None
    is_kongsi_vendor: Optional[bool] = None
    asis_branch_id: Optional[UUID] = None
    asis_company_id: Optional[UUID] = None


class AsisWarehouseCreate(BaseModel):
    asis_id: str = Field(..., min_length=1, max_length=255)
    asis_code: str = Field(..., min_length=1, max_length=100)
    asis_company_id: Optional[UUID] = None
    asis_branch_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    location: Optional[str] = None
    pic_name: Optional[str] = Field(None, max_length=100)
    pic_email: Optional[str] = Field(None, max_length=100)
    status: bool = True
    is_kongsi: bool = False
    is_kongsi_vendor: bool = False


class AsisWarehouseDropdown(BaseModel):
    id: UUID
    asis_id: str
    asis_code: str
    name: str
    asis_branch_id: Optional[UUID] = None
    is_kongsi: bool
    is_kongsi_vendor: bool

    model_config = {"from_attributes": True}


class AsisWarehouseListResponse(BaseModel):
    data: List[AsisWarehouseResponse]
    total: int


class AsisWarehousePreview(BaseModel):
    """Data warehouse dari ASIS sebelum disimpan ke CRM."""
    asis_id: str
    asis_code: str
    name: str
    location: Optional[str] = None
    pic_name: Optional[str] = None
    pic_email: Optional[str] = None
    status: bool
    is_kongsi: bool
    is_kongsi_vendor: bool
    already_synced: bool = False


class AsisWarehousePreviewListResponse(BaseModel):
    data: List[AsisWarehousePreview]
    total: int


# ── Sync result ───────────────────────────────────────────────────────────────

class SyncResult(BaseModel):
    synced_count: int = Field(description="Record baru yang berhasil disimpan")
    updated_count: int = Field(description="Record lama yang diperbarui")
    skipped_count: int = Field(description="Record dilewati karena konflik kode")
    errors: List[str] = Field(default_factory=list, description="Pesan error per item")
