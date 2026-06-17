from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.order import Order_Service
from app.models.service_point import Service_Point
from app.schemas.service_point import (
    ServicePointCreate,
    ServicePointListResponse,
    ServicePointResponse,
    ServicePointUpdate,
)

router = APIRouter(prefix="/service-points", tags=["Service Points"])


async def ensure_service_point_exists(
    db: AsyncSession,
    service_point_id: UUID,
    *,
    detail: str = "Service point tidak ditemukan.",
) -> Service_Point:
    point = (await db.execute(
        select(Service_Point).where(Service_Point.id == service_point_id)
    )).scalar_one_or_none()
    if not point:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return point


@router.get("/", response_model=ServicePointListResponse)
async def list_service_points(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    search: Optional[str] = Query(None, description="Cari nama atau alamat service point"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar semua titik service."""
    stmt = select(Service_Point)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Service_Point.name.ilike(pattern) | Service_Point.address.ilike(pattern)
        )
    stmt = stmt.order_by(Service_Point.name)

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    points = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return ServicePointListResponse(data=points, total=total)


@router.get("/dropdown", response_model=List[ServicePointResponse])
async def dropdown_service_points(
    search: Optional[str] = Query(None, description="Cari nama atau alamat"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Semua titik service untuk dropdown (tanpa paginasi)."""
    stmt = select(Service_Point).order_by(Service_Point.name)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Service_Point.name.ilike(pattern) | Service_Point.address.ilike(pattern)
        )
    return (await db.execute(stmt)).scalars().all()


@router.get("/{service_point_id}", response_model=ServicePointResponse)
async def get_service_point(
    service_point_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Detail titik service."""
    return await ensure_service_point_exists(db, service_point_id)


@router.post("/", response_model=ServicePointResponse, status_code=status.HTTP_201_CREATED)
async def create_service_point(
    data: ServicePointCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Buat titik service baru."""
    existing = (await db.execute(
        select(Service_Point).where(Service_Point.name == data.name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service point dengan nama '{data.name}' sudah ada.",
        )

    point = Service_Point(**data.model_dump())
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


@router.put("/{service_point_id}", response_model=ServicePointResponse)
async def update_service_point(
    service_point_id: UUID,
    data: ServicePointUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update titik service."""
    point = await ensure_service_point_exists(db, service_point_id)
    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != point.name:
        existing = (await db.execute(
            select(Service_Point).where(Service_Point.name == update_data["name"])
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service point dengan nama '{update_data['name']}' sudah ada.",
            )

    for field, value in update_data.items():
        setattr(point, field, value)

    await db.commit()
    await db.refresh(point)
    return point


@router.delete("/{service_point_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_point(
    service_point_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus titik service (gagal jika masih dipakai order service)."""
    point = await ensure_service_point_exists(db, service_point_id)

    in_use = (await db.execute(
        select(func.count()).select_from(Order_Service).where(
            Order_Service.service_point_id == service_point_id
        )
    )).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tidak bisa menghapus service point — masih dipakai oleh {in_use} order service.",
        )

    await db.delete(point)
    await db.commit()
    return None
