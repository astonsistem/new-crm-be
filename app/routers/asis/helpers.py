"""Shared helpers untuk CRUD ASIS entities di CRM."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asis_sync import AsisBranch, AsisCompany, AsisWarehouse


async def ensure_company_exists(
    db: AsyncSession, company_id: UUID, *, detail: str = "Company tidak ditemukan."
) -> AsisCompany:
    company = (await db.execute(
        select(AsisCompany).where(AsisCompany.id == company_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return company


async def ensure_branch_exists(
    db: AsyncSession, branch_id: UUID, *, detail: str = "Branch tidak ditemukan."
) -> AsisBranch:
    branch = (await db.execute(
        select(AsisBranch).where(AsisBranch.id == branch_id)
    )).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return branch


async def ensure_warehouse_exists(
    db: AsyncSession, warehouse_id: UUID, *, detail: str = "Warehouse tidak ditemukan."
) -> AsisWarehouse:
    warehouse = (await db.execute(
        select(AsisWarehouse).where(AsisWarehouse.id == warehouse_id)
    )).scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return warehouse


async def ensure_unique_asis_id(
    db: AsyncSession,
    model,
    asis_id: str,
    *,
    exclude_id: UUID | None = None,
    label: str = "Record",
) -> None:
    stmt = select(model).where(model.asis_id == asis_id)
    if exclude_id:
        stmt = stmt.where(model.id != exclude_id)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} dengan asis_id '{asis_id}' sudah ada.",
        )


async def ensure_unique_asis_code(
    db: AsyncSession,
    model,
    asis_code: str,
    *,
    exclude_id: UUID | None = None,
    label: str = "Record",
) -> None:
    stmt = select(model).where(model.asis_code == asis_code)
    if exclude_id:
        stmt = stmt.where(model.id != exclude_id)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} dengan asis_code '{asis_code}' sudah ada.",
        )
