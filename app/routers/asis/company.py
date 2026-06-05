from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional

from app.core.logging import get_logger
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.asis_sync import AsisCompany
from app.routers.asis.helpers import (
    ensure_company_exists,
    ensure_unique_asis_code,
    ensure_unique_asis_id,
)
from app.schemas.asis_sync import (
    AsisCompanyCreate,
    AsisCompanyDropdown,
    AsisCompanyListResponse,
    AsisCompanyResponse,
    AsisCompanyUpdate,
)

logger = get_logger("app.asis_company")

router = APIRouter(prefix="/asis-companies", tags=["ASIS Companies"])


def _apply_company_filters(
    stmt,
    *,
    search: Optional[str] = None,
    status_filter: Optional[bool] = None,
):
    if search:
        stmt = stmt.where(
            AsisCompany.name.ilike(f"%{search}%")
            | AsisCompany.asis_code.ilike(f"%{search}%")
        )
    if status_filter is not None:
        stmt = stmt.where(AsisCompany.status == status_filter)
    return stmt


@router.get("/", response_model=AsisCompanyListResponse)
async def list_companies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, description="Cari nama atau kode company"),
    status_filter: Optional[bool] = Query(None, alias="status", description="Filter status aktif/nonaktif"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar company tersimpan di CRM dengan paginasi."""
    stmt = _apply_company_filters(select(AsisCompany), search=search, status_filter=status_filter)
    stmt = stmt.order_by(AsisCompany.name)

    total = (await db.execute(
        select(func.count()).select_from(stmt.with_only_columns(AsisCompany.id).subquery())
    )).scalar_one()
    companies = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return AsisCompanyListResponse(data=companies, total=total)


@router.get("/dropdown", response_model=List[AsisCompanyDropdown])
async def dropdown_companies(
    search: Optional[str] = Query(None, description="Cari nama atau kode company"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Semua company aktif untuk dropdown (tanpa paginasi)."""
    stmt = _apply_company_filters(select(AsisCompany), search=search, status_filter=True)
    stmt = stmt.order_by(AsisCompany.name)
    return (await db.execute(stmt)).scalars().all()


@router.get("/{company_id}", response_model=AsisCompanyResponse)
async def get_company(
    company_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Detail company berdasarkan CRM ID."""
    return await ensure_company_exists(db, company_id)


@router.post("/", response_model=AsisCompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: AsisCompanyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Buat company baru di CRM (input manual)."""
    await ensure_unique_asis_id(db, AsisCompany, data.asis_id, label="Company")
    await ensure_unique_asis_code(db, AsisCompany, data.asis_code, label="Company")

    company = AsisCompany(**data.model_dump())
    db.add(company)
    await db.flush()

    company = await ensure_company_exists(db, company.id)
    await db.commit()
    logger.info("Company dibuat: id=%s asis_id=%s", company.id, company.asis_id)
    return company


@router.put("/{company_id}", response_model=AsisCompanyResponse)
async def update_company(
    company_id: UUID,
    data: AsisCompanyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update company di CRM."""
    company = await ensure_company_exists(db, company_id)
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(company, field, value)

    await db.commit()
    company = await ensure_company_exists(db, company_id)
    logger.info("Company diperbarui: id=%s", company_id)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus company dari CRM."""
    company = await ensure_company_exists(db, company_id)
    await db.delete(company)
    await db.commit()
    logger.info("Company dihapus: id=%s", company_id)
    return None
