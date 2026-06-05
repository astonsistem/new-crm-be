from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import List, Optional

from app.core.logging import get_logger
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.asis_sync import AsisBranch, AsisWarehouse
from app.routers.asis.helpers import (
    ensure_branch_exists,
    ensure_company_exists,
    ensure_unique_asis_code,
    ensure_unique_asis_id,
    ensure_warehouse_exists,
)
from app.schemas.asis_sync import (
    AsisWarehouseCreate,
    AsisWarehouseDropdown,
    AsisWarehouseListResponse,
    AsisWarehouseResponse,
    AsisWarehouseUpdate,
)

logger = get_logger("app.asis_warehouse")

router = APIRouter(prefix="/asis-warehouses", tags=["ASIS Warehouses"])


def _warehouse_opts():
    return [
        selectinload(AsisWarehouse.company),
        selectinload(AsisWarehouse.branch),
    ]


def _apply_warehouse_filters(
    stmt,
    *,
    search: Optional[str] = None,
    status_filter: Optional[bool] = None,
    asis_company_id: Optional[UUID] = None,
    asis_branch_id: Optional[UUID] = None,
    is_kongsi: Optional[bool] = None,
    is_kongsi_vendor: Optional[bool] = None,
):
    if search:
        stmt = stmt.where(
            AsisWarehouse.name.ilike(f"%{search}%")
            | AsisWarehouse.asis_code.ilike(f"%{search}%")
        )
    if status_filter is not None:
        stmt = stmt.where(AsisWarehouse.status == status_filter)
    if asis_company_id:
        stmt = stmt.where(AsisWarehouse.asis_company_id == asis_company_id)
    if asis_branch_id:
        stmt = stmt.where(AsisWarehouse.asis_branch_id == asis_branch_id)
    if is_kongsi is not None:
        stmt = stmt.where(AsisWarehouse.is_kongsi == is_kongsi)
    if is_kongsi_vendor is not None:
        stmt = stmt.where(AsisWarehouse.is_kongsi_vendor == is_kongsi_vendor)
    return stmt


@router.get("/", response_model=AsisWarehouseListResponse)
async def list_warehouses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, description="Cari nama atau kode warehouse"),
    status_filter: Optional[bool] = Query(None, alias="status"),
    asis_company_id: Optional[UUID] = Query(None, description="Filter berdasarkan CRM company ID"),
    asis_branch_id: Optional[UUID] = Query(None, description="Filter berdasarkan CRM branch ID"),
    is_kongsi: Optional[bool] = Query(None),
    is_kongsi_vendor: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar warehouse tersimpan di CRM dengan paginasi."""
    stmt = select(AsisWarehouse).options(*_warehouse_opts())
    stmt = _apply_warehouse_filters(
        stmt,
        search=search,
        status_filter=status_filter,
        asis_company_id=asis_company_id,
        asis_branch_id=asis_branch_id,
        is_kongsi=is_kongsi,
        is_kongsi_vendor=is_kongsi_vendor,
    )
    stmt = stmt.order_by(AsisWarehouse.name)

    total = (await db.execute(
        select(func.count()).select_from(stmt.with_only_columns(AsisWarehouse.id).subquery())
    )).scalar_one()
    warehouses = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return AsisWarehouseListResponse(data=warehouses, total=total)


@router.get("/dropdown", response_model=List[AsisWarehouseDropdown])
async def dropdown_warehouses(
    asis_company_id: Optional[UUID] = Query(None, description="Filter berdasarkan CRM company ID"),
    asis_branch_id: Optional[UUID] = Query(None, description="Filter berdasarkan CRM branch ID"),
    search: Optional[str] = Query(None, description="Cari nama atau kode warehouse"),
    is_kongsi: Optional[bool] = Query(None),
    is_kongsi_vendor: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Semua warehouse aktif untuk dropdown (tanpa paginasi)."""
    stmt = select(AsisWarehouse)
    stmt = _apply_warehouse_filters(
        stmt,
        search=search,
        status_filter=True,
        asis_company_id=asis_company_id,
        asis_branch_id=asis_branch_id,
        is_kongsi=is_kongsi,
        is_kongsi_vendor=is_kongsi_vendor,
    )
    stmt = stmt.order_by(AsisWarehouse.name)
    return (await db.execute(stmt)).scalars().all()


@router.get("/{warehouse_id}", response_model=AsisWarehouseResponse)
async def get_warehouse(
    warehouse_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Detail warehouse berdasarkan CRM ID."""
    warehouse = (await db.execute(
        select(AsisWarehouse).options(*_warehouse_opts()).where(AsisWarehouse.id == warehouse_id)
    )).scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse tidak ditemukan.")
    return warehouse


@router.post("/", response_model=AsisWarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    data: AsisWarehouseCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Buat warehouse baru di CRM (input manual)."""
    await ensure_unique_asis_id(db, AsisWarehouse, data.asis_id, label="Warehouse")
    await ensure_unique_asis_code(db, AsisWarehouse, data.asis_code, label="Warehouse")

    if data.asis_company_id:
        await ensure_company_exists(db, data.asis_company_id)
    if data.asis_branch_id:
        branch = await ensure_branch_exists(db, data.asis_branch_id)
        if data.asis_company_id and branch.asis_company_id and branch.asis_company_id != data.asis_company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch tidak termasuk dalam company yang dipilih.",
            )

    warehouse = AsisWarehouse(**data.model_dump())
    db.add(warehouse)
    await db.flush()

    warehouse = (await db.execute(
        select(AsisWarehouse).options(*_warehouse_opts()).where(AsisWarehouse.id == warehouse.id)
    )).scalar_one()
    await db.commit()
    logger.info("Warehouse dibuat: id=%s asis_id=%s", warehouse.id, warehouse.asis_id)
    return warehouse


@router.put("/{warehouse_id}", response_model=AsisWarehouseResponse)
async def update_warehouse(
    warehouse_id: UUID,
    data: AsisWarehouseUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update warehouse di CRM."""
    warehouse = await ensure_warehouse_exists(db, warehouse_id)
    update_data = data.model_dump(exclude_unset=True)

    new_company_id = update_data.get("asis_company_id", warehouse.asis_company_id)
    new_branch_id = update_data.get("asis_branch_id", warehouse.asis_branch_id)

    if "asis_company_id" in update_data and update_data["asis_company_id"] is not None:
        await ensure_company_exists(db, update_data["asis_company_id"])
    if "asis_branch_id" in update_data and update_data["asis_branch_id"] is not None:
        branch = await ensure_branch_exists(db, update_data["asis_branch_id"])
        if new_company_id and branch.asis_company_id and branch.asis_company_id != new_company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Branch tidak termasuk dalam company yang dipilih.",
            )

    for field, value in update_data.items():
        setattr(warehouse, field, value)

    await db.commit()
    warehouse = (await db.execute(
        select(AsisWarehouse).options(*_warehouse_opts()).where(AsisWarehouse.id == warehouse_id)
    )).scalar_one()
    logger.info("Warehouse diperbarui: id=%s", warehouse_id)
    return warehouse


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse(
    warehouse_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus warehouse dari CRM."""
    warehouse = await ensure_warehouse_exists(db, warehouse_id)
    await db.delete(warehouse)
    await db.commit()
    logger.info("Warehouse dihapus: id=%s", warehouse_id)
    return None
