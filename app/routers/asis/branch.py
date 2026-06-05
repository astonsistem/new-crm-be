from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import List, Optional

from app.core.logging import get_logger
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.asis_sync import AsisBranch
from app.routers.asis.helpers import (
    ensure_branch_exists,
    ensure_company_exists,
    ensure_unique_asis_code,
    ensure_unique_asis_id,
)
from app.schemas.asis_sync import (
    AsisBranchCreate,
    AsisBranchDropdown,
    AsisBranchListResponse,
    AsisBranchResponse,
    AsisBranchUpdate,
)

logger = get_logger("app.asis_branch")

router = APIRouter(prefix="/asis-branches", tags=["ASIS Branches"])


def _branch_opts():
    return [selectinload(AsisBranch.company)]


def _apply_branch_filters(
    stmt,
    *,
    search: Optional[str] = None,
    status_filter: Optional[bool] = None,
    asis_company_id: Optional[UUID] = None,
):
    if search:
        stmt = stmt.where(
            AsisBranch.name.ilike(f"%{search}%")
            | AsisBranch.asis_code.ilike(f"%{search}%")
        )
    if status_filter is not None:
        stmt = stmt.where(AsisBranch.status == status_filter)
    if asis_company_id:
        stmt = stmt.where(AsisBranch.asis_company_id == asis_company_id)
    return stmt


@router.get("/", response_model=AsisBranchListResponse)
async def list_branches(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, description="Cari nama atau kode branch"),
    status_filter: Optional[bool] = Query(None, alias="status"),
    asis_company_id: Optional[UUID] = Query(None, description="Filter berdasarkan CRM company ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar branch tersimpan di CRM dengan paginasi."""
    stmt = select(AsisBranch).options(*_branch_opts())
    stmt = _apply_branch_filters(
        stmt, search=search, status_filter=status_filter, asis_company_id=asis_company_id
    )
    stmt = stmt.order_by(AsisBranch.name)

    total = (await db.execute(
        select(func.count()).select_from(stmt.with_only_columns(AsisBranch.id).subquery())
    )).scalar_one()
    branches = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return AsisBranchListResponse(data=branches, total=total)


@router.get("/dropdown", response_model=List[AsisBranchDropdown])
async def dropdown_branches(
    asis_company_id: Optional[UUID] = Query(None, description="Filter berdasarkan CRM company ID"),
    search: Optional[str] = Query(None, description="Cari nama atau kode branch"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Semua branch aktif untuk dropdown (tanpa paginasi)."""
    stmt = select(AsisBranch)
    stmt = _apply_branch_filters(
        stmt, search=search, status_filter=True, asis_company_id=asis_company_id
    )
    stmt = stmt.order_by(AsisBranch.name)
    return (await db.execute(stmt)).scalars().all()


@router.get("/{branch_id}", response_model=AsisBranchResponse)
async def get_branch(
    branch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Detail branch berdasarkan CRM ID."""
    branch = (await db.execute(
        select(AsisBranch).options(*_branch_opts()).where(AsisBranch.id == branch_id)
    )).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch tidak ditemukan.")
    return branch


@router.post("/", response_model=AsisBranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    data: AsisBranchCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Buat branch baru di CRM (input manual)."""
    await ensure_unique_asis_id(db, AsisBranch, data.asis_id, label="Branch")
    await ensure_unique_asis_code(db, AsisBranch, data.asis_code, label="Branch")

    if data.asis_company_id:
        await ensure_company_exists(db, data.asis_company_id)

    branch = AsisBranch(**data.model_dump())
    db.add(branch)
    await db.flush()

    branch = (await db.execute(
        select(AsisBranch).options(*_branch_opts()).where(AsisBranch.id == branch.id)
    )).scalar_one()
    await db.commit()
    logger.info("Branch dibuat: id=%s asis_id=%s", branch.id, branch.asis_id)
    return branch


@router.put("/{branch_id}", response_model=AsisBranchResponse)
async def update_branch(
    branch_id: UUID,
    data: AsisBranchUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update branch di CRM."""
    branch = await ensure_branch_exists(db, branch_id)
    update_data = data.model_dump(exclude_unset=True)

    if "asis_company_id" in update_data and update_data["asis_company_id"] is not None:
        await ensure_company_exists(db, update_data["asis_company_id"])

    for field, value in update_data.items():
        setattr(branch, field, value)

    await db.commit()
    branch = (await db.execute(
        select(AsisBranch).options(*_branch_opts()).where(AsisBranch.id == branch_id)
    )).scalar_one()
    logger.info("Branch diperbarui: id=%s", branch_id)
    return branch


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus branch dari CRM."""
    branch = await ensure_branch_exists(db, branch_id)
    await db.delete(branch)
    await db.commit()
    logger.info("Branch dihapus: id=%s", branch_id)
    return None
